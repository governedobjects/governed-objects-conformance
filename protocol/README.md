# Adapter Protocol (reference note)

> **NON-NORMATIVE · TEST INFRASTRUCTURE · NOT A GOVERNED OBJECTS INTERCHANGE FORMAT**

This protocol only connects the conformance runner to an adapter that drives one implementation. It is not a Governed Objects wire format, serialization, network protocol or provider protocol. The [adapter-author guide](../docs/adapter-guide.md) explains how to use it; this note and `protocol.schema.json` list every operation and field the Core runner uses.

## Running an adapter

```
python -m runner --adapter-command "<command line>" [--adapter-cwd DIR] --output-dir DIR
```

The command is split with shell quoting rules and run **without a shell**. The runner starts it once per run, speaks the protocol below on its stdin/stdout, and keeps its stderr for diagnostics. The runner has no knowledge of how an adapter is built or which implementation it drives.

## Transport

- stdin/stdout, newline-delimited JSON; one request line, one response line.
- The request `id` is echoed in the response.

## Operations

| Operation | Purpose |
| --- | --- |
| `capabilities` | Return the self-declaration and capability claims (below) |
| `reset` | Discard object state and revocations; keep fixture definitions already received |
| `define_fixture_types` | Receive the suite-owned fixture definitions; echo `fixtures_sha256` |
| `restart` | Restart the runtime over the surviving store, optionally revoking actors (`revoke`) |
| `create` / `read` / `mutate` / `transition` | Governed operations by a named fixture actor |
| `add_relationship` / `remove_relationship` | Relationship operations |
| `detach` | Operational-metadata-only operation (conditional) |
| `restore` | Restore objects through the runtime's governed restoration path |
| `get_history` / `replay` / `semantic_view` | Observer channel (administrative; never caller-visible) |
| `set_clock` | Only when `harness_clock` is declared |

Field shapes are in `protocol.schema.json` (`$defs/req_<op>`, `$defs/response`).

## Normalized outcomes

`ACCEPTED`, `AUTHORIZATION_DENIED`, `SEMANTICALLY_INVALID`, `CONFLICT`, `REFUSED`, `UNMAPPABLE`, and `UNCLASSIFIED` (the runtime executed the operation and left a non-accepted result without an outcome class). Adapters must not infer hidden semantics to make scenarios pass; report `UNMAPPABLE` when the implementation cannot expose a distinction honestly.

## Self-declaration (`capabilities`)

Required, and recorded by the runner as **self-declared**:

- `implementation.name`, `implementation.version`
- `spec_version` (`v0alpha1`), `spec_revision` (`draft2.2`), `core_claimed` (`true`)
- `profiles_claimed` (list, possibly empty; the Core suite does not test profiles)

The remaining capability fields (`replay_types`, `restoration`, `restorable_types`, `create_with_relationships`, `operational_metadata_ops`, `harness_clock`, `concurrent_invocation`, `restart`, `governance_reconfiguration`, `declared_refusals`, `version_token_grammar`, ...) are the conditional-capability claims that decide whether conditional scenarios apply. An optional `build` object may carry implementation-specific build facts; it is recorded verbatim and never used to judge a run.

## Suite-owned fixtures

`fixtures/fixtures.json` defines the fixture types, actors and fixture rules (for example "a work-item title must not be blank"). The runner sends it in `define_fixture_types` (after every `reset`) and the adapter must implement it through the implementation under test and echo `fixtures_sha256`. An adapter that does not echo the digest cannot produce a claim-supporting bundle.

## Results

Each run writes `results-bundle.json` (self-attested; format described in the adapter-author guide), transcripts and human-readable reports. `python -m runner --verify-bundle DIR` checks a bundle against the suite checkout.
