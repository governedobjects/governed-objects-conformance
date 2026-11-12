# Adapter-Author Guide

> **NON-NORMATIVE · TEST INFRASTRUCTURE · NOT A GOVERNED OBJECTS INTERCHANGE OR WIRE FORMAT**

An adapter connects the conformance runner to one implementation. This guide is for people writing an adapter for their own implementation. The authoritative machine-readable description of every request and field is [`protocol/protocol.schema.json`](../protocol/protocol.schema.json); this guide explains how the pieces fit and what the runner does with them. If the two ever disagree, the schema and the runner win; please report the difference.

## 1. What an adapter is

An adapter is a program that:

- reads one JSON request per line from standard input and writes exactly one JSON response line per request to standard output;
- translates each request into calls on your implementation's public API, and translates what the implementation returns into the response shape below;
- **normalizes but never repairs**: it must not add behavior your implementation lacks (no faked version bumps, no synthetic relationship removal, no invented history), must not hide a deficiency to make a scenario pass, and must not guess a distinction your implementation does not expose. Where a distinction cannot be observed honestly, return `UNMAPPABLE`.

The runner knows nothing about your language, build system or implementation. The only coupling is a command line.

## 2. Launch model

```
python -m runner --adapter-command "<command line>" [--adapter-cwd DIR] --output-dir DIR
```

- The command line is split with shell quoting rules and started **without a shell**. Any build step must happen inside the command (a launcher script is the usual way).
- The runner starts the adapter **once per run** and keeps the process for all scenarios. It starts the process in its own process group so a timeout can end the adapter and anything it started.
- Standard error is captured for diagnostics (the tail is shown if the adapter fails). Standard output must carry protocol lines only.
- Send one response line per request line, in order. The response `id` must echo the request `id`.
- Close of standard input means the run is over; exit then.
- The runner uses the Python standard library only. Your adapter can be written in any language.

Sequence of a run:

1. `capabilities` (the first response may take up to `--startup-timeout`, default 300 seconds, so the adapter may build or load first);
2. `reset`, then `define_fixture_types`;
3. for each scenario: `reset`, `define_fixture_types`, then the scenario's steps;
4. if any `define_fixture_types` response fails to echo the digest, the bundle is not claim-supporting.

## 3. Requests and responses

Every request is a JSON object with `op` and an `id`. Governed operations name an `actor` (a fixture actor such as `writer` or `reader`, defined in `fixtures/fixtures.json`). Field shapes are in the schema (`$defs/req_<op>`).

| `op` | Purpose | Fields (required in bold) |
| --- | --- | --- |
| `capabilities` | Return the self-declaration and capability claims (section 4) | |
| `reset` | Discard all object state and revocations; **keep** the fixture definitions already received | |
| `define_fixture_types` | Receive the suite-owned fixtures; echo `fixtures_sha256` | **`fixtures`**, **`fixtures_sha256`** |
| `restart` | Restart the runtime over the surviving store, optionally revoking the named actors' grants | `revoke` (array of actors) |
| `create` | Create an object | **`actor`**, **`object_id`**, **`type`**, **`initial_state`**, `relationships`, `operational_metadata` |
| `read` | Governed read | **`actor`**, **`object_id`** |
| `mutate` | Change accepted state fields | **`actor`**, **`object_id`**, **`changes`**, `type`, `expected_version` |
| `transition` | Request a lifecycle transition | **`actor`**, **`object_id`**, **`to`**, `type`, `expected_version` |
| `add_relationship` / `remove_relationship` | Relationship operations | **`actor`**, **`object_id`**, **`relationship`** (`type`, `target`), `expected_version` |
| `detach` | Operational-metadata-only operation (conditional on `operational_metadata_ops`) | **`object_id`**, `actor` |
| `restore` | Restore objects through your implementation's governed restoration path | **`actor`**, **`objects`** |
| `get_history` / `replay` / `semantic_view` | Observer channel: administrative reads of canonical history, replayed state and the semantic view | **`object_id`** |
| `set_clock` | Not sent by suite `0.1.0` (see section 6) | **`at`** |

Notes:

- `mutate` and `transition` without `type` target a work-item (`conformance.work-item`).
- `expected_version` is an opaque Object Version token in your own grammar (a JSON string or integer, compared by the suite for equality only, never parsed or coerced); `null`/absent means no precondition. A value your implementation cannot accept is a request error or a refusal, as appropriate.
- `initial_state` and `changes` values are strings except where a scenario deliberately sends another JSON type to test refusal. Pass them through.

### Response

```json
{"id": "...", "ok": true, "outcome": "ACCEPTED", "unmappable": false,
 "caller_result": {}, "semantic_view": {}, "canonical_history": []}
```

- `ok`: `false` only for a request the adapter could not carry out (an adapter or protocol fault), **never** for a refused operation. The runner reports `ok: false` as ADAPTER-ERROR.
- `outcome` (required): one of `ACCEPTED`, `AUTHORIZATION_DENIED`, `SEMANTICALLY_INVALID`, `CONFLICT`, `REFUSED`, `UNMAPPABLE`, `UNCLASSIFIED`.
  - Take the class from your implementation's own classification. Do not infer it from message text. If the implementation executed the operation and left a non-accepted result **without** a class, report `UNCLASSIFIED` (the scenario then fails; it never passes on a guess).
  - `UNMAPPABLE` (with `unmappable: true`) means your implementation cannot expose the distinction the request needs. Scenarios treat it as ADAPTER-ERROR unless the step is explicitly marked as allowed to be unmappable (then the scenario is NOT EXECUTABLE).
- `outcome_native`, `outcome_detail`: optional strings; `outcome_detail` appears in notes.
- `caller_result`: **the exact value your implementation returned to the requester**, serialized with nothing removed, added or renamed. The runner scans it for protected values to test the disclosure requirements, so an adapter that trims or masks fields would hide a leak and violates the contract.
- `semantic_view`, `canonical_history`: the **observer channel** — administrative observations of the stored object, made after the step, never caller-visible. `semantic_view` has `canonical_identity`, `type_identity`, `type_version` (omit or null if not exposed), `object_version` (an opaque token: the runner only compares for equality), `accepted_state`, `relationships` (`source`, `type`, `target`) and `canonical_history_summary` (entries with `effect` of `object_created`, `state_updated`, `lifecycle_transition`, `relationship_added` or `relationship_removed`, plus identity, version, `actor`, `accepted_at`). Read audit records and rejected attempts may be reported separately but are not canonical history.
- `error`: a string when `ok` is false.

Keep the two channels apart. Disclosure and invariance checks use only `caller_result`; canonical effects and lineage use only the observer channel.

## 4. Capability and claim declarations (`CONF-CLAIM-001`)

The `capabilities` response is your **self-declaration**. The runner records it as self-declared and never inspects the implementation, its source or how it was built. Required fields:

| Field | Value |
| --- | --- |
| `implementation.name` | non-empty string |
| `implementation.version` | non-empty string; to support a claim it must be a concrete version (see section 8) |
| `spec_version` | `v0alpha1` |
| `spec_revision` | `draft2.2` |
| `core_claimed` | `true` |
| `profiles_claimed` | list of profile names, possibly empty (the Core suite does not test profiles) |

An incomplete declaration aborts a full run; a diagnostic run records it and is never claim-supporting. `spec_version` and `spec_revision` must match the target stated in the suite's `SUITE.json`.

The remaining capability fields are **conditional-capability claims**. A conditional scenario runs only when you declare the capability that triggers it; otherwise its result is NOT APPLICABLE. Declare honestly: claiming a capability you do not have produces failures, and omitting one you have produces NOT APPLICABLE results, which are reported as such and never as PASS. The fields (see `$defs/capabilities` for types) include `replay` and `replay_types`, `restoration` and `restorable_types`, `create_with_relationships`, `operational_metadata_ops`, `restart`, `governance_reconfiguration`, `relationship_add`/`relationship_remove`, `mutable_objects`, `unconditional_mutation`, `expected_version_required`, `type_version_exposed`, `semantic_portability_view`, `version_token_grammar`, `object_version_ceiling`, `never_issued_version_token`, `declared_refusals`, `actors`, `harness_clock`, `concurrent_invocation` and free-text `notes`. Each scenario file states its trigger in `applicability`.

`never_issued_version_token` is optional: a token, in your own grammar, that this run guarantees was never issued for any object. A few scenarios need a precondition value that is neither current nor one your implementation has ever issued; they use this field when you supply it, and fall back to a decimal-integer literal (backward-compatible with a decimal-integer token grammar) when you do not. If your token grammar is not decimal-integer, declare this field or those scenarios cannot be expressed against your adapter.

An optional `build` object may carry implementation-specific build facts (toolchain, module identity and so on). It is recorded verbatim and never used to judge a run. Avoid absolute paths in it: the default bundle redacts them (section 9) but redaction is a safety net, not a contract.

## 5. Suite-owned fixtures

The suite, not the adapter, defines what the fixture objects are. [`fixtures/fixtures.json`](../fixtures/fixtures.json) defines:

- the abstract permissions and the actors with their permissions;
- the fixture types (`conformance.work-item`, `conformance.record`, `conformance.party`): fields, fields required on create, lifecycle states and transitions, create defaults, actions and relationship types;
- the **fixture rules** that the implementation must enforce through its own public API, for example "a work-item title must not be blank" (`title-not-blank`).

The runner sends the full definition in `define_fixture_types` (once at the start and again after every `reset`). The adapter must:

1. implement the received definitions through your implementation's public type, permission and rule mechanisms;
2. keep them across `reset` and re-apply them on `restart`;
3. answer with `outcome: ACCEPTED` and `fixtures_sha256` equal to the request's digest.

An adapter that does not echo the digest cannot produce a claim-supporting bundle (a full run aborts). The adapter must not add, drop or change types, actors or rules, and must not default missing fields (a missing required title is a rejection, not "Untitled").

## 6. NOT APPLICABLE versus NOT EXECUTABLE

These are distinct results and neither is a PASS.

| Result | Meaning | Examples |
| --- | --- | --- |
| **NOT APPLICABLE** | The scenario's claim-based trigger is absent: you did not declare the capability that makes the scenario relevant | A replay scenario when you declare no replay for the type; a restoration scenario when `restoration` is not declared |
| **NOT EXECUTABLE** | The trigger is present, or the scenario is unconditional, but the scenario cannot be carried out here | The adapter returned `UNMAPPABLE` on a step the scenario allows to be unmappable; a setup step whose provocation could not be established; a harness capability the suite lacks |

A **mandatory** scenario that is NOT EXECUTABLE does not by itself stop a claim, but it is named in the claim text and in the report (section 8).

**Scenarios with no assertions.** The runner never executes a scenario whose `assert` list is empty: it is recorded as NOT EXECUTABLE, whatever the adapter declares, its steps are not sent to the adapter, and the note says the suite does not yet test it (planned for suite `0.2.0`). The rule is generic, not tied to scenario IDs. In suite `0.1.0` it applies to `D22-CON-001` (concurrent invocation) and `D22-CS4-003` (timestamp independence); see [gap-table.md](gap-table.md). Declaring `concurrent_invocation` or `harness_clock` has no effect in `0.1.0`: those scenarios are NOT EXECUTABLE either way, and `set_clock` is never sent.

## 7. Timeouts

- Each request has a timeout: `--request-timeout` seconds (default **30**).
- The first response (to `capabilities`) has `--startup-timeout` seconds (default **300**), so an adapter may build before it answers.
- A request that does not answer in time is **terminated**: the adapter's process group is killed, the scenario is recorded as **ADAPTER-ERROR** (never PASS or NOT EXECUTABLE), and the runner restarts the adapter for the next scenario. If restarting fails twice in a row, the remaining scenarios are reported as ADAPTER-ERROR.
- A bundle with ADAPTER-ERROR on any scenario is not claim-supporting.
- Choose timeouts that suit your implementation; both values are recorded in the bundle under `run_options`.

## 8. The results bundle and claims

Each run writes `results-bundle.json` (format `governed-objects-conformance-results/1`), `transcripts/adapter.jsonl` and human-readable reports. Main fields:

| Field | Content |
| --- | --- |
| `attestation` | `self-attested`, `certification: none`, and the statement |
| `mode`, `claim_supporting`, `claim_support_blockers`, `label` | whether the run can support a claim and why not |
| `claim_text` | wording for a claim; `null` unless `claim_supporting` |
| `not_executed_statement` | for example "Not executed by suite 0.1.0: D22-CON-001, D22-CS4-003." when mandatory scenarios could not be executed; present whether or not the bundle supports a claim |
| `suite` | name, version, `prerelease`, integrity status against `SUITE-MANIFEST.json` |
| `spec` | specification version, revision, profile scope |
| `scenario_manifest` | scenario count and a hash of the scenario set |
| `fixtures` | fixture digest, version, types, `acknowledged` |
| `adapter` | command, working directory label, declaration, declaration problems, verbatim capabilities |
| `environment` | runner and Python version, OS family, architecture, suite version |
| `run_options` | timeouts, and whether local detail was included |
| `summary`, `results` | counts (MUST and SHOULD separately) and per-scenario results |
| `transcripts`, `integrity` | hashes of the transcript and of the bundle body |

`claim_supporting` is true only when **all** of these hold:

1. a full run of every scenario, not `--diagnostic`, no `--scenario` subset;
2. a complete adapter declaration and acknowledged fixture definitions;
3. suite files unmodified: they match `SUITE-MANIFEST.json`;
4. **the suite version is not a pre-release.** Any semantic-version pre-release suffix (`-dev`, `-alpha`, `-beta`, `-rc.1` and the like) blocks claims;
5. **a concrete implementation version**: non-empty and not a placeholder. Placeholders are values starting (case-insensitively) with `unversioned`, `unknown` or `dev`. Third-party version formats vary, so semantic versioning is not required;
6. no FAIL and no ADAPTER-ERROR.

NOT APPLICABLE, NOT EXECUTABLE and SHOULD-DEVIATION results do not block a claim. Whenever mandatory scenarios are NOT EXECUTABLE, `claim_text` (when present), `not_executed_statement` and `latest.md` name them. There is no flag that overrides these rules.

Integrity is hash-based only. `--verify-bundle DIR` checks that a bundle is internally consistent and was produced by this unmodified suite. It is not a signature; it does not detect an adapter that lies or a bundle edited together with its hash. Signing belongs with a certification program, not this suite. The bundle is self-attested.

## 9. What a default bundle does not contain

By default the bundle and the reports contain no absolute paths, user names, host names or home directories. Such values anywhere in the bundle, including in your adapter's responses, are replaced by `<abs-path>`, `<local>` or `<adapter-workdir>`. The environment block keeps only the OS family, architecture, Python version and suite version. Source-control metadata in adapter-supplied information is also dropped by default: keys such as `vcs`, `vcs.revision`, `vcs.time`, `vcs.modified` (and `commit`/`revision` keys inside `build`), and commit-hash strings (40-character or abbreviated hexadecimal) become `<commit-hash>`. The runner's own SHA-256 integrity fields are not touched. `--include-local-detail` keeps all of this local detail for private diagnostics (and adds the platform string and invocation); it is recorded in `run_options`, the console and `latest.md` show a warning, and the bundle should be reviewed before sharing. Claim support is unchanged.

## 10. A minimal worked example

The suite's own self-tests use a small third-party-style adapter, [`tests/fake_adapter.py`](../tests/fake_adapter.py), which wraps an in-memory fake implementation. Its entire protocol loop is:

```python
import json, sys

for line in sys.stdin:                       # one request per line
    req = json.loads(line)
    resp = dict(my_implementation.handle(req))   # your translation layer
    resp["id"] = req.get("id")               # echo the request id
    if req["op"] == "define_fixture_types":
        resp["fixtures_sha256"] = req["fixtures_sha256"]   # acknowledge the fixtures
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()                       # one response line per request
```

with a `capabilities` response beginning:

```json
{"ok": true, "outcome": "ACCEPTED", "capabilities": {
  "implementation": {"name": "fake-third-party", "version": "dev-fake"},
  "spec_version": "v0alpha1", "spec_revision": "draft2.2",
  "core_claimed": true, "profiles_claimed": [],
  "restoration": true, "restorable_types": ["conformance.record"]}}
```

To run the sample from the root of this repository:

```
python -m runner --adapter-command "python3 tests/fake_adapter.py" --output-dir results-fake
python -m runner --verify-bundle results-fake
```

`dev-fake` is a placeholder version (section 8), so a run of the sample never supports a claim. Its results are test output, not a claim about any implementation.

A short exchange (responses abbreviated):

```
> {"op": "create", "id": "adapter-5", "actor": "writer", "object_id": "wi-1",
   "type": "conformance.work-item", "initial_state": {"title": "First"}}
< {"id": "adapter-5", "ok": true, "outcome": "ACCEPTED", "unmappable": false,
   "caller_result": {"outcome": "ACCEPTED", "object": {"version": 1, "state": {"title": "First", "status": "draft"}}},
   "semantic_view": {"channel": "observer", "canonical_identity": "wi-1", "type_identity": "conformance.work-item",
                     "object_version": 1, "accepted_state": {"title": "First", "status": "draft"}, "relationships": [],
                     "canonical_history_summary": [{"effect": "object_created", "object_version": 1, "actor": "writer"}]}}
> {"op": "mutate", "id": "adapter-6", "actor": "reader", "object_id": "wi-1", "changes": {"title": "x"}}
< {"id": "adapter-6", "ok": true, "outcome": "AUTHORIZATION_DENIED", "unmappable": false,
   "caller_result": {"outcome": "AUTHORIZATION_DENIED", "object": {"version": 1, "state": {"title": "First", "status": "draft"}}},
   "semantic_view": {"object_version": 1, "accepted_state": {"title": "First", "status": "draft"}}}
```

To try your own adapter: run the same command with your own adapter command line, with `--diagnostic --scenario C-ID-001` first (a quick check that the protocol works), then a full run, then `--verify-bundle`.

## 11. Checklist

- [ ] The adapter answers every request line with exactly one response line and echoes `id`.
- [ ] `capabilities` returns a complete, honest self-declaration with a concrete `implementation.version`.
- [ ] `define_fixture_types` implements the received definitions and echoes `fixtures_sha256`; the definitions survive `reset` and are re-applied on `restart`.
- [ ] `caller_result` is the unmodified value your implementation returned.
- [ ] Outcome classes come from your implementation; unexposed distinctions are `UNMAPPABLE` and uncategorized failures are `UNCLASSIFIED`.
- [ ] Conditional capabilities are declared only if they exist.
- [ ] A request cannot hang: your adapter answers or exits within the request timeout.
