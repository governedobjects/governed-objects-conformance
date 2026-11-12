# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Human-readable reports (written only under --output-dir, next to the results bundle)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from runner.d22.engine import (
    ADAPTER_ERROR,
    FAIL,
    NOT_APPLICABLE,
    NOT_EXECUTABLE,
    NOT_EXECUTABLE_ADAPTER,
    PASS,
    STATUSES,
    is_conditional,
    load_inherited_map,
)

CLAIM_SCOPE = (
    "Where 'Claim supported' is yes, the implementation passed all mandatory Core scenarios of the targeted specification revision "
    "executable on this conformance surface. Conditional, not-applicable, SHOULD and not-executable cases "
    "are reported separately. This is not certification, a production-readiness finding, a claim about "
    "every implementation API, a Portable Restoration Continuity claim, an interoperability or wire-format "
    "claim, or evidence of thread safety."
)
ALIASING_LIMIT = (
    "The process-boundary conformance harness does not prove absence of in-process mutable aliases "
    "on all implementation APIs."
)


def scenario_class(s: dict[str, Any]) -> str:
    if s.get("modality") == "SHOULD":
        return "SHOULD"
    return "MUST-conditional" if is_conditional(s) else "MUST"


def inventory_counts(scenarios: list[dict[str, Any]]) -> dict[str, int]:
    c = Counter(scenario_class(s) for s in scenarios)
    return {
        "total": len(scenarios),
        "must_unconditional": c["MUST"],
        "must_conditional": c["MUST-conditional"],
        "should": c["SHOULD"],
        "inherited": sum(1 for s in scenarios if s["origin"] == "inherited"),
        "new_draft2.2": sum(1 for s in scenarios if s["origin"] == "draft2.2"),
    }


def adapter_counts(scenarios: list[dict[str, Any]], per: dict[str, Any]) -> dict[str, Any]:
    by_status = Counter(per[s["id"]]["status"] for s in scenarios)
    by_class: dict[str, Counter] = {}
    for s in scenarios:
        by_class.setdefault(scenario_class(s), Counter())[per[s["id"]]["status"]] += 1
    mandatory = [s for s in scenarios if scenario_class(s) == "MUST"]
    # Every mandatory scenario (unconditional or conditional) that is NOT EXECUTABLE because the
    # adapter did not declare a harness capability blocks a claim (IR-003). Suite-caused NOT
    # EXECUTABLE (a scenario with no executable assertions) does not.
    mandatory_incl_conditional = [s for s in scenarios if scenario_class(s) in ("MUST", "MUST-conditional")]
    adapter_blocked = [
        s["id"]
        for s in mandatory_incl_conditional
        if per[s["id"]]["status"] == NOT_EXECUTABLE and per[s["id"]].get("not_executable_cause") == NOT_EXECUTABLE_ADAPTER
    ]
    claim_blockers = [s["id"] for s in scenarios if per[s["id"]]["status"] in (FAIL, ADAPTER_ERROR)]
    mandatory_not_run = [s["id"] for s in mandatory if per[s["id"]]["status"] in (NOT_EXECUTABLE, NOT_APPLICABLE)]
    return {
        "by_status": {k: by_status.get(k, 0) for k in STATUSES},
        "by_class": {k: {st: v.get(st, 0) for st in STATUSES} for k, v in sorted(by_class.items())},
        "must_failures_total": sum(len(per[s["id"]]["must_failures"]) for s in scenarios),
        "claim_blockers": claim_blockers,
        "adapter_caused_not_executable_blockers": adapter_blocked,
        "mandatory_not_executed": mandatory_not_run,
        "claim_supported": not claim_blockers and not adapter_blocked,
    }


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def write_reports(
    repo_root: Path,
    manifest: dict[str, Any],
    scenarios: list[dict[str, Any]],
    results: dict[str, dict[str, Any]],
    bundle: dict[str, Any],
    output_dir: Path,
) -> None:
    """Human-readable reports next to results-bundle.json (the machine-readable record)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    inv = inventory_counts(scenarios)
    counts = {name: adapter_counts(scenarios, per) for name, per in results.items()}
    requirements = json.loads((repo_root / manifest["requirements_path"]).read_text(encoding="utf-8"))
    inherited_map = load_inherited_map(repo_root, manifest)
    _write_latest_md(output_dir, manifest, scenarios, results, counts, inv, bundle)
    _write_coverage(output_dir, requirements, scenarios, results)
    _write_scenario_map(output_dir, scenarios, inherited_map, manifest)
    _write_disclosure(output_dir, scenarios, results)


def _write_latest_md(output_dir, manifest, scenarios, results, counts, inv, bundle) -> None:
    impl = bundle["adapter"]["declaration"]["implementation"]
    lines = [
        f"# {bundle['spec']['profile_scope']} conformance results: {bundle['spec']['version']} {bundle['spec']['revision']}",
        "",
        f"**{bundle['attestation']['statement']}**",
        "",
    ]
    if bundle.get("run_options", {}).get("local_detail_included"):
        from runner.privacy import LOCAL_DETAIL_WARNING

        lines += [f"**{LOCAL_DETAIL_WARNING}**", ""]
    if bundle["label"]:
        lines += [f"**{bundle['label']}**", ""]
    lines += [
        f"- Suite: `{bundle['suite']['name']}` version `{bundle['suite']['version']}` "
        f"(integrity: {bundle['suite']['integrity']['status']})",
        f"- Specification: `{bundle['spec']['version']}` revision `{bundle['spec']['revision']}`, "
        f"profile scope {bundle['spec']['profile_scope']} (Portable Restoration Continuity is not in scope)",
        f"- Implementation (self-declared): `{impl['name']}` `{impl['version']}`",
        f"- Generated: {bundle['generated_at']}",
        f"- Claim supporting: {'yes' if bundle['claim_supporting'] else 'NO'}",
    ]
    lines += [f"  - blocker: {b}" for b in bundle["claim_support_blockers"]]
    if bundle["claim_text"]:
        lines += ["", f"Claim text: {bundle['claim_text']}"]
    if bundle.get("not_executed_statement"):
        # Required whenever mandatory scenarios could not be executed, claim or not.
        lines += ["", f"**{bundle['not_executed_statement']}**"]
    lines += [
        "",
        "## Claim scope",
        "",
        CLAIM_SCOPE,
        "",
        "Limitations:",
        "",
    ]
    lines += [f"- {lim}" for lim in manifest.get("claim_limitations", []) + [ALIASING_LIMIT]]
    lines += [
        "",
        "## Scenario inventory",
        "",
        f"Total {inv['total']}: {inv['must_unconditional']} MUST (unconditional), "
        f"{inv['must_conditional']} MUST (conditional), {inv['should']} SHOULD. "
        f"{inv['inherited']} inherited, {inv['new_draft2.2']} new for Draft 2.2.",
        "",
        "## Counts",
        "",
        "| Adapter | " + " | ".join(STATUSES) + " | Claim supported |",
        "| --- | " + " | ".join("---" for _ in STATUSES) + " | --- |",
    ]
    for name, c in counts.items():
        lines.append(
            f"| {name} | " + " | ".join(str(c["by_status"][s]) for s in STATUSES) + f" | {'yes' if c['claim_supported'] else 'no'} |"
        )
    lines += ["", "By scenario class:", ""]
    for name, c in counts.items():
        for cls, row in c["by_class"].items():
            nonzero = ", ".join(f"{k} {v}" for k, v in row.items() if v)
            lines.append(f"- {name} {cls}: {nonzero}")
    lines += ["", "## Results", "", "| Scenario | Class | " + " | ".join(results) + " |", "| --- | --- | " + " | ".join("---" for _ in results) + " |"]
    for s in scenarios:
        lines.append(
            f"| {s['id']} | {scenario_class(s)} | " + " | ".join(results[n][s["id"]]["status"] for n in results) + " |"
        )
    lines += ["", "## Details", ""]
    for s in scenarios:
        for n in results:
            r = results[n][s["id"]]
            if r["status"] == PASS and not r["notes"]:
                continue
            lines.append(f"### {s['id']} — {n}: {r['status']}")
            lines.append("")
            for f in r["must_failures"]:
                lines.append(f"- MUST: {_cell(f)}")
            for d in r["should_deviations"]:
                lines.append(f"- SHOULD: {_cell(d)}")
            for note in r["notes"]:
                lines.append(f"- note: {_cell(note)}")
            for ev in r.get("evidence", []):
                if "branch" in ev:
                    lines.append(f"- conditional branch taken ({ev['assertion']}): {ev['branch']}")
            lines.append("")
    (output_dir / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_coverage(output_dir, requirements, scenarios, results) -> None:
    by_req: dict[str, list[str]] = {}
    for s in scenarios:
        for rid in s.get("requirements", []):
            by_req.setdefault(rid, []).append(s["id"])
    lines = [
        "# Draft 2.2 Core requirement coverage",
        "",
        f"{len(requirements['requirements'])} Core requirements "
        f"({sum(1 for r in requirements['requirements'] if r['level'] == 'MUST')} MUST, "
        f"{sum(1 for r in requirements['requirements'] if r['level'] == 'SHOULD')} SHOULD). "
        "Optional-profile requirements are out of scope.",
        "",
        "| Requirement | Level | Spec change | Coverage | Scenarios | " + " | ".join(results) + " | Note |",
        "| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in results) + " | --- |",
    ]
    classes = {s["id"]: scenario_class(s) for s in scenarios}
    dispositions: Counter = Counter()
    for req in requirements["requirements"]:
        sids = by_req.get(req["id"], [])
        cells = []
        for n in results:
            c = Counter(results[n][sid]["status"] for sid in sids)
            cells.append(", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "—")
        if req.get("coverage"):
            coverage = req["coverage"]
        elif not sids:
            coverage = "none"
        elif any(classes[sid] == "MUST" for sid in sids):
            coverage = "direct scenario"
        elif all(classes[sid] == "SHOULD" for sid in sids):
            coverage = "direct scenario (SHOULD)"
        else:
            coverage = "conditional scenario"
        dispositions[coverage] += 1
        lines.append(
            f"| {req['id']} | {req['level']} | {req['spec_status']} | {coverage} | {', '.join(sids) or '—'} | "
            + " | ".join(cells)
            + f" | {_cell(req.get('note', ''))} |"
        )
    uncovered = [r["id"] for r in requirements["requirements"] if not by_req.get(r["id"]) and not r.get("coverage")]
    lines += [
        "",
        "Dispositions: " + ", ".join(f"{k} {v}" for k, v in sorted(dispositions.items())),
        "",
        f"Requirements with no scenario and no recorded disposition: {', '.join(uncovered) or 'none'}",
    ]
    (output_dir / "requirement-coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_scenario_map(output_dir, scenarios, inherited_map, manifest) -> None:
    lines = [
        "# Draft 2.2 scenario revision map",
        "",
        "## Inherited scenarios",
        "",
        "Dispositions: unchanged, clarified, superseded, conditionality-changed.",
        "",
        "| Scenario | Disposition | Draft 2.2 requirements | Note |",
        "| --- | --- | --- | --- |",
    ]
    for sid, entry in sorted(inherited_map["scenarios"].items()):
        lines.append(
            f"| {sid} | {entry['disposition']}"
            + (f" → {entry['superseded_by']}" if entry.get("superseded_by") else "")
            + f" | {', '.join(entry.get('draft22_requirements', []))} | {_cell(entry.get('note', ''))} |"
        )
    c = Counter(e["disposition"] for e in inherited_map["scenarios"].values())
    lines += ["", "Totals: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())), ""]
    lines += ["## New Draft 2.2 scenarios", "", "| Scenario | CS | Class | Trigger | Requirements |", "| --- | --- | --- | --- | --- |"]
    for s in scenarios:
        if s["origin"] != "draft2.2":
            continue
        lines.append(
            f"| {s['id']} | {', '.join(s.get('cs', []))} | {scenario_class(s)} | "
            f"{_cell((s.get('applicability') or {}).get('trigger') or 'unconditional')} | {', '.join(s.get('requirements', []))} |"
        )
    (output_dir / "scenario-map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_disclosure(output_dir, scenarios, results) -> None:
    lines = [
        "# AUTH-DISCLOSE-001 evidence",
        "",
        "Raw caller-visible results of non-accepted requests, with the protected values the referee searched for. "
        "Values are shown exactly as returned: an absent key, `null`, an empty container and a value are "
        "distinct observations.",
        "",
    ]
    for s in scenarios:
        if "AUTH-DISCLOSE-001" not in s.get("requirements", []):
            continue
        lines.append(f"## {s['id']} — {s.get('title', '')}")
        lines.append("")
        for n in results:
            r = results[n][s["id"]]
            lines.append(f"### {n}: {r['status']}")
            lines.append("")
            for ev in r.get("evidence", []):
                if "observed" not in ev:
                    continue
                lines.append(f"Protected tokens {ev['protected']['tokens']}, strings {ev['protected']['strings']}.")
                lines.append("")
                for obs in ev["observed"]:
                    raw = json.dumps(obs["caller_result"], sort_keys=True)
                    if len(raw) > 700:
                        raw = raw[:700] + " …"
                    lines.append(f"- `{obs['step']}` {obs['outcome']}: `{raw}`")
                if ev["leaks"]:
                    lines.append("")
                    lines.append("Leaks:")
                    lines += [f"- {leak}" for leak in ev["leaks"]]
                lines.append("")
    (output_dir / "disclosure-evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
