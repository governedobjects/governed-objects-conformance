# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Draft 2.2 harness self-tests: referee units and negative fixtures.

Negative fixtures run the real scenario files against ``FakeClient`` with one
injected defect each; the scenario built to catch that defect must FAIL."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_runtime import FakeClient  # noqa: E402
from runner.d22 import referee  # noqa: E402
from runner.d22.engine import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    NOT_EXECUTABLE,
    PASS,
    SHOULD_DEVIATION,
    load_draft22_scenarios,
    run_d22_scenario,
)
from runner.revisions import load_manifest  # noqa: E402

MANIFEST = load_manifest(ROOT, "draft2.2")
SCENARIOS = {s["id"]: s for s in load_draft22_scenarios(ROOT, MANIFEST)}


def run(sid: str, faults: set[str] | None = None):
    client = FakeClient(faults)
    client.request({"op": "reset"})
    return run_d22_scenario(client, SCENARIOS[sid])


class RefereeUnitTests(unittest.TestCase):
    VIEW = {
        "channel": "observer",
        "object_version": 7300444,
        "accepted_state": {"title": "secret-title", "status": "active"},
        "relationships": [{"type": "depends_on", "target": "p-secret"}],
        "canonical_history_summary": [{"object_version": 7300421}, {"object_version": 7300444}],
    }

    def test_version_leaked_on_denial_is_detected(self):
        leaks = referee.find_disclosures(
            {"outcome": "denied", "actual_version": 7300444}, referee.protected_values(self.VIEW), {"expected_version": 1}
        )
        self.assertTrue(any("7300444" in leak for leak in leaks))

    def test_version_in_error_text_is_detected(self):
        leaks = referee.find_disclosures(
            {"reason": "stale: current is 7300421"}, referee.protected_values(self.VIEW), {}
        )
        self.assertTrue(leaks)

    def test_state_and_relationship_values_are_detected(self):
        leaks = referee.find_disclosures(
            {"details": {"state": "active", "edge": "p-secret"}}, referee.protected_values(self.VIEW), {}
        )
        self.assertEqual(len(leaks), 2)

    def test_requester_supplied_values_are_not_protected(self):
        leaks = referee.find_disclosures(
            {"expected_version": 7300444, "object_id": "x"},
            referee.protected_values(self.VIEW),
            {"request": {"expected_version": 7300444, "object_id": "x"}},
        )
        self.assertEqual(leaks, [])

    def test_absent_null_empty_and_value_are_distinct(self):
        c = {"a": None, "b": [], "c": 5}
        self.assertEqual(
            [referee.fidelity(c, k) for k in ("missing", "a", "b", "c")], ["absent", "null", "empty", "value"]
        )

    def test_token_oracle_content_difference_is_detected(self):
        stale = referee.normalize_for_invariance({"outcome": "conflict", "actual": 4}, {"expected_version": 2})
        current = referee.normalize_for_invariance({"outcome": "conflict", "actual": None}, {"expected_version": 4})
        self.assertIsNotNone(referee.first_difference(stale, current))

    def test_requester_echo_against_nothing_is_not_a_difference(self):
        with_token = referee.normalize_for_invariance({"expected_version": 2}, {"expected_version": 2})
        without = referee.normalize_for_invariance({"expected_version": None}, {})
        self.assertIsNone(referee.first_difference(with_token, without))

    def test_duplicate_version_in_history(self):
        problems = referee.lineage_violations([{"object_version": 1}, {"object_version": 2}, {"object_version": 1}], 1, [])
        self.assertTrue(any("identifies history entries" in p for p in problems))

    def test_revision_missing_a_version(self):
        problems = referee.lineage_violations([{"object_version": 1}, {"object_version": None}], None, [])
        self.assertTrue(any("no Object Version" in p for p in problems))

    def test_exposed_version_outside_lineage(self):
        problems = referee.lineage_violations([{"object_version": 1}], 1, [("step", "$.version", 9)])
        self.assertTrue(any("no revision in history" in p for p in problems))

    def test_exposed_versions_ignore_type_version_and_out_of_grammar_values(self):
        found = referee.exposed_versions(
            {"type_version": 3, "Version": 0, "ObjectVersion": 5, "resulting_version": 6}, {}, "^[1-9][0-9]*$"
        )
        self.assertEqual(sorted(t for _, t in found), [5, 6])


class ScenarioInventoryTests(unittest.TestCase):
    def test_inherited_scenarios_are_all_mapped(self):
        inherited = [s for s in SCENARIOS.values() if s["origin"] == "inherited"]
        self.assertEqual(len(inherited), 46)
        self.assertNotIn("C-TYPE-003", SCENARIOS)

    def test_cs2s_is_should(self):
        for sid in ("D22-CS2S-UPDATE", "D22-CS2S-TRANSITION", "D22-CS2S-RELADD", "D22-CS2S-RELREMOVE"):
            self.assertEqual(SCENARIOS[sid]["modality"], "SHOULD")


class CleanFakeTests(unittest.TestCase):
    def test_clean_fake_passes_every_executable_draft22_scenario(self):
        expected_gated = {
            "D22-CS4-002": NOT_APPLICABLE,
            "D22-CS5-001": NOT_APPLICABLE,
            "D22-CS7B-001": NOT_APPLICABLE,
            "D22-CS4-003": NOT_EXECUTABLE,
            "D22-CON-001": NOT_EXECUTABLE,
        }
        for sid, scenario in SCENARIOS.items():
            if scenario["origin"] != "draft2.2":
                continue
            with self.subTest(sid=sid):
                out = run(sid)
                self.assertEqual(out.status, expected_gated.get(sid, PASS), out.must_failures + out.notes)


class NegativeFixtureTests(unittest.TestCase):
    def assertFails(self, sid: str, fault: str, needle: str):
        out = run(sid, {fault})
        self.assertEqual(out.status, FAIL, f"{sid} with {fault}: {out.notes}")
        self.assertTrue(any(needle in f for f in out.must_failures), out.must_failures)

    def test_version_leaked_on_denial(self):
        for sid in ("D22-CS2-UPDATE", "D22-CS2R-001", "D22-CS2-WNR", "D22-CS2-RESTORED"):
            with self.subTest(sid=sid):
                self.assertFails(sid, "leak_version", "protected information disclosed")

    def test_token_oracle(self):
        for sid in ("D22-CS2-UPDATE", "D22-CS2-TRANSITION", "D22-CS2-RELADD", "D22-CS2-RELREMOVE"):
            with self.subTest(sid=sid):
                self.assertFails(sid, "token_oracle", "varies with protected information")

    def test_token_oracle_is_only_a_should_deviation_for_a_reader(self):
        out = run("D22-CS2S-UPDATE", {"token_oracle"})
        self.assertEqual(out.status, SHOULD_DEVIATION)
        self.assertEqual(out.must_failures, [])

    def test_duplicate_version_in_history(self):
        self.assertFails("D22-CS1-001", "reuse_version", "not pairwise distinct")
        self.assertFails("D22-CS1-002", "reuse_version", "not pairwise distinct")

    def test_revision_missing_a_version(self):
        self.assertFails("D22-CS7-001", "missing_version", "no Object Version")

    def test_timestamp_order_misuse(self):
        self.assertFails("D22-CS4-001", "timestamp_order", "history")

    def test_duplicate_add_advancing_the_version(self):
        self.assertFails("D22-CS7-001", "dup_add_advances", "history")

    def test_restoration_appending_a_revision(self):
        self.assertFails("D22-CS8-001", "restore_appends", "history")


if __name__ == "__main__":
    unittest.main()
