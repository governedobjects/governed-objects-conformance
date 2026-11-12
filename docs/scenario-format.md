# Scenario Format

Scenarios are JSON test fixtures — **not** Governed Object wire format.

## File Location

`scenarios/<set>/<category>/<id>.json` (sets: `core` and `draft2.1` hold inherited scenarios, `draft2.2` holds scenarios written for the targeted revision). `scenarios/manifests/draft2.2.json` selects the scenarios and lists the claim limitations.

## Structure

```json
{
  "id": "C-CON-001",
  "title": "Human-readable title",
  "requirements": ["CON-CONFLICT-001"],
  "requires_capabilities": {},
  "skip_if_missing": [],
  "steps": [],
  "assert": []
}
```

## Steps

Each step invokes one adapter operation. Step results may be stored with `"as": "variable_name"`.

Supported step operations mirror the adapter protocol: `create`, `read`, `mutate`, `transition`, `add_relationship`, `remove_relationship`, `get_history`, `replay`, `semantic_view`, `restore`, `restart`, `detach`.

Variables from prior steps are referenced as `$variable_name.field.path`.

## Assertions

| Form | Example |
| --- | --- |
| Step outcome | `{"step": "mutate_a", "outcome": "ACCEPTED"}` |
| Field equality | `{"compare": "$after.title", "equals": "Expected"}` |
| Inequality | `{"compare": "$v2", "not_equals": "$v1"}` |
| Non-null field | `{"compare": "$view.semantic_view.type_version", "not_null": true}` |
| History count | `{"history_accepted_min": 3, "step": "history"}` |
| Exact history count | `{"history_accepted_count": 3, "step": "history"}` |
| History content | `{"history_contains": {"effect": "relationship_removed"}, "step": "history"}` |
| Required history fields | `{"history_all_fields_not_null": ["effect", "type_version"], "step": "history"}` |
| Relationship present | `{"relationship_exists": {"type": "owned_by", "target": "party-1"}}` |
| Relationship absent | `{"relationship_absent": {"type": "depends_on", "target": "wi-2"}}` |
| Relationship set unchanged | `{"relationship_set_equals": "before", "step": "after"}` |
| Relationship collection unique | `{"relationship_collection_unique": true, "step": "after"}` |
| Relationship triple count | `{"relationship_triple_count": {"type": "belongs_to", "target": "b", "count": 1}}` |
| History unchanged | `{"history_unchanged": "before", "step": "after"}` |
| History excludes entry | `{"history_excludes": {"effect": "relationship_removed"}}` |
| Relationship mutation history count | `{"history_relationship_mutation_count": 2}` |
| Empty relationship collection | `{"relationship_set_empty": true}` |

Relationship comparison uses set-with-uniqueness: observable triples must be unique, and collections are equal when their sets of `(source, type, target)` triples match. Enumeration order is ignored. Duplicates are detected before set comparison and cause failure. History assertions compare normalized semantic summaries, not implementation-specific event IDs, timestamps or storage envelopes.

A scenario may also carry `applicability` (the claim-based trigger that decides NOT APPLICABLE), `harness_requires` (suite capabilities needed to execute it; otherwise NOT EXECUTABLE), `modality` (`MUST` or `SHOULD`), and per-step `allow_unmappable` and `precondition_outcomes` markers.

## Scenario ID Families

| Prefix | Domain |
| --- | --- |
| C-ID- | Identity |
| C-TYPE- | Type identity/version |
| C-STATE- | Accepted state |
| C-OP- | Operations/outcomes |
| C-AUTH- | Authorization |
| C-VALID- | Validation |
| C-LIFE- | Lifecycle |
| C-CON- | Concurrency |
| C-REL- | Relationships |
| C-EVT- | History/events |
| C-REPLAY- | Replay |
| C-PORT- | Semantic portability exposure |
| D22- | Scenarios written for the targeted revision (clause families CS-1 to CS-10, type and operation checks) |

Scenario IDs supplement, and never replace, specification requirement IDs.
