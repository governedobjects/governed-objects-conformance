# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Self-attested results bundle.

Any implementer can produce a bundle with the generic runner. A bundle records what was
run (suite version and integrity, targeted spec revision, scenario set hash, the adapter's
self-declaration, the runner environment), what happened (per-scenario results, MUST and
SHOULD separately, NOT APPLICABLE and NOT EXECUTABLE never counted as PASS) and hashes of
the transcripts. It is self-attested: the suite does not certify anything.

``claim_supporting`` is true only for a complete, non-diagnostic run of an unmodified
release of the suite, with a complete adapter declaration, acknowledged fixture
definitions and no FAIL or ADAPTER-ERROR. A pre-release suite version never supports a
claim."""

from __future__ import annotations

import json
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runner import suite
from runner.declaration import claimed_capabilities, version_problem
from runner.privacy import WORKDIR_LABEL, Redactor, environment_block
from runner.d22.engine import (
    ADAPTER_ERROR,
    FAIL,
    NOT_APPLICABLE,
    NOT_EXECUTABLE,
    NOT_EXECUTABLE_ADAPTER,
    NOT_EXECUTABLE_SUITE,
    PASS,
    STATUSES,
)
from runner.d22.report import adapter_counts, scenario_class

BUNDLE_FORMAT = "governed-objects-conformance-results/1"
BUNDLE_FILE = "results-bundle.json"
TRANSCRIPT_FILE = "transcripts/adapter.jsonl"
ATTESTATION = (
    "SELF-ATTESTED. These results were produced and reported by the party that ran the suite. "
    "They are not certification, not endorsement and not a production-readiness finding."
)
DIAGNOSTIC_LABEL = "DIAGNOSTIC RUN: not evidence supporting a conformance claim."


def _summary(scenarios: list[dict[str, Any]], per: dict[str, Any]) -> dict[str, Any]:
    counts = adapter_counts(scenarios, per)
    must: Counter = Counter()
    should: Counter = Counter()
    for s in scenarios:
        (should if scenario_class(s) == "SHOULD" else must)[per[s["id"]]["status"]] += 1
    return {
        "must": {k: must.get(k, 0) for k in STATUSES},
        "should": {k: should.get(k, 0) for k in STATUSES},
        "total": counts["by_status"],
        "must_failures_total": counts["must_failures_total"],
        "mandatory_not_executed": counts["mandatory_not_executed"],
        "mandatory_not_executable": not_executed_mandatory(scenarios, per),
        "results_support_claim": counts["claim_supported"],
        "claim_blockers_in_results": counts["claim_blockers"],
        "adapter_caused_not_executable_blockers": counts["adapter_caused_not_executable_blockers"],
    }


def not_executed_mandatory(scenarios: list[dict[str, Any]], per: dict[str, Any]) -> list[str]:
    """Mandatory (MUST, including conditional MUST) scenarios the suite could not execute,
    for any reason (suite- or adapter-caused; see ``not_executed_mandatory_by_cause``)."""
    return sorted(
        s["id"]
        for s in scenarios
        if scenario_class(s) in ("MUST", "MUST-conditional") and per[s["id"]]["status"] == NOT_EXECUTABLE
    )


def not_executed_mandatory_by_cause(
    scenarios: list[dict[str, Any]], per: dict[str, Any], cause: str
) -> list[str]:
    """Mandatory NOT EXECUTABLE scenarios of one cause (IR-003): ``NOT_EXECUTABLE_SUITE``
    (no executable assertions; compatible with a claim) or ``NOT_EXECUTABLE_ADAPTER`` (a
    missing harness capability or an UNMAPPABLE step; blocks a claim)."""
    return sorted(
        s["id"]
        for s in scenarios
        if scenario_class(s) in ("MUST", "MUST-conditional")
        and per[s["id"]]["status"] == NOT_EXECUTABLE
        and per[s["id"]].get("not_executable_cause") == cause
    )


def not_executed_statement(version: str, suite_ids: list[str], adapter_ids: list[str]) -> str | None:
    """Claim text naming untested mandatory scenarios, worded differently by cause (IR-003):
    suite-caused (no executable assertions yet) versus adapter-caused (the adapter did not
    declare a capability the scenario needs), for example
    "Not executed by suite 0.1.0: D22-CON-001, D22-CS4-003."."""
    parts = []
    if suite_ids:
        parts.append(f"Not executed by suite {version}: {', '.join(suite_ids)}.")
    if adapter_ids:
        parts.append(
            "Not executed because the adapter did not declare a capability the scenario needs: "
            + ", ".join(adapter_ids)
            + "."
        )
    return " ".join(parts) if parts else None


def body_digest(bundle: dict[str, Any]) -> str:
    body = {k: v for k, v in bundle.items() if k != "integrity"}
    return suite.sha256_bytes(suite.canonical_json(body))


def build_bundle(
    *,
    root: Path,
    manifest: dict[str, Any],
    scenarios: list[dict[str, Any]],
    per: dict[str, Any],
    steps: dict[str, Any],
    adapter: dict[str, Any],
    fixtures: dict[str, Any],
    complete_scenario_set: bool,
    diagnostic_requested: bool,
    invocation: list[str],
    include_local_detail: bool = False,
    request_timeout: float | None = None,
    startup_timeout: float | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    redact = Redactor(enabled=not include_local_detail)
    steps = redact.apply(steps)
    per = redact.apply(per)
    adapter = {
        **adapter,
        "command": redact.apply(adapter["command"]),
        "cwd": (adapter["cwd"] if include_local_detail else (WORKDIR_LABEL if adapter["cwd"] else None)),
        "declaration": redact.metadata(adapter["declaration"]),
        "declaration_problems": redact.apply(adapter["declaration_problems"]),
        "capabilities": redact.metadata(adapter["capabilities"]),
    }
    version = suite.read_version(root)
    integrity = suite.check_integrity(root)
    lines: list[str] = []
    line_hashes: dict[str, str] = {}
    for sid in sorted(per):
        line = json.dumps({"scenario": sid, "status": per[sid]["status"], "steps": steps[sid]}, sort_keys=True, default=str)
        lines.append(line)
        line_hashes[sid] = suite.sha256_bytes(line.encode("utf-8"))
    transcript_text = "\n".join(lines) + "\n"

    summary = _summary(scenarios, per)
    blockers: list[str] = []
    if diagnostic_requested:
        blockers.append("diagnostic mode requested")
    if not complete_scenario_set:
        blockers.append("not every Core scenario was selected")
    if adapter["declaration_problems"]:
        blockers.append("adapter declaration incomplete: " + "; ".join(adapter["declaration_problems"]))
    if not fixtures["acknowledged"]:
        blockers.append("adapter did not acknowledge the suite fixture definitions")
    if integrity["status"] != "verified":
        blockers.append(f"suite integrity {integrity['status']}: " + "; ".join(integrity["differences"][:5]))
    if suite.is_prerelease(version):
        blockers.append(f"suite version {version} is a pre-release")
    impl = adapter["declaration"]["implementation"]
    problem = version_problem(impl.get("version"))
    if problem:
        blockers.append(problem)
    if summary["claim_blockers_in_results"]:
        blockers.append("FAIL or ADAPTER-ERROR results: " + ", ".join(summary["claim_blockers_in_results"]))
    if summary["adapter_caused_not_executable_blockers"]:
        blockers.append(
            "mandatory scenarios not executed because the adapter did not declare a required capability: "
            + ", ".join(summary["adapter_caused_not_executable_blockers"])
        )
    claim_supporting = not blockers
    not_executed_suite = not_executed_mandatory_by_cause(scenarios, per, NOT_EXECUTABLE_SUITE)
    not_executed_adapter = not_executed_mandatory_by_cause(scenarios, per, NOT_EXECUTABLE_ADAPTER)
    statement = not_executed_statement(version, not_executed_suite, not_executed_adapter)
    claimed_caps = claimed_capabilities(adapter["capabilities"])
    caps_clause = "Conditional capabilities claimed: " + (", ".join(claimed_caps) if claimed_caps else "none") + "."
    claim_text = (
        f"{impl['name']} {impl['version']} passes the Governed Objects Conformance Suite {version} for "
        f"{manifest['spec_version']} {manifest['spec_revision_label']} {manifest['profile_scope']} "
        "(self-attested; not certified)." + (f" {statement}" if statement else "") + f" {caps_clause}"
        if claim_supporting
        else None
    )
    bundle: dict[str, Any] = {
        "bundle_format": BUNDLE_FORMAT,
        "attestation": {"kind": "self-attested", "certification": "none", "statement": ATTESTATION},
        "mode": "diagnostic" if (diagnostic_requested or not complete_scenario_set) else "full",
        "claim_supporting": claim_supporting,
        "claim_support_blockers": blockers,
        "label": None if claim_supporting else DIAGNOSTIC_LABEL if (diagnostic_requested or not complete_scenario_set) else
        "NOT CLAIM-SUPPORTING: see claim_support_blockers.",
        "claim_text": claim_text,
        "not_executed_statement": statement,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite": {
            "name": suite.read_suite(root)["name"],
            "version": version,
            "version_source": "VERSION",
            "prerelease": suite.is_prerelease(version),
            "integrity": integrity,
        },
        "spec": {
            "version": manifest["spec_version"],
            "revision": manifest["spec_revision_label"],
            "profile_scope": manifest["profile_scope"],
        },
        "scenario_manifest": {
            "path": manifest["manifest_path"],
            "scenario_count": len(scenarios),
            **{f"scenario_set_{k}": v for k, v in suite.scenario_set_digest(root, manifest).items()},
        },
        "fixtures": fixtures,
        "adapter": {
            "command": adapter["command"],
            "working_directory": adapter["cwd"],
            "declaration": adapter["declaration"],
            "declaration_valid": not adapter["declaration_problems"],
            "declaration_problems": adapter["declaration_problems"],
            "capabilities_verbatim": adapter["capabilities"],
        },
        "environment": environment_block(
            suite_version=version,
            local_detail=include_local_detail,
            invocation=invocation,
            platform_string=platform.platform(),
        ),
        "run_options": {
            "request_timeout_seconds": request_timeout,
            "startup_timeout_seconds": startup_timeout,
            "local_detail_included": include_local_detail,
        },
        "summary": summary,
        "results": {
            sid: {
                "class": scenario_class(next(s for s in scenarios if s["id"] == sid)),
                "status": per[sid]["status"],
                "must_failures": per[sid]["must_failures"],
                "should_deviations": per[sid]["should_deviations"],
                "notes": per[sid]["notes"],
            }
            for sid in sorted(per)
        },
        "transcripts": {"file": TRANSCRIPT_FILE, "sha256": suite.sha256_bytes(transcript_text.encode("utf-8")), "scenario_line_sha256": line_hashes},
    }
    bundle["integrity"] = {"algorithm": "sha256", "bundle_body_sha256": body_digest(bundle)}
    return bundle, transcript_text, per


def write_bundle(bundle: dict[str, Any], transcript_text: str, out: Path) -> None:
    (out / "transcripts").mkdir(parents=True, exist_ok=True)
    (out / TRANSCRIPT_FILE).write_text(transcript_text, encoding="utf-8")
    (out / BUNDLE_FILE).write_text(json.dumps(bundle, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def verify_bundle(out: Path, root: Path) -> list[str]:
    """Return the list of problems; empty means the bundle is internally consistent and
    was produced by this exact, unmodified suite."""
    problems: list[str] = []
    try:
        bundle = json.loads((out / BUNDLE_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read {BUNDLE_FILE}: {exc}"]
    if bundle.get("bundle_format") != BUNDLE_FORMAT:
        problems.append(f"unknown bundle_format {bundle.get('bundle_format')!r}")
    if bundle.get("integrity", {}).get("bundle_body_sha256") != body_digest(bundle):
        problems.append("bundle body hash mismatch: the bundle was edited after it was written")
    try:
        raw = (out / bundle["transcripts"]["file"]).read_bytes()
    except (OSError, KeyError) as exc:
        return problems + [f"cannot read transcripts: {exc}"]
    if suite.sha256_bytes(raw) != bundle["transcripts"]["sha256"]:
        problems.append("transcript file hash mismatch")
    seen: dict[str, str] = {}
    for line in raw.decode("utf-8").splitlines():
        row = json.loads(line)
        seen[row["scenario"]] = row["status"]
        if suite.sha256_bytes(line.encode("utf-8")) != bundle["transcripts"]["scenario_line_sha256"].get(row["scenario"]):
            problems.append(f"transcript line hash mismatch for {row['scenario']}")
    results = bundle.get("results", {})
    if set(seen) != set(results):
        problems.append("transcript scenarios differ from result scenarios")
    for sid, res in results.items():
        if seen.get(sid) != res["status"]:
            problems.append(f"{sid}: result status {res['status']} differs from transcript status {seen.get(sid)}")
    recomputed: Counter = Counter(r["status"] for r in results.values())
    if {k: recomputed.get(k, 0) for k in STATUSES} != bundle["summary"]["total"]:
        problems.append("summary totals do not match per-scenario results")
    if bundle.get("claim_supporting"):
        if bundle.get("mode") != "full" or bundle.get("claim_support_blockers"):
            problems.append("claim_supporting is true although the bundle records blockers or a non-full mode")
        if any(r["status"] in (FAIL, ADAPTER_ERROR) for r in results.values()):
            problems.append("claim_supporting is true although results contain FAIL or ADAPTER-ERROR")
        if bundle.get("summary", {}).get("adapter_caused_not_executable_blockers"):
            problems.append(
                "claim_supporting is true although a mandatory scenario was not executed because the "
                "adapter did not declare a required capability"
            )
        if suite.is_prerelease(bundle["suite"]["version"]):
            problems.append("claim_supporting is true although the suite version is a pre-release")
        impl_version = bundle["adapter"]["declaration"]["implementation"].get("version")
        if version_problem(impl_version):
            problems.append("claim_supporting is true although " + version_problem(impl_version))
    unexecuted = bundle.get("summary", {}).get("mandatory_not_executable", [])
    statement = bundle.get("not_executed_statement")
    if unexecuted and not all(i in (statement or "") for i in unexecuted):
        problems.append("mandatory scenarios were not executed but the bundle does not name them")
    if bundle.get("claim_supporting") and unexecuted and not all(i in (bundle.get("claim_text") or "") for i in unexecuted):
        problems.append("claim text does not name the mandatory scenarios that were not executed")
    # Same suite? Compare with the live suite checkout.
    live = suite.check_integrity(root)
    if bundle["suite"]["version"] != suite.read_version(root):
        problems.append(f"bundle suite version {bundle['suite']['version']} != this suite {suite.read_version(root)}")
    if bundle["suite"]["integrity"]["live_sha256"] != live["live_sha256"]:
        problems.append("suite files differ from those that produced the bundle (suite hash mismatch)")
    from runner.revisions import load_manifest

    manifest = load_manifest(root, bundle["spec"]["revision"])
    if bundle["scenario_manifest"]["scenario_set_sha256"] != suite.scenario_set_digest(root, manifest)["sha256"]:
        problems.append("scenario set differs from the one that produced the bundle")
    return problems


__all__ = ["build_bundle", "write_bundle", "verify_bundle", "BUNDLE_FILE", "PASS", "NOT_APPLICABLE", "NOT_EXECUTABLE"]
