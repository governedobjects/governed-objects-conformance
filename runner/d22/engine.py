# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Draft 2.2 Core scenario execution and result model.

Result statuses, defined by this suite (not a specification section):

* PASS             every checked requirement is satisfied
* FAIL             a MUST / MUST NOT is violated
* SHOULD-DEVIATION a SHOULD is not followed while every applicable MUST holds
* NOT APPLICABLE   the scenario's claim-based trigger is absent
* NOT EXECUTABLE   the trigger is present but the harness lacks a capability
* ADAPTER-ERROR    the adapter could not carry out a step (harness fault)

A SHOULD-DEVIATION is never aggregated with FAIL. MUST failures and SHOULD
deviations are both retained when they occur in one scenario.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from runner.adapter_client import AdapterClient
from runner.engine import (
    _get_path,
    _resolve,
    _substitute,
    evaluate_assertion,
    load_scenarios,
)
from runner.d22 import referee

PASS = "PASS"
FAIL = "FAIL"
SHOULD_DEVIATION = "SHOULD-DEVIATION"
NOT_APPLICABLE = "NOT APPLICABLE"
NOT_EXECUTABLE = "NOT EXECUTABLE"
ADAPTER_ERROR = "ADAPTER-ERROR"
STATUSES = (PASS, FAIL, SHOULD_DEVIATION, NOT_APPLICABLE, NOT_EXECUTABLE, ADAPTER_ERROR)


# NOT EXECUTABLE cause, for IR-003: only "suite" (no executable assertions) is
# compatible with a claim. "adapter" means a missing harness capability (or an
# UNMAPPABLE step) kept a mandatory scenario from running, which blocks a claim.
NOT_EXECUTABLE_SUITE = "suite"
NOT_EXECUTABLE_ADAPTER = "adapter"


class ScenarioOutcome:
    def __init__(self, scenario_id: str, status: str):
        self.scenario_id = scenario_id
        self.status = status
        self.must_failures: list[str] = []
        self.should_deviations: list[str] = []
        self.notes: list[str] = []
        self.evidence: list[dict[str, Any]] = []
        self.steps: list[dict[str, Any]] = []
        self.not_executable_cause: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "must_failures": self.must_failures,
            "should_deviations": self.should_deviations,
            "notes": self.notes,
            "evidence": self.evidence,
            "not_executable_cause": self.not_executable_cause,
        }


# --- scenario loading -------------------------------------------------------


def load_inherited_map(repo_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    with (repo_root / manifest["inherited_map_path"]).open(encoding="utf-8") as fh:
        return json.load(fh)


def _inherited_to_d22(scenario: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(scenario)
    out["origin"] = "inherited"
    out["disposition"] = entry["disposition"]
    out["modality"] = entry.get("modality", "MUST")
    out["requirements"] = entry.get("draft22_requirements", scenario.get("requirements", []))
    claim_keys = set(entry.get("claim_capabilities", []))
    required = scenario.get("requires_capabilities") or {}
    claims = [{"capability": k} for k in required if k in claim_keys]
    harness = [{"capability": k} for k in required if k not in claim_keys]
    if claims:
        out["applicability"] = {"trigger": entry.get("trigger", "claimed capability"), "claims": claims}
    if harness:
        out["harness_requires"] = harness
    out.pop("requires_capabilities", None)
    out.pop("skip_if_missing", None)
    return out


def load_draft22_scenarios(repo_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    inherited_map = load_inherited_map(repo_root, manifest)["scenarios"]
    excluded = set(manifest.get("exclude_scenarios", []))
    scenarios: dict[str, dict[str, Any]] = {}
    for root_rel in manifest["inherited_scenario_roots"]:
        for scenario in load_scenarios(repo_root / root_rel):
            sid = scenario["id"]
            if sid in scenarios or sid in excluded:
                continue
            if sid not in inherited_map:
                raise ValueError(f"inherited scenario {sid} has no Draft 2.2 revision-map entry")
            scenarios[sid] = _inherited_to_d22(scenario, inherited_map[sid])
    for scenario in load_scenarios(repo_root / manifest["draft22_scenario_root"]):
        sid = scenario["id"]
        if sid in scenarios:
            raise ValueError(f"duplicate scenario id {sid}")
        scenario = dict(scenario)
        scenario["origin"] = "draft2.2"
        scenarios[sid] = scenario
    missing = set(inherited_map) - set(scenarios) - excluded
    if missing:
        raise ValueError(f"revision map names scenarios that were not loaded: {sorted(missing)}")
    return [scenarios[k] for k in sorted(scenarios)]


def is_conditional(scenario: dict[str, Any]) -> bool:
    return bool((scenario.get("applicability") or {}).get("claims"))


# --- triggers -----------------------------------------------------------------


def _condition_holds(cond: dict[str, Any], caps: dict[str, Any]) -> bool:
    val = caps.get(cond["capability"])
    if "contains" in cond:
        return isinstance(val, list) and cond["contains"] in val
    if cond.get("nonempty"):
        return bool(val)
    if "equals" in cond:
        return val == cond["equals"]
    return val is True


def _describe(cond: dict[str, Any]) -> str:
    if "contains" in cond:
        return f"{cond['capability']} contains {cond['contains']!r}"
    if cond.get("nonempty"):
        return f"{cond['capability']} non-empty"
    if "equals" in cond:
        return f"{cond['capability']} == {cond['equals']!r}"
    return f"{cond['capability']}"


def applicability(scenario: dict[str, Any], caps: dict[str, Any]) -> tuple[str | None, str]:
    appl = scenario.get("applicability") or {}
    for cond in appl.get("claims", []):
        if not _condition_holds(cond, caps):
            return NOT_APPLICABLE, f"trigger absent: {appl.get('trigger', '')} ({_describe(cond)} not declared)"
    for cond in scenario.get("harness_requires", []):
        if not _condition_holds(cond, caps):
            return NOT_EXECUTABLE, f"harness capability absent: {_describe(cond)}"
    return None, ""


# --- execution ----------------------------------------------------------------


def supplied_by_requester(record: dict[str, Any]) -> dict[str, Any]:
    """Content the requester supplied: the scenario request and the exact
    native request the adapter passed to the runtime API."""
    return {"request": record["request"], "native_request": record["response"].get("native_request")}


def token_grammar(caps: dict[str, Any]) -> str | None:
    grammar = caps.get("version_token_grammar")
    return grammar.split()[0] if isinstance(grammar, str) and grammar else None


def run_d22_scenario(
    client: AdapterClient,
    scenario: dict[str, Any],
    *,
    relationship_comparison: str = "set_with_uniqueness",
) -> ScenarioOutcome:
    sid = scenario["id"]
    caps = client.capabilities
    gate, reason = applicability(scenario, caps)
    if gate == NOT_APPLICABLE:
        out = ScenarioOutcome(sid, gate)
        out.notes.append(reason)
        return out
    if not scenario.get("assert"):
        # A scenario that asserts nothing cannot establish a pass or a failure, whatever
        # the adapter declares. Its steps are not sent to the adapter. This is suite-caused:
        # it is compatible with a claim (IR-003).
        out = ScenarioOutcome(sid, NOT_EXECUTABLE)
        out.not_executable_cause = NOT_EXECUTABLE_SUITE
        out.notes.append(
            "the suite does not yet test this scenario (it defines no assertions); planned for suite 0.2.0"
        )
        return out
    if gate:
        out = ScenarioOutcome(sid, gate)
        if gate == NOT_EXECUTABLE:
            out.not_executable_cause = NOT_EXECUTABLE_ADAPTER
            reason = f"not executed because the adapter did not declare a required harness capability: {reason}"
        out.notes.append(reason)
        return out

    ctx: dict[str, Any] = {"caps": caps, "_steps": [], "_req": {}}
    out = ScenarioOutcome(sid, PASS)
    for idx, step in enumerate(scenario.get("steps", [])):
        op = step["op"]
        payload = {
            k: v for k, v in step.items() if k not in ("op", "as", "allow_unmappable", "note", "precondition_outcomes")
        }
        payload = _substitute(payload, ctx)
        payload["op"] = op
        name = step.get("as") or f"_{idx}"
        try:
            resp = client.request(payload)
        except Exception as exc:  # noqa: BLE001
            out.status = ADAPTER_ERROR
            out.notes.append(f"step {name} ({op}): {exc}")
            return out
        record = {"name": name, "op": op, "request": payload, "response": resp}
        ctx["_steps"].append(record)
        out.steps.append(record)
        ctx["_req"][name] = supplied_by_requester(record)
        ctx[name] = resp
        ctx["_last"] = resp
        if resp.get("ok") is False:
            out.status = ADAPTER_ERROR
            out.notes.append(f"step {name} ({op}) request error: {resp.get('error')}")
            return out
        if "precondition_outcomes" in step and resp.get("outcome") not in step["precondition_outcomes"]:
            out.status = NOT_EXECUTABLE
            out.not_executable_cause = NOT_EXECUTABLE_ADAPTER
            out.notes.append(
                f"not executed because the adapter did not declare a capability the scenario needs: "
                f"setup step {name} ({op}) gave {resp.get('outcome')} ({resp.get('outcome_detail')}); "
                f"the scenario's provocation could not be established"
            )
            return out
        if resp.get("unmappable"):
            if step.get("allow_unmappable"):
                out.status = NOT_EXECUTABLE
                out.not_executable_cause = NOT_EXECUTABLE_ADAPTER
                out.notes.append(
                    f"not executed because the adapter did not declare this as expressible: "
                    f"step {name} ({op}) is not expressible on this adapter: {resp.get('outcome_detail')}"
                )
                return out
            out.status = ADAPTER_ERROR
            out.notes.append(f"step {name} ({op}) unexpectedly UNMAPPABLE: {resp.get('outcome_detail')}")
            return out

    for assertion in scenario.get("assert", []):
        level = assertion.get("level", scenario.get("modality", "MUST"))
        ok, msg, evidence = evaluate_d22_assertion(assertion, ctx, relationship_comparison=relationship_comparison)
        if evidence:
            out.evidence.append({"assertion": _label(assertion), **evidence})
        if ok:
            continue
        text = f"[{','.join(assertion.get('requirements', [])) or 'scenario'}] {msg}"
        if level == "SHOULD":
            out.should_deviations.append(text)
        else:
            out.must_failures.append(text)

    if out.must_failures:
        out.status = FAIL
    elif out.should_deviations:
        out.status = SHOULD_DEVIATION
    return out


def _label(assertion: dict[str, Any]) -> str:
    if "label" in assertion:
        return assertion["label"]
    keys = [k for k in assertion if k not in ("level", "requirements", "label")]
    return keys[0] if keys else "assertion"


# --- assertions -----------------------------------------------------------------


def _step(ctx: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ctx:
        raise KeyError(f"unknown step {name!r}")
    return ctx[name]


def _observer(resp: dict[str, Any]) -> dict[str, Any] | None:
    view = resp.get("semantic_view")
    if isinstance(view, dict) and view.get("channel") == "observer":
        return view
    return None


def _history(resp: dict[str, Any]) -> list[dict[str, Any]]:
    hist = resp.get("canonical_history")
    if isinstance(hist, list):
        return hist
    return referee.history_of(_observer(resp))


def _rel_set(view: dict[str, Any] | None) -> list[tuple[str, str]]:
    return sorted((r.get("type"), r.get("target")) for r in (view or {}).get("relationships") or [])


def _canonical_snapshot(view: dict[str, Any] | None) -> dict[str, Any]:
    view = view or {}
    return {
        "object_version": view.get("object_version"),
        "type_version": view.get("type_version"),
        "accepted_state": view.get("accepted_state"),
        "relationships": _rel_set(view),
        "history": referee.history_projection(
            referee.history_of(view), ["effect", "object_version", "relationship_type", "relationship_target"]
        ),
    }


def evaluate_d22_assertion(
    assertion: dict[str, Any],
    ctx: dict[str, Any],
    *,
    relationship_comparison: str,
) -> tuple[bool, str, dict[str, Any] | None]:
    try:
        return _evaluate(assertion, ctx, relationship_comparison)
    except KeyError as exc:
        return False, f"scenario references {exc}", None


def _evaluate(
    a: dict[str, Any], ctx: dict[str, Any], relationship_comparison: str
) -> tuple[bool, str, dict[str, Any] | None]:
    if "outcome_in" in a:
        spec = a["outcome_in"]
        got = _step(ctx, spec["step"]).get("outcome")
        if got not in spec["outcomes"]:
            return False, f"step {spec['step']} outcome {got} not in {spec['outcomes']}", None
        return True, "", {"step": spec["step"], "outcome": got}

    if "outcome_not" in a:
        spec = a["outcome_not"]
        bad = [(s, _step(ctx, s).get("outcome")) for s in spec["steps"] if _step(ctx, s).get("outcome") in spec["outcomes"]]
        if bad:
            return False, f"steps reported a forbidden outcome {spec['outcomes']}: {bad}", None
        return True, "", None

    if "no_disclosure" in a:
        spec = a["no_disclosure"]
        sources = spec["protected_from"] if isinstance(spec["protected_from"], list) else [spec["protected_from"]]
        protected: dict[str, set[Any]] = {"tokens": set(), "strings": set()}
        for src in sources:
            part = referee.protected_values(_observer(_step(ctx, src)))
            protected["tokens"] |= part["tokens"]
            protected["strings"] |= part["strings"]
        for literal in spec.get("protected_literals", []):
            # A protected_literals entry is a version token only when it looks like one
            # (int, or digit-string); other strings are secret-state content, not tokens.
            if isinstance(literal, int) and not isinstance(literal, bool):
                protected["tokens"].add(literal)
            elif isinstance(literal, str) and literal.isdigit():
                protected["tokens"].add(int(literal))
            else:
                protected["strings"].add(literal)
        leaks: list[str] = []
        observed: list[dict[str, Any]] = []
        for s in spec["steps"]:
            resp = _step(ctx, s)
            if resp.get("outcome") == "ACCEPTED":
                return False, f"step {s} was ACCEPTED; disclosure-safe rejection was expected", None
            if "caller_result" not in resp:
                return False, f"step {s}: adapter exposed no caller_result", None
            found = referee.find_disclosures(resp["caller_result"], protected, ctx["_req"][s])
            leaks.extend(f"{s}: {leak}" for leak in found)
            observed.append({"step": s, "outcome": resp.get("outcome"), "caller_result": resp["caller_result"]})
        evidence = {
            "protected": {"tokens": sorted(protected["tokens"]), "strings": sorted(protected["strings"])},
            "observed": observed,
            "leaks": leaks,
        }
        if leaks:
            return False, "protected information disclosed: " + "; ".join(leaks[:12]) + (
                f" (+{len(leaks) - 12} more)" if len(leaks) > 12 else ""
            ), evidence
        return True, "", evidence

    if "invariant" in a:
        spec = a["invariant"]
        steps = spec["steps"]
        base = steps[0]
        base_resp = _step(ctx, base)
        diffs: list[str] = []
        for s in steps[1:]:
            resp = _step(ctx, s)
            if resp.get("outcome") != base_resp.get("outcome"):
                diffs.append(f"outcome {base}={base_resp.get('outcome')} vs {s}={resp.get('outcome')}")
                continue
            if spec.get("content", True):
                left = referee.normalize_for_invariance(base_resp.get("caller_result"), ctx["_req"][base])
                right = referee.normalize_for_invariance(resp.get("caller_result"), ctx["_req"][s])
                diff = referee.first_difference(left, right)
                if diff:
                    diffs.append(f"content {base} vs {s} at {diff}")
        evidence = {"outcomes": {s: _step(ctx, s).get("outcome") for s in steps}}
        if diffs:
            return False, "outcome/content varies with protected information: " + "; ".join(diffs[:8]), evidence
        return True, "", evidence

    if "distinct" in a:
        vals = [_resolve(ref, ctx) for ref in a["distinct"]]
        if any(v is None for v in vals):
            return False, f"missing value among {dict(zip(a['distinct'], vals))}", None
        if len({json.dumps(v) for v in vals}) != len(vals):
            return False, f"values are not pairwise distinct: {dict(zip(a['distinct'], vals))}", None
        return True, "", {"values": vals}

    if "lineage" in a:
        spec = a["lineage"]
        oid = spec["object_id"]
        final = _step(ctx, spec["history"])
        history = _history(final)
        current = (_observer(final) or {}).get("object_version")
        grammar = token_grammar(ctx["caps"])
        exposures: list[tuple[str, str, int]] = []
        prefix_problems: list[str] = []
        final_proj = referee.history_projection(history, ["effect", "object_version"])
        names = [rec["name"] for rec in ctx["_steps"]]
        window = ctx["_steps"][: names.index(spec["history"]) + 1]
        for rec in window:
            req = rec["request"]
            resp = rec["response"]
            if req.get("object_id") != oid:
                continue
            if "caller_result" in resp:
                for path, tok in referee.exposed_versions(resp["caller_result"], supplied_by_requester(rec), grammar):
                    exposures.append((rec["name"], path, tok))
            view = _observer(resp)
            if view and view.get("canonical_identity") == oid:
                ver = referee.as_token(view.get("object_version"))
                if ver is not None:
                    exposures.append((rec["name"], "observer.object_version", ver))
                proj = referee.history_projection(referee.history_of(view), ["effect", "object_version"])
                if proj != final_proj[: len(proj)]:
                    prefix_problems.append(f"history observed at {rec['name']} is not a prefix of the final history")
        problems = referee.lineage_violations(history, current, exposures) + prefix_problems
        evidence = {"history_versions": referee.history_versions(history), "exposed": sorted({t for _, _, t in exposures})}
        if problems:
            return False, "; ".join(problems[:10]), evidence
        return True, "", evidence

    if "history_equals" in a:
        spec = a["history_equals"]
        keys = spec.get("keys", ["effect"])
        got = referee.history_projection(_history(_step(ctx, spec["step"])), keys)
        want = _substitute(spec["expected"], ctx)
        want = [{k: w.get(k) for k in keys} for w in want]
        if got != want:
            return False, f"history {got} != expected {want}", {"history": got}
        return True, "", {"history": got}

    if "history_same_as" in a:
        spec = a["history_same_as"]
        keys = spec.get("keys", ["effect", "object_version"])
        left = referee.history_projection(_history(_step(ctx, spec["step"])), keys)
        right = referee.history_projection(_history(_step(ctx, spec["other"])), keys)
        if left != right:
            return False, f"history at {spec['step']} {left} != at {spec['other']} {right}", None
        return True, "", None

    if "history_unique_versions" in a:
        hist = _history(_step(ctx, a["history_unique_versions"]))
        problems = [p for p in referee.lineage_violations(hist, referee.history_versions(hist)[-1] if hist else None, [])]
        if problems:
            return False, "; ".join(problems), None
        return True, "", None

    if "history_actor_absent" in a:
        spec = a["history_actor_absent"]
        hist = _history(_step(ctx, spec["step"]))
        hits = [i for i, e in enumerate(hist) if e.get("actor") == spec["actor"]]
        if hits:
            return False, f"actor {spec['actor']!r} is recorded in canonical history at entries {hits}", None
        return True, "", None

    if "version_in_history" in a:
        spec = a["version_in_history"]
        val = referee.as_token(_resolve(spec["version"], ctx) if str(spec["version"]).startswith("$") else spec["version"])
        versions = {referee.as_token(v) for v in referee.history_versions(_history(_step(ctx, spec["step"])))}
        present = val in versions
        if present != spec.get("expect", True):
            return False, f"Object Version {val} {'is' if present else 'is not'} a revision in history", None
        return True, "", None

    if "observer_unchanged" in a:
        spec = a["observer_unchanged"]
        before = _canonical_snapshot(_observer(_step(ctx, spec["before"])))
        after = _canonical_snapshot(_observer(_step(ctx, spec["after"])))
        diff = referee.first_difference(before, after)
        if diff:
            return False, f"canonical representation changed between {spec['before']} and {spec['after']}: {diff}", None
        return True, "", None

    if "observer_absent" in a:
        view = _step(ctx, a["observer_absent"]).get("semantic_view")
        if view is not None:
            return False, f"object exists after {a['observer_absent']} (partial or unexpected object)", None
        return True, "", None

    if "observer_field" in a:
        spec = a["observer_field"]
        val = _get_path(_observer(_step(ctx, spec["step"])), spec["path"])
        want = _substitute(spec["equals"], ctx)
        if spec.get("as_token"):
            val, want = referee.as_decimal(val), referee.as_decimal(want)
        if val != want:
            return False, f"observer {spec['path']} at {spec['step']} = {val!r}, expected {want!r}", None
        return True, "", None

    if "relationships_equal" in a:
        spec = a["relationships_equal"]
        got = _rel_set(_observer(_step(ctx, spec["step"])) or _step(ctx, spec["step"]).get("semantic_view"))
        want = sorted((r["type"], r["target"]) for r in spec["expected"])
        if got != want:
            return False, f"relationships {got} != expected {want}", None
        return True, "", None

    if "views_equal" in a:
        spec = a["views_equal"]
        left = _step(ctx, spec["step"]).get("semantic_view") or {}
        right = _step(ctx, spec["other"]).get("semantic_view") or {}
        diffs = []
        for field in spec.get("fields", ["accepted_state", "relationships", "object_version", "type_version"]):
            if field == "relationships":
                lv, rv = _rel_set(left), _rel_set(right)
            elif field == "history":
                keys = ["effect", "object_version", "relationship_type", "relationship_target"]
                lv = referee.history_projection(referee.history_of(left), keys)
                rv = referee.history_projection(referee.history_of(right), keys)
            else:
                lv, rv = left.get(field), right.get(field)
            if lv != rv:
                diffs.append(f"{field}: {lv!r} vs {rv!r}")
        if diffs:
            return False, f"{spec['step']} ({left.get('channel')}) differs from {spec['other']}: " + "; ".join(diffs), None
        return True, "", None

    if "record" in a:
        spec = a["record"]
        return True, "", {"recorded": {k: _resolve(v, ctx) if isinstance(v, str) else v for k, v in spec.items()}}

    if "one_of" in a:
        spec = a["one_of"]
        reasons: list[str] = []
        for branch in spec["branches"]:
            failed = []
            for sub in branch["assert"]:
                ok, msg, _ = _evaluate(sub, ctx, relationship_comparison)
                if not ok:
                    failed.append(msg)
            if not failed:
                return True, "", {"branch": branch["name"]}
            reasons.append(f"{branch['name']}: {'; '.join(failed)}")
        return False, "no permitted branch holds — " + " | ".join(reasons), None

    ok, msg = evaluate_assertion(a, ctx, relationship_comparison=relationship_comparison)
    return ok, msg, None
