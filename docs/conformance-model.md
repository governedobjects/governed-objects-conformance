# Conformance Model

This suite is an **experimental executable conformance suite** for the Core semantics of the Governed Objects Specification. Suite `0.1.x` targets `v0alpha1 draft2.2` (stated in `SUITE.json`).

## What is normative

- The Governed Objects Specification. The suite never overrides it.

## What is derived

- `scenarios/draft2.2/requirements.json`: the Core requirement inventory of the targeted revision, with the hash of each requirement's text.
- Scenario JSON files: black-box behavioral scenarios traced to requirement identifiers. Scenarios whose identifiers begin `C-` were written for earlier revisions and are reused where their expected observations remain required (`scenarios/draft2.2/inherited-map.json` records how each applies); those beginning `D22-` were written for this revision.
- Reports: generated per run, next to the results bundle.

## What is test-only

- The adapter protocol (`protocol/`), the semantic view structure, the fixture types and rules (`fixtures/fixtures.json`), and the runner. None of these is a Governed Objects interchange or wire format.

## Requirement classification

| Class | Treatment |
| --- | --- |
| Executable behavior | Direct scenario coverage |
| Static capability / declaration | Semantic view or capability probes |
| Conditional capability | Scenario runs only when the adapter claims the capability; otherwise NOT APPLICABLE |
| Documentation / conformance claim | Not runtime black-box tested |
| Not practically black-box testable | Listed in the [gap table](gap-table.md) |

## Assertion philosophy

A scenario should make a passing result hard to obtain by accident. A scenario that exercises a mutation normally asserts both the normalized outcome and the observable semantic effect or invariant:

- accepted mutations change the relevant accepted canonical semantics, advance the opaque Object Version when required, and leave evidence in canonical history;
- authorization-denied, semantically invalid and conflicting mutations leave accepted state, relationships, Object Version and canonical history unchanged;
- rejections do not disclose protected values to the requester;
- replay checks compare reconstructed observable semantics, not implementation-specific event envelopes.

Object Version assertions use equality only. The suite never assumes numeric increments, ordering, timestamps or lexical properties.

## Result model

| Result | Meaning |
| --- | --- |
| PASS | Every checked requirement is satisfied |
| FAIL | A MUST or MUST NOT is violated |
| SHOULD-DEVIATION | A SHOULD is not followed while every applicable MUST holds; never aggregated with FAIL |
| NOT APPLICABLE | The scenario's claim-based trigger is absent |
| NOT EXECUTABLE | The trigger is present (or the scenario is unconditional) but the scenario cannot be carried out here |
| ADAPTER-ERROR | The adapter could not carry out a step, including a request that timed out |

A scenario that defines no assertions is always NOT EXECUTABLE, never PASS or ADAPTER-ERROR, whatever the adapter declares. NOT APPLICABLE and NOT EXECUTABLE are never counted as PASS. Known implementation gaps are FAIL, not expected-failure.

## Conformance claims

The suite does not certify anything. A bundle that satisfies the release rules in the README supports a self-attested claim of the form given there, subject to the specification's TRADEMARKS.md. Passing this suite does not demonstrate wire or interchange interoperability, thread safety, or any property listed as untested in the [gap table](gap-table.md).
