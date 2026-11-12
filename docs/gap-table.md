# Requirement coverage and gaps

Status: Experimental. This table classifies every Core requirement identifier of the targeted specification revision (`v0alpha1 draft2.2`, 66 identifiers) by what suite `0.1.x` tests. It is the public list of gaps; the suite does not claim to cover every requirement.

## Not executable in suite 0.1.0

Two mandatory scenarios exist but define no assertions yet, so suite `0.1.0` records them as NOT EXECUTABLE for every adapter, whatever the adapter declares. Their steps are not sent to the adapter. Both are planned for suite `0.2.0`. Every claim-supporting bundle names them in its claim text.

| Scenario | What it would test | Requirements affected |
| --- | --- | --- |
| D22-CON-001 | Concurrent conditional mutations of one object yield exactly one accepted change and one lineage | CON-CONFLICT-001, CORE-LINEAGE-001, CON-UNIQUE-001 |
| D22-CS4-003 | Natively accepted changes with equal, reversed or future clock timestamps keep acceptance order | EVT-ORDER-001, EVT-CONTENT-001 |

The rows below stay as they are: each affected requirement is also exercised by other scenarios, so it appears as *partially tested* with the not-executable clause named.

## Classes

| Class | Meaning |
| --- | --- |
| tested | at least one unconditional scenario exercises the requirement through the adapter protocol |
| partially tested | exercised, but only for part of the requirement, only indirectly, only by scenarios that apply when the adapter claims a capability, or only by scenarios that need a harness capability the adapter may not declare (reported MUST, but NOT EXECUTABLE rather than NOT APPLICABLE if the adapter omits it) |
| not executable by this suite | a harness limitation: the scenario exists but defines no assertions yet, so the runner does not execute it. Two scenarios, D22-CON-001 (concurrent invocation) and D22-CS4-003 (timestamp independence), are in this state; they are planned for suite 0.2.0. They attach to requirements that other scenarios also exercise, so those requirements appear as *partially tested* below and no requirement is listed here by itself |
| not externally observable | cannot be checked by a black-box test of one implementation |
| not yet tested | observable in principle, but the suite has no scenario or protocol support yet |

Making a conformance claim does not require every requirement to be tested. Scenarios that cannot be executed are named in the claim text; see the README.

## Counts

| Class | Requirements |
| --- | --- |
| tested | 21 |
| partially tested | 27 |
| not executable by this suite | 0 |
| not externally observable | 4 |
| not yet tested | 14 |
| total | 66 |

## Table

| Requirement | Level | Class | Scenarios | Reason (rows not fully tested) |
| --- | --- | --- | --- | --- |
| CORE-ID-001 | MUST | tested | C-ID-001, C-ID-002 |  |
| CORE-ID-002 | MUST | partially tested | C-ID-001, C-ID-002 | exercised only by scenarios that check the observer echoes the requested id, not independent object identity |
| CORE-STATE-001 | MUST | tested | C-PORT-001, C-STATE-001 |  |
| CORE-STATE-002 | MUST | tested | C-STATE-001, C-STATE-002, C-STATE-003, C-STATE-004 |  |
| CORE-GOV-001 | MUST | not externally observable | none | governance-context completeness cannot be observed without implementation internals; no governed-write bypass was found by the scenarios, which proves nothing about absence |
| CORE-HIST-001 | MUST | tested | C-EVT-001, C-REL-004, D22-CS1-003, D22-CS7-001, D22-CS7-002, D22-CS8-001 |  |
| CORE-LINEAGE-001 | MUST | partially tested | D22-CON-001, D22-CS6-001, D22-CS7-001, D22-CS7-002, D22-CS7B-001, D22-CS9-002 | the concurrent-invocation clause is not executable (D22-CON-001, planned for suite 0.2.0); single-lineage behaviour is checked sequentially |
| CORE-EVOL-001 | MUST | not yet tested | none | no type-evolution operation exists in the adapter protocol; part of the requirement depends on conversion mechanisms the specification leaves open |
| TYPE-ID-001 | MUST | tested | C-PORT-001, C-TYPE-001 |  |
| TYPE-VERSION-001 | MUST | tested | C-TYPE-001, C-TYPE-002 |  |
| TYPE-BIND-001 | MUST | partially tested | C-TYPE-002, D22-CS8-001, D22-TYPE-001 | exercised only by scenarios checking a type version stays the same across one mutation |
| TYPE-SUPPORT-001 | MUST | partially tested | D22-TYPE-001 | exercised only by conditional scenarios (D22-TYPE-001); they apply when the adapter claims: declared restoration capability (restoration: true, restorable_types contains conformance.record) |
| TYPE-SEM-001 | MUST | not yet tested | none | needs an operation that returns a type's semantic definition; not in the adapter protocol |
| TYPE-VALID-001 | MUST | tested | C-LIFE-001, C-LIFE-002, C-LIFE-003, C-OP-003, C-STATE-003, C-VALID-001, C-VALID-002, D22-OP-001 |  |
| TYPE-EXT-001 | MUST | partially tested | C-PORT-001 | exercised only by C-PORT-001, which needs the harness capability semantic_portability_view |
| OP-CTX-001 | MUST | partially tested | C-AUTH-001 | checked only indirectly: every request carries an actor and a target |
| OP-OUTCOME-001 | MUST | tested | C-AUTH-002, C-OP-001, C-OP-002, C-OP-003, C-OP-004, C-VALID-002, D22-CS10-001, D22-OP-001 |  |
| OP-ACCEPT-001 | MUST | tested | C-AUTH-001, C-LIFE-001, C-LIFE-002, C-OP-001, C-STATE-001 |  |
| OP-NOCHANGE-001 | MUST | tested | C-AUTH-002, C-CON-001, C-CON-002, C-CON-003, C-LIFE-003, C-OP-004, C-REL-006, C-REL-007, C-REL-008, C-REL-011, C-REL-012, C-REL-013, C-REL-014, C-STATE-002, C-STATE-003, C-STATE-004, C-VALID-001, D22-CS10-001, D22-CS2-RELADD, D22-CS2-RELREMOVE, D22-CS2-RESTORED, D22-CS2-TRANSITION, D22-CS2-UPDATE, D22-CS2-WNR, D22-CS2S-RELADD, D22-CS2S-RELREMOVE, D22-CS2S-TRANSITION, D22-CS2S-UPDATE, D22-CS3-001, D22-CS9-001, D22-OP-001 |  |
| OP-HIST-001 | MUST | tested | C-EVT-001, C-REL-001, C-REL-002, C-REL-003, C-REL-004, C-REL-009, C-REL-010 |  |
| AUTH-BASE-001 | MUST | tested | C-AUTH-001, C-AUTH-002, C-OP-002, C-REL-006, C-REL-011, C-REL-012, C-VALID-002, D22-CS2-RELADD, D22-CS2-RELREMOVE, D22-CS2-TRANSITION, D22-CS2-UPDATE, D22-CS6-001, D22-CS6-002 |  |
| AUTH-NARROW-001 | MUST | not yet tested | none | needs delegated or mandated downstream context on commands; not in the adapter protocol |
| AUTH-APP-001 | MUST | not yet tested | none | needs an Application Context on commands; not in the adapter protocol |
| AUTH-QUERY-001 | MUST | partially tested | D22-CS2R-001 | exercised only by a single-object read denial, not query-level authorization scope |
| AUTH-GRAPH-001 | MUST | not yet tested | none | needs a traversal operation with an inaccessible intermediate object; not in the adapter protocol |
| AUTH-DISCLOSE-001 | MUST | tested | D22-CS2-RELADD, D22-CS2-RELREMOVE, D22-CS2-RESTORED, D22-CS2-TRANSITION, D22-CS2-UPDATE, D22-CS2-WNR, D22-CS2R-001, D22-CS3-001 |  |
| AUTH-ORDER-001 | SHOULD | tested | D22-CS2S-RELADD, D22-CS2S-RELREMOVE, D22-CS2S-TRANSITION, D22-CS2S-UPDATE | exercised as SHOULD scenarios only (reported as deviations, not failures) |
| CON-VERSION-001 | MUST | partially tested | C-CON-005, C-VER-001 | exercised only by scenarios that need the harness capability mutable_objects (C-CON-005 also needs unconditional_mutation) |
| CON-CONFLICT-001 | MUST | partially tested | C-CON-001, C-CON-002, C-CON-003, C-OP-004, C-REL-008, C-REL-013, C-REL-014, C-STATE-004, D22-CON-001, D22-CS1-001, D22-CS1-002, D22-CS2-WNR, D22-CS2S-RELADD, D22-CS2S-RELREMOVE, D22-CS2S-TRANSITION, D22-CS2S-UPDATE, D22-CS9-001, D22-CS9-002 | concurrent conflicting invocations are not executable (D22-CON-001, planned for suite 0.2.0); conflicts are checked sequentially |
| CON-ADVANCE-001 | MUST | tested | C-CON-003, C-REL-001, C-REL-002, C-REL-003, C-REL-015, C-VER-001, D22-CS1-001, D22-CS1-002, D22-CS1-003 |  |
| CON-NOADVANCE-001 | MUST | tested | C-CON-001, C-CON-002, C-CON-003, C-OP-004, C-REL-006, C-REL-007, C-REL-008, C-REL-009, C-REL-010, C-REL-011, C-REL-012, C-REL-013, C-REL-014, C-REL-015, C-STATE-002, C-VALID-001, D22-CS10-001, D22-CS2-RELADD, D22-CS2-RELREMOVE, D22-CS2-TRANSITION, D22-CS2-UPDATE, D22-CS7-001, D22-CS7-002, D22-OP-001 |  |
| CON-UNIQUE-001 | MUST | partially tested | D22-CON-001, D22-CS1-001, D22-CS1-002, D22-CS1-003, D22-CS8-001, D22-CS9-001, D22-CS9-002 | uniqueness under concurrent invocation is not executable (D22-CON-001, planned for suite 0.2.0); checked sequentially |
| EVT-ACCEPT-001 | MUST | tested | C-EVT-002 |  |
| EVT-CONTENT-001 | MUST | partially tested | C-EVT-001, C-EVT-002, C-EVT-003, C-REL-001, C-REL-004, D22-CS4-001, D22-CS4-003 | the timestamp-related clause is not executable (D22-CS4-003, planned for suite 0.2.0); content of accepted history is checked |
| EVT-SEPARATE-001 | MUST | tested | C-EVT-002 |  |
| EVT-BASELINE-001 | MUST | partially tested | C-REPLAY-001, D22-CS4-002, D22-CS5-001, D22-CS5-002 | exercised only by conditional scenarios (C-REPLAY-001, D22-CS4-002, D22-CS5-001, D22-CS5-002); they apply when the adapter claims: canonical-history replay claimed (EVT-REPLAY-001); creation with relationships exposed (create_with_relationships) and replay claimed for conformance.work-item; declared restoration capability (restoration: true, restorable_types contains conformance.record); replay claimed for conformance.record, and declared restoration capability |
| EVT-REPLAY-001 | MUST | partially tested | C-REL-002, C-REL-005, C-REL-016, C-REPLAY-001, D22-CS4-002, D22-CS5-001 | exercised only by conditional scenarios (C-REL-002, C-REL-005, C-REL-016, C-REPLAY-001, D22-CS4-002, D22-CS5-001); they apply when the adapter claims: canonical-history replay claimed (EVT-REPLAY-001); creation with relationships exposed (create_with_relationships) and replay claimed for conformance.work-item; replay claimed for conformance.record, and declared restoration capability |
| EVT-ORDER-001 | MUST | partially tested | C-EVT-003, D22-CS4-001, D22-CS4-002, D22-CS4-003 | timestamp independence of acceptance order is not executable (D22-CS4-003, planned for suite 0.2.0); ordering is checked without clock control |
| EVT-OBS-001 | MUST | not yet tested | none | needs external observation ingestion; not in the adapter protocol |
| EVT-REPAIR-001 | MUST | not yet tested | none | needs provider synchronization; not in the adapter protocol |
| REL-EDGE-001 | MUST | partially tested | C-REL-001 | exercised only by C-REL-001, which needs the harness capability relationship_add; an adapter that does not declare it leaves this requirement NOT EXECUTABLE rather than skipped |
| REL-EQUAL-001 | MUST | partially tested | C-REL-017 | exercised only by C-REL-017, which needs the harness capability relationship_add |
| REL-MULT-001 | MUST | partially tested | C-REL-009, C-REL-017 | exercised only by scenarios that need the harness capability relationship_add |
| REL-ORDER-001 | MUST | partially tested | C-REL-017 | exercised only by C-REL-017, which needs the harness capability relationship_add |
| REL-OWNER-001 | MUST | partially tested | C-REL-015 | exercised only by C-REL-015, which needs the harness capabilities relationship_add and relationship_remove |
| REL-ACCEPT-001 | MUST | partially tested | C-CON-002, C-CON-003, C-REL-001, C-REL-003, C-REL-005 | exercised only by scenarios that need the harness capability relationship_add (C-REL-005 also needs replay) |
| REL-REMOVE-001 | MUST | partially tested | C-REL-002, C-REL-006, C-REL-007, C-REL-008 | exercised only by scenarios that need the harness capabilities relationship_add and relationship_remove (C-REL-002 also needs replay) |
| REL-NOOP-001 | MUST | partially tested | C-REL-009, C-REL-010, C-REL-016, D22-CS7-001, D22-CS7-002 | exercised only by scenarios that need a harness capability (relationship_add and/or relationship_remove for C-REL-009/010/016; restart for D22-CS7-001/002) |
| REL-DUP-001 | MUST | partially tested | C-REL-009, C-REL-016 | exercised only by scenarios that need the harness capability relationship_add (C-REL-016 also needs relationship_remove and replay) |
| REL-ABSENT-001 | MUST | partially tested | C-REL-010, C-REL-016 | exercised only by scenarios that need the harness capability relationship_remove (C-REL-016 also needs relationship_add and replay) |
| REL-AUTH-001 | MUST | tested | C-REL-011, C-REL-012, D22-CS2-RELADD, D22-CS2-RELREMOVE |  |
| REL-PRECOND-001 | MUST | tested | C-REL-013, C-REL-014, D22-CS1-002 |  |
| REL-PRECEDENCE-001 | MUST | tested | C-REL-011, C-REL-012, C-REL-013, C-REL-014, D22-CS2-RELADD, D22-CS2-RELREMOVE, D22-CS2-RESTORED |  |
| REL-REPLAY-001 | MUST | partially tested | C-REL-016, D22-CS5-001, D22-CS5-002 | exercised only by conditional scenarios (C-REL-016, D22-CS5-001, D22-CS5-002); they apply when the adapter claims: canonical-history replay claimed (EVT-REPLAY-001); creation with relationships exposed (create_with_relationships) and replay claimed for conformance.work-item; declared restoration capability (restoration: true, restorable_types contains conformance.record) |
| REL-PORT-001 | MUST | not yet tested | none | needs provider detachment with relationship assertions as a Core scenario; not yet written |
| REL-PORT-002 | MUST | not yet tested | none | needs export of relationships as a distinct set; no export operation in the Core adapter protocol |
| REL-COMPAT-001 | MUST | not yet tested | none | needs import of data with duplicate relationships; no such scenario or protocol path yet |
| REL-TRAVERSE-001 | MUST | not yet tested | none | needs a traversal operation; not in the adapter protocol |
| PORT-SEM-001 | MUST | not yet tested | none | needs an export or transfer claim exercised through the adapter protocol; not in the Core protocol |
| PORT-APP-001 | MUST | not yet tested | none | needs application replacement; not in the adapter protocol |
| PORT-RUNTIME-001 | MUST | not externally observable | none | concerns permission and independence from a vendor; not a black-box check of one implementation |
| PORT-EVOL-001 | MUST | not externally observable | none | the specification leaves conversion mechanisms unresolved, so there is no operation to observe |
| PORT-PROVIDER-001 | MUST | not yet tested | none | needs provider replacement; not in the adapter protocol |
| PORT-RESTORE-001 | MUST | partially tested | D22-CS6-002, D22-CS8-001 | exercised only by conditional scenarios (D22-CS6-002, D22-CS8-001); they apply when the adapter claims: declared restoration capability (restoration: true, restorable_types contains conformance.record) |
| PORT-PRESERVE-001 | MUST | partially tested | D22-CS5-002, D22-CS8-001, D22-TYPE-001 | exercised only by conditional scenarios (D22-CS5-002, D22-CS8-001, D22-TYPE-001); they apply when the adapter claims: declared restoration capability (restoration: true, restorable_types contains conformance.record) |
| CONF-CLAIM-001 | MUST | not externally observable | none | a claim-format requirement, not runtime behaviour; the results bundle and claim text implement the claim format |

Scenario identifiers beginning `C-` are inherited scenarios; those beginning `D22-` were written for this revision of the specification. Scenario classes and applicability are in the generated `scenario-map.md` and `requirement-coverage.md` reports of each run.
