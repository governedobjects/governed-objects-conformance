# Governed Objects Conformance Suite

**Status: Experimental.** This is the open Core conformance suite for the Governed Objects Specification. It runs black-box scenarios against an implementation through a small adapter and writes a self-attested results bundle. It is not certification.

Version numbers of the suite, the specification and any runtime are independent of each other. A `0.x` suite version means the suite itself is experimental.

## Compatibility

| Suite version | Specification revision targeted | Scope |
| --- | --- | --- |
| `0.1.0` | `v0alpha1 draft2.2` | Core |

The suite version is stored only in the file `VERSION`. `SUITE.json` states which specification revision each suite version targets. Suite, specification and runtime version numbers are not linked: a new suite version may target the same specification revision, and a runtime release does not imply a suite release.

`VERSION` is `0.1.0`. A `0.x` suite version is not itself a pre-release marker: results from it can support a claim once the other [release rules](#release-rules) are met. A suite version with a semantic-version pre-release suffix (`-dev`, `-alpha`, `-beta`, `-rc.1` and the like) is what cannot support a claim.

## What is in this repository

- `scenarios/`: the Core scenarios, each traced to specification requirement identifiers.
- `fixtures/fixtures.json`: the fixture types, actors and fixture rules, defined once by the suite.
- `protocol/`: the adapter protocol (NDJSON over stdin/stdout) and its JSON Schema. It is test infrastructure, not a Governed Objects interchange or wire format.
- `runner/`: the runner (Python standard library only).
- `docs/`: the [adapter-author guide](docs/adapter-guide.md), the [requirement gap table](docs/gap-table.md), the conformance model and the scenario format.
- `tests/`: the suite's self-tests and a sample third-party-style adapter (`tests/fake_adapter.py`). Run the self-tests from the root of this repository with `python -m unittest discover -s tests`.
- `LICENSE` and `NOTICE`.

## How to run it

You need Python 3 (the runner uses only the standard library and has been run with Python 3.12), this repository, and an adapter: a program that implements the protocol in `protocol/` by driving your implementation. See the [adapter-author guide](docs/adapter-guide.md).

Run these commands from the root of this repository:

```
python -m runner --adapter-command "<command that starts your adapter>" --output-dir results
python -m runner --verify-bundle results
```

- The command is split with shell quoting rules and run without a shell. Use `--adapter-cwd DIR` to set its working directory.
- The runner starts the adapter once, resets it between scenarios, and gives each request a timeout (`--request-timeout`, default 30 seconds; `--startup-timeout`, default 300 seconds, for the first response).
- `--diagnostic` and `--scenario ID` run a subset or mark the run diagnostic; such bundles never support a claim.
- Example adapters live with their runtimes: https://github.com/governedobjects/governed-objects-python/tree/main/conformance-adapter and https://github.com/governedobjects/governed-objects-go/tree/main/conformance-adapter. Each runtime's README gives its exact command; use a separate `--output-dir` for each run.
- Tested on Linux. macOS is expected to work but is untested. On Windows, use WSL. The adapters are `bash` scripts.

## The results bundle

A run writes to the output directory:

- `results-bundle.json`: the machine-readable record (suite, specification target, scenario set hash, the adapter's self-declaration, per-scenario results, transcript hashes, and a body hash).
- `transcripts/adapter.jsonl`: what the adapter was sent and answered.
- `latest.md`, `requirement-coverage.md`, `scenario-map.md`, `disclosure-evidence.md`: human-readable reports.

The bundle is **self-attested**. The party that ran the suite produced it, and the suite does not verify the adapter or the implementation behind it. Hashes detect accidental or careless edits (`--verify-bundle`); they are not signatures and do not stop someone who edits a bundle and recomputes its hash. The bundle is not certification, endorsement or a production-readiness finding.

By default the bundle and reports contain no absolute paths, user names, host names or home directories, and the environment block keeps only the operating-system family, architecture, Python version and suite version. Source-control details (revision, time, modified flag) and commit-hash strings in adapter-supplied metadata are also removed by default. `--include-local-detail` keeps local detail for private diagnostics, records that in the bundle and shows a warning in the console and report: such a bundle should be reviewed before sharing. Claim support is not affected.

Every result is one of PASS, FAIL, SHOULD-DEVIATION, NOT APPLICABLE, NOT EXECUTABLE or ADAPTER-ERROR. NOT APPLICABLE and NOT EXECUTABLE are never counted as PASS.

## Making a claim

The Governed Objects Specification's [TRADEMARKS.md](https://github.com/governedobjects/governed-objects-spec/blob/main/TRADEMARKS.md) governs claims. In summary:

- **"Implements"** the specification: free to say, in good faith.
- **"Conforms to"** or "compatible with" a specification version: requires passing this suite for that version. The claim must name both the specification version and the suite version, and you must keep the supporting results. If asked in writing, you provide them within 30 days; you may do so confidentially. **Passing this suite is necessary for that claim but is not by itself sufficient**: `CONF-CLAIM-001` also requires satisfying every normative requirement applicable to the claim, naming each conditional capability claimed, and disclosing documented deviations, which this suite's scope (see "What the suite does not test") does not fully verify.
- **"Certified"**: reserved for a separate, optional certification program under a signed agreement. This suite does not certify anything.

When a bundle supports a claim, its `claim_text` field contains wording of the form:

> `<implementation> <version>` passes the Governed Objects Conformance Suite `<suite version>` for `v0alpha1 draft2.2` Core (self-attested; not certified). [Not executed by suite `<suite version>`: `<IDs>`.] Conditional capabilities claimed: `<capability>`, ...

## Release rules

1. **Pre-release suites never support claims.** A suite whose version has a semantic-version pre-release suffix (`-dev`, `-alpha`, `-beta`, `-rc.1` and the like) cannot produce a claim-supporting bundle.
2. **Untested mandatory scenarios are named, and only a suite-caused gap is compatible with a claim.** A mandatory scenario can be NOT EXECUTABLE for one of two different reasons, worded differently in the bundle, the claim text and the human-readable report:
   - **Suite-caused**: the scenario defines no assertions yet (planned for a later suite version), whatever the adapter declares. This does not block a claim. Named, for example: "Not executed by suite 0.1.0: D22-CON-001, D22-CS4-003."
   - **Adapter-caused**: the scenario's trigger condition is present, but a harness capability it also needs was not declared, or a step came back UNMAPPABLE. This blocks a claim: an adapter cannot obtain a claim-supporting result by declaring fewer capabilities than its implementation has. Named, for example: "Not executed because the adapter did not declare a capability the scenario needs: C-REL-009."

Other conditions, all required: a full run of every scenario (not `--diagnostic`, not a subset); a complete adapter declaration; fixture definitions acknowledged by the adapter; an unmodified suite whose files match `SUITE-MANIFEST.json`; a concrete implementation version (non-empty and not a placeholder such as one starting with `unversioned`, `unknown` or `dev`; semantic versioning is not required); and no FAIL or ADAPTER-ERROR on any scenario. A request that times out is reported as ADAPTER-ERROR.

## What the suite does not test

[docs/gap-table.md](docs/gap-table.md) classifies every Core requirement identifier of the targeted revision as tested, partially tested, not executable by this suite, not externally observable or not yet tested, with a reason for each row that is not fully tested. Optional profiles are out of scope. A passing result does not demonstrate interoperability, wire-format compatibility, thread safety or fitness for production.

## Contributing and governance

Contribution terms for this repository, including the Developer Certificate of Origin sign-off, are in [CONTRIBUTING.md](CONTRIBUTING.md). Report security issues as described in [SECURITY.md](SECURITY.md). The process for proposing changes to the specification, and the commitment that the conformance suite stays openly available, are described in the specification repository's [GOVERNANCE.md](https://github.com/governedobjects/governed-objects-spec/blob/main/GOVERNANCE.md).

## License

Apache License 2.0; see `LICENSE` and `NOTICE`. The license does not grant trademark rights; see the specification's TRADEMARKS.md. See also the specification's PATENTS.md: https://github.com/governedobjects/governed-objects-spec/blob/main/PATENTS.md.
