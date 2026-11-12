# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Internal harness tests for relationship-set assertions and revision behavior."""

from __future__ import annotations

import unittest

from runner.engine import (
    _relationship_sets_equal,
    _relationship_uniqueness_error,
    evaluate_assertion,
)
from runner.revisions import load_manifest


class RelationshipComparisonTests(unittest.TestCase):
    def test_draft2_sorted_list_hides_order_but_not_extra_entries(self) -> None:
        left = [{"source": "a", "type": "t", "target": "b"}]
        right = [{"source": "a", "type": "t", "target": "b"}, {"source": "a", "type": "t", "target": "b"}]
        ok, _ = _relationship_sets_equal(left, right, comparison_mode="sorted_list")
        self.assertFalse(ok)

    def test_draft21_uniqueness_failure_on_duplicates(self) -> None:
        rels = [
            {"source": "a", "type": "t", "target": "b"},
            {"source": "a", "type": "t", "target": "b"},
        ]
        err = _relationship_uniqueness_error([("a", "t", "b"), ("a", "t", "b")])
        self.assertIsNotNone(err)
        ok, msg = _relationship_sets_equal(rels, rels[:1], comparison_mode="set_with_uniqueness")
        self.assertFalse(ok)
        self.assertIn("duplicate", msg)

    def test_draft21_set_equality_ignores_order(self) -> None:
        left = [
            {"type": "owned_by", "target": "p1"},
            {"type": "depends_on", "target": "w2"},
        ]
        right = [
            {"type": "depends_on", "target": "w2"},
            {"type": "owned_by", "target": "p1"},
        ]
        ok, msg = _relationship_sets_equal(left, right, comparison_mode="set_with_uniqueness")
        self.assertTrue(ok, msg)

    def test_relationship_triple_count_assertion(self) -> None:
        ctx = {
            "step": {
                "semantic_view": {
                    "relationships": [
                        {"type": "belongs_to", "target": "b"},
                        {"type": "belongs_to", "target": "b"},
                    ]
                }
            }
        }
        ok, msg = evaluate_assertion(
            {
                "relationship_triple_count": {"type": "belongs_to", "target": "b", "count": 1},
                "step": "step",
            },
            ctx,
            relationship_comparison="set_with_uniqueness",
        )
        self.assertFalse(ok)
        self.assertIn("expected 1", msg)


class TargetSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = __import__("pathlib").Path(__file__).resolve().parents[1]

    def test_only_the_draft22_target_exists(self) -> None:
        from runner.revisions import supported_revisions

        self.assertEqual(supported_revisions(self.repo_root), ("draft2.2",))
        with self.assertRaises(ValueError):
            load_manifest(self.repo_root, "draft2.1")

    def test_spec_identity_is_stated_once_in_suite_json(self) -> None:
        import json

        raw = json.loads((self.repo_root / "scenarios" / "manifests" / "draft2.2.json").read_text(encoding="utf-8"))
        for key in ("spec_version", "spec_revision", "spec_revision_label", "profile_scope"):
            self.assertNotIn(key, raw, key)
        manifest = load_manifest(self.repo_root, "draft2.2")
        target = json.loads((self.repo_root / "SUITE.json").read_text(encoding="utf-8"))["targets"][0]
        self.assertEqual((manifest["spec_version"], manifest["spec_revision"]), (target["spec_version"], target["spec_revision"]))
        self.assertIn("spec_identity_note", target)

    def test_gap_table_covers_every_core_requirement_once(self) -> None:
        import json
        import re

        reqs = json.loads((self.repo_root / "scenarios" / "draft2.2" / "requirements.json").read_text(encoding="utf-8"))
        ids = [r["id"] for r in reqs["requirements"]]
        text = (self.repo_root / "docs" / "gap-table.md").read_text(encoding="utf-8")
        classes = {"tested", "partially tested", "not executable by this suite", "not externally observable", "not yet tested"}
        rows = re.findall(r"^\| ([A-Z0-9-]+-\d{3}) \| (MUST|SHOULD) \| ([a-z ]+) \|", text, re.M)
        self.assertEqual(sorted(r[0] for r in rows), sorted(ids))
        self.assertTrue({r[2].strip() for r in rows} <= classes)

    def test_draft22_selects_78_scenarios(self) -> None:
        from runner.d22.engine import load_draft22_scenarios

        manifest = load_manifest(self.repo_root, "draft2.2")
        scenarios = load_draft22_scenarios(self.repo_root, manifest)
        self.assertEqual(len(scenarios), 78)
        self.assertEqual(sum(1 for s in scenarios if s["origin"] == "inherited"), 46)


if __name__ == "__main__":
    unittest.main()
