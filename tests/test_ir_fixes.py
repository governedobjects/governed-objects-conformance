# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Self-tests for the independent-review fixes (IR-001, IR-003): Object Versions are
opaque JSON scalars compared only by equality, and only a suite-caused NOT EXECUTABLE
(no executable assertions) is compatible with a claim."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_generic_runner import CONCRETE_VERSION, _copy_suite, _run  # noqa: E402

STRTOKEN = f"{sys.executable} {ROOT / 'tests' / 'fake_adapter_strtoken.py'}"
MINCAPS = f"{sys.executable} {ROOT / 'tests' / 'fake_adapter_mincaps.py'}"


class OpaqueTokenTests(unittest.TestCase):
    """IR-001: the suite must not assume decimal-integer Object Version tokens."""

    def test_non_integer_tokens_pass_every_unconditional_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite")
            bundle = _run(root, Path(tmp) / "out", command=STRTOKEN, diagnostic=True)
            self.assertEqual(bundle["summary"]["total"]["FAIL"], 0, bundle["results"])
            self.assertEqual(bundle["summary"]["total"]["ADAPTER-ERROR"], 0, bundle["results"])
            self.assertGreater(bundle["summary"]["total"]["PASS"], 0)

    def test_leak_detection_works_for_non_integer_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite")
            bundle = _run(
                root, Path(tmp) / "out", command=STRTOKEN, diagnostic=True,
                env={"FAKE_ADAPTER_FAULTS": "leak_version"},
            )
            self.assertGreater(bundle["summary"]["total"]["FAIL"], 0, "no leak detected for string tokens")

    def test_leak_detection_still_works_for_integer_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite")
            bundle = _run(
                root, Path(tmp) / "out", diagnostic=True,
                env={**CONCRETE_VERSION, "FAKE_ADAPTER_FAULTS": "leak_version"},
            )
            self.assertGreater(bundle["summary"]["total"]["FAIL"], 0, "no leak detected for integer tokens")


class ClaimRuleTests(unittest.TestCase):
    """IR-003: omitting a harness capability declaration must not yield a
    claim-supporting bundle for an implementation that breaks a Core rule."""

    def test_minimal_declaration_with_a_core_fault_is_not_claim_supporting(self):
        for fault in ("dup_add_advances", "timestamp_order", "restore_appends"):
            with self.subTest(fault=fault):
                with tempfile.TemporaryDirectory() as tmp:
                    root = _copy_suite(Path(tmp) / "suite")
                    bundle = _run(
                        root, Path(tmp) / "out", command=MINCAPS, diagnostic=True,
                        env={"FAKE_ADAPTER_FAULTS": fault},
                    )
                    self.assertFalse(bundle["claim_supporting"])
                    self.assertTrue(
                        any("did not declare a required capability" in b for b in bundle["claim_support_blockers"]),
                        bundle["claim_support_blockers"],
                    )

    def test_suite_caused_not_executable_does_not_block_a_claim(self):
        # D22-CON-001 and D22-CS4-003 define no assertions (planned for 0.2.0): suite-caused,
        # not adapter-caused, so they must not appear among the adapter-caused blockers.
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            bundle = _run(root, Path(tmp) / "out", env=CONCRETE_VERSION)
            self.assertTrue(bundle["claim_supporting"], bundle["claim_support_blockers"])
            self.assertEqual(bundle["summary"]["adapter_caused_not_executable_blockers"], [])


if __name__ == "__main__":
    unittest.main()
