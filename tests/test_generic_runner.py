# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Self-tests for the implementation-neutral runner: generic launch, self-declaration,
self-attested results bundle, suite versioning and integrity, suite-owned fixtures,
diagnostic modes and protocol-schema accuracy."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runner import suite  # noqa: E402
from runner.bundle import BUNDLE_FILE, verify_bundle  # noqa: E402
from runner.d22.cli import run_draft22  # noqa: E402
from runner.revisions import load_manifest  # noqa: E402

FAKE = f"{sys.executable} {ROOT / 'tests' / 'fake_adapter.py'}"
# The fake adapter's default version is the placeholder "dev-fake", which never supports a
# claim. Every run below that needs a claim-capable declaration, or that proves some other
# rule blocks a claim, pins this concrete version so the placeholder is not a second cause.
CONCRETE_VERSION = {"FAKE_ADAPTER_VERSION": "9.9.9"}
SUITE_PARTS = ("runner", "scenarios", "fixtures", "protocol")


def _copy_suite(dest: Path, version: str = "1.0.0") -> Path:
    for part in SUITE_PARTS:
        shutil.copytree(ROOT / part, dest / part, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(ROOT / "SUITE.json", dest / "SUITE.json")
    (dest / "VERSION").write_text(version + "\n", encoding="utf-8")
    suite.write_integrity_manifest(dest)
    return dest


def _run(root: Path, out: Path, command: str = FAKE, *, diagnostic=False, scenario=None, env=None):
    args = argparse.Namespace(
        adapter_command=command, adapter_cwd=None, output_dir=str(out), diagnostic=diagnostic, scenario=scenario
    )
    manifest = load_manifest(root, "draft2.2")
    old = dict(os.environ)
    os.environ.update(env or {})
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            run_draft22(root, manifest, args)
    finally:
        os.environ.clear()
        os.environ.update(old)
    return json.loads((out / BUNDLE_FILE).read_text(encoding="utf-8"))


class SuiteIdentityTests(unittest.TestCase):
    def test_version_is_single_semver_source(self):
        version = suite.read_version(ROOT)
        self.assertEqual(version, "0.1.0")
        self.assertFalse(suite.is_prerelease(version))
        self.assertTrue(suite.is_prerelease("0.1.0-dev"))
        self.assertFalse(suite.is_prerelease("1.0.0"))
        self.assertEqual(sorted(suite.read_suite(ROOT)), ["fixtures", "integrity_manifest", "name", "note", "targets", "version_file"])
        self.assertNotIn("version", suite.read_suite(ROOT))

    def test_suite_states_which_spec_revision_it_targets(self):
        targets = suite.read_suite(ROOT)["targets"]
        self.assertEqual([(t["spec_version"], t["spec_revision"]) for t in targets], [("v0alpha1", "draft2.2")])

    def test_bad_version_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "VERSION").write_text("one.two\n")
            with self.assertRaises(ValueError):
                suite.read_version(Path(tmp))


class FakeThirdPartyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_generic_launch_produces_valid_self_attested_claim_supporting_bundle(self):
        root = _copy_suite(self.tmp / "suite")  # a released (non-prerelease, manifest-verified) suite
        bundle = _run(root, self.tmp / "out", env=CONCRETE_VERSION)
        self.assertEqual(bundle["attestation"]["kind"], "self-attested")
        self.assertEqual(bundle["attestation"]["certification"], "none")
        self.assertEqual(bundle["adapter"]["declaration"]["implementation"], {"name": "fake-third-party", "version": "9.9.9"})
        self.assertTrue(bundle["adapter"]["declaration"]["self_declared"])
        self.assertEqual(bundle["suite"]["version"], "1.0.0")
        self.assertEqual(bundle["suite"]["integrity"]["status"], "verified")
        self.assertEqual(bundle["spec"]["revision"], "draft2.2")
        self.assertTrue(bundle["fixtures"]["acknowledged"])
        self.assertEqual(bundle["summary"]["total"]["FAIL"], 0)
        self.assertTrue(bundle["claim_supporting"], bundle["claim_support_blockers"])
        self.assertIn("1.0.0", bundle["claim_text"])
        self.assertIn("v0alpha1 draft2.2", bundle["claim_text"])
        self.assertIn("self-attested", bundle["claim_text"])
        self.assertEqual(verify_bundle(self.tmp / "out", root), [])

    def test_default_fake_version_is_a_placeholder_that_blocks_a_claim(self):
        # The same full run of a released, verified suite as above, but with the sample's own
        # default version: the placeholder is the only reason it supports no claim.
        root = _copy_suite(self.tmp / "suite")
        saved = os.environ.pop("FAKE_ADAPTER_VERSION", None)
        try:
            bundle = _run(root, self.tmp / "out")
        finally:
            if saved is not None:
                os.environ["FAKE_ADAPTER_VERSION"] = saved
        self.assertEqual(bundle["adapter"]["declaration"]["implementation"], {"name": "fake-third-party", "version": "dev-fake"})
        self.assertEqual(bundle["mode"], "full")
        self.assertEqual(bundle["suite"]["integrity"]["status"], "verified")
        self.assertFalse(bundle["suite"]["prerelease"])
        self.assertTrue(bundle["fixtures"]["acknowledged"])
        self.assertEqual(bundle["summary"]["total"]["FAIL"], 0)
        self.assertEqual(bundle["summary"]["total"]["ADAPTER-ERROR"], 0)
        self.assertFalse(bundle["claim_supporting"])
        self.assertIsNone(bundle["claim_text"])
        self.assertEqual(
            bundle["claim_support_blockers"],
            ["implementation version 'dev-fake' is a placeholder (starts with 'dev')"],
        )
        self.assertEqual(verify_bundle(self.tmp / "out", root), [])

    def test_not_applicable_and_not_executable_are_never_counted_as_pass(self):
        bundle = _run(_copy_suite(self.tmp / "suite"), self.tmp / "out", env=CONCRETE_VERSION)
        results = bundle["results"]
        for sid, r in results.items():
            if r["status"] in ("NOT APPLICABLE", "NOT EXECUTABLE"):
                self.assertNotEqual(r["status"], "PASS")
        s = bundle["summary"]
        self.assertEqual(sum(s["total"].values()), len(results))
        self.assertEqual(sum(s["must"].values()) + sum(s["should"].values()), len(results))
        self.assertGreater(s["should"]["PASS"], 0)
        self.assertIn("D22-CON-001", s["mandatory_not_executed"])

    def test_prerelease_suite_never_supports_a_claim(self):
        bundle = _run(ROOT_COPY_PRERELEASE(self.tmp), self.tmp / "out", env=CONCRETE_VERSION)
        self.assertFalse(bundle["claim_supporting"])
        self.assertTrue(any("pre-release" in b for b in bundle["claim_support_blockers"]))
        self.assertIsNone(bundle["claim_text"])


def ROOT_COPY_PRERELEASE(tmp: Path) -> Path:
    return _copy_suite(tmp / "suite-pre", version="0.1.0-dev")


class DiagnosticModeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = _copy_suite(self.tmp / "suite")

    def tearDown(self):
        self._tmp.cleanup()

    def test_diagnostic_flag_cannot_produce_claim_supporting_bundle(self):
        bundle = _run(self.root, self.tmp / "out", diagnostic=True, env=CONCRETE_VERSION)
        self.assertFalse(bundle["claim_supporting"])
        self.assertEqual(bundle["mode"], "diagnostic")
        self.assertIsNone(bundle["claim_text"])
        self.assertIn("DIAGNOSTIC", bundle["label"])

    def test_scenario_subset_is_diagnostic(self):
        bundle = _run(self.root, self.tmp / "out", scenario=["C-ID-001"], env=CONCRETE_VERSION)
        self.assertFalse(bundle["claim_supporting"])
        self.assertEqual(bundle["mode"], "diagnostic")
        self.assertEqual(list(bundle["results"]), ["C-ID-001"])

    def test_edited_scenario_is_detected(self):
        target = next((self.root / "scenarios" / "draft2.2" / "core").glob("*.json"))
        target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        bundle = _run(self.root, self.tmp / "out", env=CONCRETE_VERSION)
        self.assertEqual(bundle["suite"]["integrity"]["status"], "modified")
        self.assertFalse(bundle["claim_supporting"])

    def test_missing_integrity_manifest_is_not_claim_supporting(self):
        (self.root / suite.MANIFEST_NAME).unlink()
        bundle = _run(self.root, self.tmp / "out", env=CONCRETE_VERSION)
        self.assertEqual(bundle["suite"]["integrity"]["status"], "missing")
        self.assertFalse(bundle["claim_supporting"])

    def test_incomplete_declaration_refused_unless_diagnostic(self):
        with self.assertRaises(SystemExit) as caught:
            _run(self.root, self.tmp / "out", env={"FAKE_ADAPTER_MODE": "no-declaration"})
        self.assertIn("declaration incomplete", str(caught.exception))
        bundle = _run(self.root, self.tmp / "out2", diagnostic=True, env={"FAKE_ADAPTER_MODE": "no-declaration"})
        self.assertFalse(bundle["claim_supporting"])
        self.assertFalse(bundle["adapter"]["declaration_valid"])

    def test_unacknowledged_fixtures_refused_unless_diagnostic(self):
        with self.assertRaises(SystemExit) as caught:
            _run(self.root, self.tmp / "out", env={**CONCRETE_VERSION, "FAKE_ADAPTER_MODE": "no-ack"})
        self.assertIn("fixture definitions", str(caught.exception))
        bundle = _run(self.root, self.tmp / "out2", diagnostic=True, env={**CONCRETE_VERSION, "FAKE_ADAPTER_MODE": "no-ack"})
        self.assertFalse(bundle["fixtures"]["acknowledged"])
        self.assertFalse(bundle["claim_supporting"])

    def test_adapter_that_cannot_start_is_a_clean_error(self):
        with self.assertRaises(SystemExit):
            _run(self.root, self.tmp / "out", command="/nonexistent/adapter")


class BundleIntegrityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = _copy_suite(self.tmp / "suite")
        self.out = self.tmp / "out"
        _run(self.root, self.out, env=CONCRETE_VERSION)

    def tearDown(self):
        self._tmp.cleanup()

    def _edit(self, fn):
        path = self.out / BUNDLE_FILE
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def test_untouched_bundle_verifies(self):
        self.assertEqual(verify_bundle(self.out, self.root), [])

    def test_edited_result_is_detected(self):
        def flip(d):
            sid = next(k for k, v in d["results"].items() if v["status"] == "NOT EXECUTABLE")
            d["results"][sid]["status"] = "PASS"
        self._edit(flip)
        problems = verify_bundle(self.out, self.root)
        self.assertTrue(any("body hash" in p for p in problems), problems)

    def test_edited_transcript_is_detected(self):
        t = self.out / "transcripts" / "adapter.jsonl"
        t.write_text(t.read_text(encoding="utf-8").replace("ACCEPTED", "REFUSED", 1), encoding="utf-8")
        self.assertTrue(any("transcript" in p for p in verify_bundle(self.out, self.root)))

    def test_bundle_from_another_suite_version_is_detected(self):
        (self.root / "VERSION").write_text("1.0.1\n", encoding="utf-8")
        problems = verify_bundle(self.out, self.root)
        self.assertTrue(any("suite version" in p for p in problems), problems)

    def test_bundle_with_edited_scenarios_is_detected(self):
        target = next((self.root / "scenarios" / "draft2.2" / "core").glob("*.json"))
        target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        problems = verify_bundle(self.out, self.root)
        self.assertTrue(any("scenario set" in p or "suite files differ" in p for p in problems), problems)


class NeutralityTests(unittest.TestCase):
    FORBIDDEN = (
        "governed_object", "go-test", "PYTHONPATH", "CONFORMANCE_PYTHON_RUNTIME_REPO", "GO_RUNTIME_MODULE",
        "go build", "-modfile", "replace_dir", "buildinfo", "python_adapter_command", "go_adapter_command",
        "module_under_runtime", "--profile", "draft2.1", "frozen",
    )

    def test_runner_contains_no_runtime_specific_code(self):
        for path in sorted((ROOT / "runner").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for word in self.FORBIDDEN:
                self.assertNotIn(word, text, f"{path.relative_to(ROOT)} mentions {word!r}")

    def test_cli_has_no_stale_entry_points(self):
        text = (ROOT / "runner" / "__main__.py").read_text(encoding="utf-8")
        self.assertNotIn("prc", text.lower())
        self.assertFalse((ROOT / "runner" / "prc").exists())
        self.assertEqual(sorted(p.name for p in (ROOT / "scenarios" / "manifests").iterdir()), ["draft2.2.json"])


class FixtureAndProtocolTests(unittest.TestCase):
    def test_blank_title_rule_is_suite_owned(self):
        fixtures, sha = suite.load_fixtures(ROOT)
        rules = fixtures["types"]["conformance.work-item"]["rules"]
        self.assertEqual([(r["field"], r["rule"], r["applies_to"]) for r in rules], [("title", "non-blank-string", ["create", "update"])])
        self.assertRegex(sha, r"^[0-9a-f]{64}$")

    def test_every_type_and_actor_used_by_scenarios_is_defined(self):
        fixtures, _ = suite.load_fixtures(ROOT)
        used_types, used_actors, used_ops = set(), set(), set()

        def walk(node):
            if isinstance(node, dict):
                if "op" in node and isinstance(node["op"], str):
                    used_ops.add(node["op"])
                    if node.get("actor"):
                        used_actors.add(node["actor"])
                    if node.get("type"):
                        used_types.add(node["type"])
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        for path in (ROOT / "scenarios").rglob("*.json"):
            if "manifests" in path.parts or path.name in ("requirements.json", "inherited-map.json"):
                continue
            walk(json.loads(path.read_text(encoding="utf-8")))
        self.assertLessEqual(used_types, set(fixtures["types"]))
        self.assertLessEqual({a for a in used_actors if not a.startswith("$")}, set(fixtures["actors"]))
        self.used_ops = used_ops

    def test_protocol_schema_lists_every_operation_scenarios_send(self):
        schema = json.loads((ROOT / "protocol" / "protocol.schema.json").read_text(encoding="utf-8"))
        schema_ops = {d["properties"]["op"]["const"] for k, d in schema["$defs"].items() if k.startswith("req_")}
        sent = set()
        reserved_unused = {"concurrent", "replay_unsupported_type_version"}  # only in non-executed / excluded scenarios
        for path in (ROOT / "scenarios").rglob("*.json"):
            if "manifests" in path.parts or path.name in ("requirements.json", "inherited-map.json"):
                continue
            text = path.read_text(encoding="utf-8")
            sent |= set(re.findall(r'"op":\s*"([a-z_]+)"', text))
        self.assertLessEqual(sent - reserved_unused, schema_ops)
        # runner-originated operations
        self.assertLessEqual({"capabilities", "reset", "define_fixture_types"}, schema_ops)

    def test_schema_documents_declaration_fields(self):
        schema = json.loads((ROOT / "protocol" / "protocol.schema.json").read_text(encoding="utf-8"))
        caps = schema["$defs"]["capabilities"]
        self.assertEqual(
            set(caps["required"]), {"implementation", "spec_version", "spec_revision", "core_claimed", "profiles_claimed"}
        )


if __name__ == "__main__":
    unittest.main()
