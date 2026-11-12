# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Draft 2.2 Core target entry point (dispatched from ``python -m runner``)."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import Any

from runner import suite
from runner.adapter_client import AdapterClient, AdapterError
from runner.adapter_client import DEFAULT_REQUEST_TIMEOUT, DEFAULT_STARTUP_TIMEOUT
from runner.bundle import build_bundle, write_bundle
from runner.d22.engine import ADAPTER_ERROR, ScenarioOutcome, load_draft22_scenarios, run_d22_scenario
from runner.d22.report import write_reports
from runner.declaration import extract_declaration

RESULT_KEY = "adapter"


def run_draft22(repo_root: Path, manifest: dict[str, Any], args: argparse.Namespace) -> Path:
    all_scenarios = load_draft22_scenarios(repo_root, manifest)
    scenarios = all_scenarios
    if getattr(args, "scenario", None):
        wanted = set(args.scenario)
        unknown = wanted - {s["id"] for s in all_scenarios}
        if unknown:
            raise SystemExit(f"unknown scenario ids: {sorted(unknown)}")
        scenarios = [s for s in all_scenarios if s["id"] in wanted]
    complete = len(scenarios) == len(all_scenarios)
    diagnostic = bool(getattr(args, "diagnostic", False))
    output_dir = Path(args.output_dir).resolve() if args.output_dir else Path.cwd() / "conformance-results"

    fixtures, fixtures_sha = suite.load_fixtures(repo_root)
    command = shlex.split(args.adapter_command)
    request_timeout = float(getattr(args, "request_timeout", DEFAULT_REQUEST_TIMEOUT))
    startup_timeout = float(getattr(args, "startup_timeout", DEFAULT_STARTUP_TIMEOUT))
    include_local_detail = bool(getattr(args, "include_local_detail", False))
    cwd = Path(args.adapter_cwd).resolve() if args.adapter_cwd else None
    print(f"Suite version: {suite.read_version(repo_root)}")
    print(f"Spec revision: {manifest['spec_revision']}")
    print(f"Scenarios selected: {len(scenarios)} of {len(all_scenarios)}")
    print(f"Output directory: {output_dir}")
    print(f"Timeouts: {request_timeout:g} s per request, {startup_timeout:g} s for the first response")

    try:
        client = AdapterClient(RESULT_KEY, command, cwd=cwd, request_timeout=request_timeout, startup_timeout=startup_timeout)
    except AdapterError as exc:
        raise SystemExit(str(exc)) from None
    per: dict[str, Any] = {}
    steps: dict[str, Any] = {}
    try:
        try:
            caps = client.read_capabilities()
            declaration, problems = extract_declaration(caps, manifest)
            if problems and not diagnostic and not getattr(args, "scenario", None):
                raise SystemExit("adapter declaration incomplete (use --diagnostic to run anyway):\n  " + "\n  ".join(problems))
            client.request({"op": "reset"})
            ack = client.define_fixtures(fixtures, fixtures_sha)
            acknowledged = ack.get("fixtures_sha256") == fixtures_sha and ack.get("outcome") == "ACCEPTED"
            if not acknowledged and not diagnostic and not getattr(args, "scenario", None):
                raise SystemExit(
                    "adapter did not acknowledge the suite fixture definitions (define_fixture_types must echo "
                    f"fixtures_sha256 {fixtures_sha}; got {ack.get('fixtures_sha256')!r})"
                )
            comparison = manifest.get("relationship_comparison", "set_with_uniqueness")
            dead_reason: str | None = None
            failed_starts = 0
            for scenario in scenarios:
                sid = scenario["id"]
                if failed_starts >= 2:
                    # The adapter could not be brought back twice in a row: stop retrying.
                    outcome = ScenarioOutcome(sid, ADAPTER_ERROR)
                    outcome.notes.append(f"adapter not restarted after repeated failures: {dead_reason}")
                    per[sid], steps[sid] = outcome.as_dict(), outcome.steps
                    print(f"[{RESULT_KEY}] {sid}: {outcome.status}")
                    continue
                try:
                    if dead_reason is not None or not client.alive:
                        # A previous request timed out (or the adapter died): start it again.
                        client.restart()
                        client.read_capabilities()
                        dead_reason = None
                        failed_starts = 0
                    client.request({"op": "reset"})
                    ack = client.define_fixtures(fixtures, fixtures_sha)
                    if ack.get("fixtures_sha256") != fixtures_sha:
                        acknowledged = False
                    outcome = run_d22_scenario(client, scenario, relationship_comparison=comparison)
                except AdapterError as exc:
                    dead_reason = str(exc)
                    failed_starts += 1 if not client.alive else 0
                    outcome = ScenarioOutcome(sid, ADAPTER_ERROR)
                    outcome.notes.append(f"adapter unavailable before the scenario could run: {exc}")
                if not client.alive:
                    dead_reason = dead_reason or "adapter process ended"
                per[sid] = outcome.as_dict()
                steps[sid] = outcome.steps
                print(f"[{RESULT_KEY}] {sid}: {outcome.status}")
        except AdapterError as exc:
            raise SystemExit(f"adapter failed: {exc}") from None
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass

    bundle, transcript_text, per = build_bundle(
        root=repo_root,
        manifest=manifest,
        scenarios=scenarios,
        per=per,
        steps=steps,
        adapter={
            "command": command,
            "cwd": str(cwd) if cwd else None,
            "declaration": declaration,
            "declaration_problems": problems,
            "capabilities": caps,
        },
        fixtures={
            "sha256": fixtures_sha,
            "fixtures_version": fixtures.get("fixtures_version"),
            "types": sorted(fixtures["types"]),
            "acknowledged": acknowledged,
        },
        complete_scenario_set=complete,
        diagnostic_requested=diagnostic,
        invocation=list(sys.argv),
        include_local_detail=include_local_detail,
        request_timeout=request_timeout,
        startup_timeout=startup_timeout,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_bundle(bundle, transcript_text, output_dir)
    write_reports(repo_root, manifest, scenarios, {RESULT_KEY: per}, bundle, output_dir)
    print(f"Results bundle: {output_dir / 'results-bundle.json'}")
    if include_local_detail:
        from runner.privacy import LOCAL_DETAIL_WARNING

        print(LOCAL_DETAIL_WARNING)
    print(f"Claim supporting: {bundle['claim_supporting']}" + ("" if bundle["claim_supporting"] else f" ({'; '.join(bundle['claim_support_blockers'])})"))
    return output_dir
