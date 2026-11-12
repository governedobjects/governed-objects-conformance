# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Scenario loading, reference substitution and shared assertion helpers (used by the Draft 2.2 engine)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REF_PATTERN = re.compile(r"\$([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)")


def _parse_default(raw: str) -> Any:
    """Literal fallback for a '$path:default' reference. Digits parse as int."""
    return int(raw) if raw.lstrip("-").isdigit() else raw


def _resolve(ref: str, ctx: dict[str, Any]) -> Any:
    if not ref.startswith("$"):
        return ref
    body = ref[1:]
    has_default = ":" in body
    default = None
    if has_default:
        body, default_raw = body.split(":", 1)
        default = _parse_default(default_raw)
    path = body.split(".")
    cur: Any = ctx.get(path[0])
    for part in path[1:]:
        if cur is None:
            return default if has_default else None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return default if has_default else None
    if cur is None and has_default:
        return default
    return cur


def _substitute(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        return _resolve(value, ctx)
    if isinstance(value, dict):
        return {k: _substitute(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, ctx) for v in value]
    return value


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _relationship_triple(rel: dict[str, Any], source: Any = None) -> tuple[str, str, str]:
    return (
        str(source if source is not None else rel.get("source", "")),
        str(rel.get("type", "")),
        str(rel.get("target", "")),
    )


def _extract_relationship_triples(rels: Any, source: Any = None) -> list[tuple[str, str, str]]:
    if not isinstance(rels, list):
        return []
    triples: list[tuple[str, str, str]] = []
    for rel in rels:
        if isinstance(rel, dict):
            triples.append(_relationship_triple(rel, source=source))
    return triples


def _canonical_relationships_sorted(rels: Any) -> list[dict[str, Any]]:
    if not isinstance(rels, list):
        return []
    return sorted(
        [
            {
                "source": rel.get("source"),
                "type": rel.get("type"),
                "target": rel.get("target"),
            }
            for rel in rels
            if isinstance(rel, dict)
        ],
        key=lambda rel: (str(rel.get("source")), str(rel.get("type")), str(rel.get("target"))),
    )


def _relationship_uniqueness_error(triples: list[tuple[str, str, str]]) -> str | None:
    seen: set[tuple[str, str, str]] = set()
    duplicates: set[tuple[str, str, str]] = set()
    for triple in triples:
        if triple in seen:
            duplicates.add(triple)
        seen.add(triple)
    if not duplicates:
        return None
    formatted = ", ".join(f"({s},{t},{g})" for s, t, g in sorted(duplicates))
    return f"duplicate relationship triples in collection: {formatted}"


def _relationship_sets_equal(
    left_rels: Any,
    right_rels: Any,
    *,
    comparison_mode: str,
) -> tuple[bool, str]:
    if comparison_mode == "set_with_uniqueness":
        left_triples = _extract_relationship_triples(left_rels)
        right_triples = _extract_relationship_triples(right_rels)
        for label, triples in (("left", left_triples), ("right", right_triples)):
            err = _relationship_uniqueness_error(triples)
            if err:
                return False, f"{label} collection: {err}"
        if set(left_triples) != set(right_triples):
            return False, f"relationship sets differ: {set(left_triples)!r} != {set(right_triples)!r}"
        return True, ""

    left = _canonical_relationships_sorted(left_rels)
    right = _canonical_relationships_sorted(right_rels)
    if left != right:
        return False, f"relationship collections differ under sorted-list comparison: {left!r} != {right!r}"
    return True, ""


def _history_from_step(step: dict[str, Any]) -> list[dict[str, Any]]:
    hist = step.get("canonical_history")
    if hist is None:
        hist = _get_path(step.get("semantic_view"), "canonical_history_summary")
    return hist if isinstance(hist, list) else []


def load_scenarios(root: Path) -> list[dict[str, Any]]:
    scenarios = []
    for path in sorted(root.rglob("*.json")):
        if path.name in ("requirements.json",) or "manifests" in path.parts:
            continue
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if "id" in data and "steps" in data:
            scenarios.append(data)
    return scenarios


def evaluate_assertion(
    assertion: dict[str, Any],
    ctx: dict[str, Any],
    *,
    relationship_comparison: str = "sorted_list",
) -> tuple[bool, str]:
    if "step" in assertion and "outcome" in assertion:
        step = ctx.get(assertion["step"], {})
        expected = assertion["outcome"]
        actual = step.get("outcome")
        if actual != expected:
            return False, f"expected outcome {expected}, got {actual} for step {assertion['step']}"
        return True, ""

    if "compare" in assertion:
        left = _resolve(assertion["compare"], ctx) if assertion["compare"].startswith("$") else assertion["compare"]
        if "not_null" in assertion and assertion["not_null"] and left is None:
            return False, f"expected {assertion['compare']} to be non-null"
        if "equals" in assertion:
            right = _substitute(assertion["equals"], ctx)
            if left != right:
                return False, f"expected {assertion['compare']} == {right}, got {left}"
        if "not_equals" in assertion:
            right = _substitute(assertion["not_equals"], ctx)
            if left == right:
                return False, f"expected {assertion['compare']} != {right}, got {left}"
        return True, ""

    if "semantic_view_field" in assertion:
        step_name = assertion.get("step", "_last")
        step = ctx.get(step_name, {})
        view = step.get("semantic_view") or {}
        val = _get_path(view, assertion["semantic_view_field"])
        if "equals" in assertion and val != assertion["equals"]:
            return False, f"semantic_view.{assertion['semantic_view_field']} expected {assertion['equals']}, got {val}"
        if "not_null" in assertion and assertion["not_null"] and val is None:
            return False, f"semantic_view.{assertion['semantic_view_field']} is null"
        return True, ""

    if "relationship_exists" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        view = step.get("semantic_view") or {}
        rels = view.get("relationships") or []
        want = assertion["relationship_exists"]
        for rel in rels:
            if rel.get("type") == want.get("type") and rel.get("target") == want.get("target"):
                return True, ""
        return False, f"relationship not found: {want}"

    if "relationship_absent" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        view = step.get("semantic_view") or {}
        rels = view.get("relationships") or []
        want = assertion["relationship_absent"]
        for rel in rels:
            if rel.get("type") == want.get("type") and rel.get("target") == want.get("target"):
                return False, f"relationship should be absent: {want}"
        return True, ""

    if "relationship_collection_unique" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        view = step.get("semantic_view") or {}
        rels = view.get("relationships") or []
        triples = _extract_relationship_triples(rels)
        err = _relationship_uniqueness_error(triples)
        if err:
            return False, err
        return True, ""

    if "relationship_triple_count" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        view = step.get("semantic_view") or {}
        rels = view.get("relationships") or []
        want = assertion["relationship_triple_count"]
        want_type = want.get("type")
        want_target = want.get("target")
        expected_count = want.get("count")
        actual_count = sum(
            1
            for rel in rels
            if isinstance(rel, dict) and rel.get("type") == want_type and rel.get("target") == want_target
        )
        if actual_count != expected_count:
            return False, (
                f"expected {expected_count} relationship(s) for type={want_type!r} target={want_target!r}, "
                f"got {actual_count}"
            )
        return True, ""

    if "history_accepted_min" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        hist = _history_from_step(step)
        minimum = assertion["history_accepted_min"]
        if len(hist) < minimum:
            return False, f"expected at least {minimum} canonical history entries, got {len(hist)}"
        return True, ""

    if "history_accepted_count" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        hist = _history_from_step(step)
        expected = assertion["history_accepted_count"]
        if len(hist) != expected:
            return False, f"expected {expected} canonical history entries, got {len(hist)}"
        return True, ""

    if "history_relationship_mutation_count" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        hist = _history_from_step(step)
        expected = assertion["history_relationship_mutation_count"]
        actual = sum(
            1
            for evt in hist
            if isinstance(evt, dict) and evt.get("effect") in ("relationship_added", "relationship_removed")
        )
        if actual != expected:
            return False, f"expected {expected} relationship mutation history entries, got {actual}"
        return True, ""

    if "history_unchanged" in assertion:
        left_step = ctx.get(assertion.get("step", "_last"), {})
        right_step = ctx.get(assertion["history_unchanged"], {})
        left = _history_from_step(left_step)
        right = _history_from_step(right_step)
        if left != right:
            return False, (
                f"expected canonical history for {assertion.get('step', '_last')} "
                f"to equal {assertion['history_unchanged']}"
            )
        return True, ""

    if "history_contains" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        hist = _history_from_step(step)
        want = _substitute(assertion["history_contains"], ctx)
        for evt in hist:
            if all(evt.get(k) == v for k, v in want.items()):
                return True, ""
        return False, f"canonical history entry not found: {want}"

    if "history_excludes" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        hist = _history_from_step(step)
        want = _substitute(assertion["history_excludes"], ctx)
        for evt in hist:
            if all(evt.get(k) == v for k, v in want.items()):
                return False, f"canonical history entry should be absent: {want}"
        return True, ""

    if "history_all_fields_not_null" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        hist = _history_from_step(step)
        fields = assertion["history_all_fields_not_null"]
        for idx, evt in enumerate(hist):
            for field in fields:
                if evt.get(field) is None:
                    return False, f"canonical history entry {idx} missing non-null field {field}"
        return True, ""

    if "relationship_set_equals" in assertion:
        left_step = ctx.get(assertion.get("step", "_last"), {})
        right_step = ctx.get(assertion["relationship_set_equals"], {})
        left = _get_path(left_step.get("semantic_view"), "relationships")
        right = _get_path(right_step.get("semantic_view"), "relationships")
        mode = assertion.get("comparison_mode", relationship_comparison)
        ok, msg = _relationship_sets_equal(left, right, comparison_mode=mode)
        if not ok:
            return False, (
                f"expected relationship set for {assertion.get('step', '_last')} "
                f"to equal {assertion['relationship_set_equals']}: {msg}"
            )
        return True, ""

    if "relationship_set_empty" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        rels = _get_path(step.get("semantic_view"), "relationships") or []
        triples = _extract_relationship_triples(rels)
        if assertion.get("relationship_set_empty"):
            if triples:
                return False, f"expected empty relationship collection, got {triples!r}"
            return True, ""
        return False, "relationship_set_empty must be true"

    if "unmappable" in assertion:
        step = ctx.get(assertion.get("step", "_last"), {})
        if bool(step.get("unmappable")) != bool(assertion["unmappable"]):
            return False, f"unmappable expected {assertion['unmappable']}, got {step.get('unmappable')}"
        return True, ""

    return False, f"unknown assertion: {assertion}"
