# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Self-tests for the release rules: pre-release suites, placeholder implementation
versions, claim text naming mandatory scenarios that were not executed, default path
minimization and per-request timeouts."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from runner import suite  # noqa: E402
from runner.bundle import BUNDLE_FILE, not_executed_statement, verify_bundle  # noqa: E402
from runner.d22.cli import run_draft22  # noqa: E402
from runner.declaration import version_problem  # noqa: E402
from runner.privacy import Redactor  # noqa: E402
from runner.revisions import load_manifest  # noqa: E402
from test_generic_runner import CONCRETE_VERSION, FAKE, _copy_suite  # noqa: E402


def _run(root: Path, out: Path, *, env=None, command: str = FAKE, **opts):
    args = argparse.Namespace(
        adapter_command=command, adapter_cwd=None, output_dir=str(out), diagnostic=False, scenario=None, **opts
    )
    old = dict(os.environ)
    os.environ.update(env or {})
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            run_draft22(root, load_manifest(root, "draft2.2"), args)
    finally:
        os.environ.clear()
        os.environ.update(old)
    return json.loads((out / BUNDLE_FILE).read_text(encoding="utf-8"))


class PrereleaseTests(unittest.TestCase):
    def test_every_prerelease_suffix_is_a_prerelease(self):
        for v in ("0.1.0-dev", "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-rc.1", "1.0.0-rc1",
                  "2.3.4-0.3.7", "1.0.0-x.7.z.92", "1.0.0-SNAPSHOT", "1.0.0-dev+build.5"):
            self.assertTrue(suite.is_prerelease(v), v)
        for v in ("0.1.0", "1.0.0", "10.20.30", "1.0.0+build.5"):
            self.assertFalse(suite.is_prerelease(v), v)

    def test_each_prerelease_suite_blocks_a_claim(self):
        for version in ("1.0.0-dev", "1.0.0-alpha.1", "1.0.0-beta", "1.0.0-rc.2"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                root = _copy_suite(Path(tmp) / "suite", version)
                bundle = _run(root, Path(tmp) / "out", env=CONCRETE_VERSION)
                self.assertFalse(bundle["claim_supporting"])
                self.assertIsNone(bundle["claim_text"])
                self.assertTrue(bundle["suite"]["prerelease"])
                self.assertTrue(any("pre-release" in b for b in bundle["claim_support_blockers"]), version)
                self.assertEqual(verify_bundle(Path(tmp) / "out", root), [])

    def test_real_suite_version_is_the_release(self):
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "0.1.0")


class ImplementationVersionTests(unittest.TestCase):
    def test_placeholders_and_empty_are_refused(self):
        for v in ("", "   ", None, "unversioned", "unversioned-working-tree", "Unknown", "unknown", "dev", "dev-build",
                  "DEV", "development"):
            self.assertIsNotNone(version_problem(v), repr(v))

    def test_concrete_versions_are_accepted_without_requiring_semver(self):
        for v in ("1.2.3", "9.9.9", "2026.11", "r45", "build-77", "v0.3", "main-77", "1.0.0-rc.1", "0"):
            self.assertIsNone(version_problem(v), v)

    def test_placeholder_blocks_a_claim_in_a_full_run(self):
        for version in ("unversioned-working-tree", "unknown", "dev-snapshot"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                root = _copy_suite(Path(tmp) / "suite", "1.0.0")
                bundle = _run(root, Path(tmp) / "out", env={"FAKE_ADAPTER_VERSION": version})
                self.assertFalse(bundle["claim_supporting"])
                self.assertTrue(any("placeholder" in b for b in bundle["claim_support_blockers"]))
                self.assertEqual(bundle["summary"]["total"]["FAIL"], 0)

    def test_non_semver_version_supports_a_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            bundle = _run(root, Path(tmp) / "out", env={"FAKE_ADAPTER_VERSION": "2026.11-r45"})
            self.assertTrue(bundle["claim_supporting"], bundle["claim_support_blockers"])
            self.assertIn("fake-third-party 2026.11-r45", bundle["claim_text"])


class ClaimTextNamesUntestedTests(unittest.TestCase):
    def test_statement_format(self):
        self.assertEqual(
            not_executed_statement("0.1.0", ["D22-CON-001", "D22-CS4-003"], []),
            "Not executed by suite 0.1.0: D22-CON-001, D22-CS4-003.",
        )
        self.assertEqual(
            not_executed_statement("0.1.0", [], ["D22-REL-999"]),
            "Not executed because the adapter did not declare a capability the scenario needs: D22-REL-999.",
        )
        self.assertIsNone(not_executed_statement("0.1.0", [], []))

    def test_claim_supporting_bundle_names_the_unexecuted_mandatory_scenarios(self):
        """The fake third-party adapter, with a temporary non-pre-release suite version
        created inside the test only; VERSION of the real suite is untouched."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            out = Path(tmp) / "out"
            bundle = _run(root, out, env=CONCRETE_VERSION)
            self.assertTrue(bundle["claim_supporting"], bundle["claim_support_blockers"])
            self.assertEqual(bundle["summary"]["mandatory_not_executable"], ["D22-CON-001", "D22-CS4-003"])
            expected = "Not executed by suite 1.0.0: D22-CON-001, D22-CS4-003."
            self.assertEqual(bundle["not_executed_statement"], expected)
            self.assertIn(expected, bundle["claim_text"])
            self.assertIn(expected, (out / "latest.md").read_text(encoding="utf-8"))
            self.assertEqual(verify_bundle(out, root), [])
            self.assertEqual((ROOT / "VERSION").read_text().strip(), "0.1.0")

    def test_report_names_them_even_when_the_bundle_supports_no_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0-rc.1")
            out = Path(tmp) / "out"
            bundle = _run(root, out, env=CONCRETE_VERSION)
            self.assertFalse(bundle["claim_supporting"])
            self.assertIn("Not executed by suite 1.0.0-rc.1: D22-CON-001, D22-CS4-003.", (out / "latest.md").read_text(encoding="utf-8"))

    def test_verification_catches_a_claim_text_that_hides_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            out = Path(tmp) / "out"
            bundle = _run(root, out, env=CONCRETE_VERSION)
            from runner.bundle import body_digest

            bundle["claim_text"] = "fake-third-party 9.9.9 passes the suite."
            bundle["integrity"]["bundle_body_sha256"] = body_digest(bundle)
            (out / BUNDLE_FILE).write_text(json.dumps(bundle), encoding="utf-8")
            problems = verify_bundle(out, root)
            self.assertTrue(any("claim text does not name" in p for p in problems), problems)


class PathMinimizationTests(unittest.TestCase):
    # Built from pieces so this file itself contains no literal local-path prefix.
    PATTERNS = re.compile("|".join(re.escape(p) for p in ("/ho" "me/", "/Us" "ers/", "/tmp/", "/var/")) + r"|[A-Za-z]:\\|\\\\")

    def _leaks(self, out: Path, extra: tuple[str, ...]) -> list[str]:
        found = []
        for path in sorted(out.rglob("*")):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for needle in extra:
                    if needle and needle in text:
                        found.append(f"{path.name}: {needle}")
                if self.PATTERNS.search(text):
                    found.append(f"{path.name}: {self.PATTERNS.search(text).group(0)}")
        return found

    def test_default_bundle_contains_no_local_detail(self):
        import getpass, socket

        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            out = Path(tmp) / "out"
            workdir = Path(tmp) / "adapter-work"
            workdir.mkdir()
            bundle = _run(
                root, out,
                env={**CONCRETE_VERSION, "FAKE_ADAPTER_BUILD_PATH": f"{Path.home()}/src/impl/{getpass.getuser()}/build"},
                command=f"{sys.executable} {ROOT / 'tests' / 'fake_adapter.py'}",
            )
            leaks = self._leaks(out, (str(Path.home()), tmp, getpass.getuser(), socket.gethostname()))
            self.assertEqual(leaks, [])
            self.assertEqual(bundle["run_options"]["local_detail_included"], False)
            self.assertEqual(sorted(bundle["environment"]), ["architecture", "os_family", "runner", "runner_python", "suite_version"])
            self.assertEqual(bundle["environment"]["suite_version"], "1.0.0")
            self.assertEqual(bundle["adapter"]["capabilities_verbatim"]["build"]["source"], "<abs-path>")
            self.assertEqual(verify_bundle(out, root), [])

    def test_adapter_workdir_is_a_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            work = Path(tmp) / "work"
            work.mkdir()
            args = argparse.Namespace(adapter_command=FAKE, adapter_cwd=str(work), output_dir=str(Path(tmp) / "out"),
                                      diagnostic=False, scenario=None)
            old = dict(os.environ)
            os.environ.update(CONCRETE_VERSION)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    run_draft22(root, load_manifest(root, "draft2.2"), args)
            finally:
                os.environ.clear()
                os.environ.update(old)
            bundle = json.loads((Path(tmp) / "out" / BUNDLE_FILE).read_text())
            self.assertEqual(bundle["adapter"]["working_directory"], "<adapter-workdir>")
            self.assertNotIn(tmp, json.dumps(bundle))

    def test_local_detail_is_opt_in_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            out = Path(tmp) / "out"
            bundle = _run(root, out, include_local_detail=True, env=CONCRETE_VERSION)
            self.assertTrue(bundle["run_options"]["local_detail_included"])
            self.assertIn("local_detail", bundle["environment"])
            self.assertIn(str(ROOT / "tests"), json.dumps(bundle["adapter"]["command"]))
            self.assertEqual(verify_bundle(out, root), [])

    def test_redactor_replaces_paths_and_keeps_ordinary_text(self):
        r = Redactor()
        home = str(Path.home())
        self.assertEqual(r.text(f"see {home}/work/x.py now"), "see <abs-path> now")
        self.assertEqual(r.text("see /opt/vendor/lib/x.py now"), "see <abs-path> now")
        self.assertEqual(r.text("C:" + chr(92) + "Work" + chr(92) + "x"), "<abs-path>")
        self.assertEqual(r.text("application/json and a/b/c and 7300444"), "application/json and a/b/c and 7300444")
        self.assertEqual(r.apply({"a": ["/opt/x/y", 3, None]}), {"a": ["<abs-path>", 3, None]})
        self.assertEqual(Redactor(enabled=False).text("/opt/vendor/x"), "/opt/vendor/x")


class TimeoutTests(unittest.TestCase):
    def test_default_timeouts_are_documented_values(self):
        from runner.adapter_client import DEFAULT_REQUEST_TIMEOUT, DEFAULT_STARTUP_TIMEOUT

        self.assertEqual((DEFAULT_REQUEST_TIMEOUT, DEFAULT_STARTUP_TIMEOUT), (30.0, 300.0))
        text = (ROOT / "README.md").read_text(encoding="utf-8") + (ROOT / "docs" / "adapter-guide.md").read_text(encoding="utf-8")
        self.assertIn("default 30 seconds", text)
        self.assertIn("default 300 seconds", text)

    def test_hung_request_is_adapter_error_and_blocks_a_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            out = Path(tmp) / "out"
            bundle = _run(
                root, out, request_timeout=2.0, startup_timeout=30.0,
                env={**CONCRETE_VERSION, "FAKE_ADAPTER_HANG_ON": "create", "FAKE_ADAPTER_HANG_MARK": str(Path(tmp) / "mark")},
            )
            errors = [sid for sid, r in bundle["results"].items() if r["status"] == "ADAPTER-ERROR"]
            self.assertEqual(len(errors), 1, errors)
            res = bundle["results"][errors[0]]
            self.assertTrue(any("did not answer" in n for n in res["notes"]), res["notes"])
            self.assertNotEqual(res["status"], "PASS")
            self.assertNotEqual(res["status"], "NOT EXECUTABLE")
            # the adapter was restarted: every other scenario still ran
            self.assertEqual(bundle["summary"]["total"]["ADAPTER-ERROR"], 1)
            self.assertGreater(bundle["summary"]["total"]["PASS"], 60)
            self.assertFalse(bundle["claim_supporting"])
            self.assertTrue(any("ADAPTER-ERROR" in b for b in bundle["claim_support_blockers"]))
            self.assertEqual(bundle["run_options"]["request_timeout_seconds"], 2.0)
            self.assertEqual(verify_bundle(out, root), [])

    def test_adapter_that_never_starts_answering_is_a_clean_error(self):
        from runner.adapter_client import AdapterClient, AdapterError, AdapterTimeout

        client = AdapterClient("t", [sys.executable, "-c", "import time; time.sleep(60)"], request_timeout=1, startup_timeout=1)
        with self.assertRaises(AdapterTimeout):
            client.request({"op": "capabilities"})
        self.assertFalse(client.alive)
        self.assertTrue(issubclass(AdapterTimeout, AdapterError))
        client.close()


class EmptyAssertionTests(unittest.TestCase):
    def _bundle(self, tmp, extra="", log=None):
        root = _copy_suite(Path(tmp) / "suite", "1.0.0")
        env = {**CONCRETE_VERSION, "FAKE_ADAPTER_CLAIM_EXTRA": extra}
        if log:
            env["FAKE_ADAPTER_LOG"] = str(log)
        return root, _run(root, Path(tmp) / "out", env=env)

    def test_scenarios_without_assertions_are_exactly_the_two_known_ones(self):
        from runner.d22.engine import load_draft22_scenarios

        scenarios = load_draft22_scenarios(ROOT, load_manifest(ROOT, "draft2.2"))
        self.assertEqual(sorted(s["id"] for s in scenarios if not s.get("assert")), ["D22-CON-001", "D22-CS4-003"])

    def test_harness_clock_declared_is_not_executable_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, b = self._bundle(tmp, "harness_clock")
            r = b["results"]["D22-CS4-003"]
            self.assertEqual(r["status"], "NOT EXECUTABLE")
            self.assertTrue(any("planned for suite 0.2.0" in n for n in r["notes"]), r["notes"])

    def test_reason_is_the_same_without_any_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, b = self._bundle(tmp, "")
            for sid in ("D22-CON-001", "D22-CS4-003"):
                r = b["results"][sid]
                self.assertEqual(r["status"], "NOT EXECUTABLE")
                self.assertTrue(any("does not yet test this scenario" in n and "0.2.0" in n for n in r["notes"]), r["notes"])

    def test_concurrent_invocation_declared_is_not_executable_not_adapter_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, b = self._bundle(tmp, "concurrent_invocation,harness_clock")
            self.assertEqual(b["results"]["D22-CON-001"]["status"], "NOT EXECUTABLE")
            self.assertEqual(b["summary"]["total"]["ADAPTER-ERROR"], 0)
            self.assertTrue(b["claim_supporting"], b["claim_support_blockers"])
            self.assertEqual(b["summary"]["mandatory_not_executable"], ["D22-CON-001", "D22-CS4-003"])
            self.assertIn("Not executed by suite 1.0.0: D22-CON-001, D22-CS4-003.", b["claim_text"])

    def test_no_steps_are_sent_for_empty_assertion_scenarios(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ops.log"
            _, b = self._bundle(tmp, "concurrent_invocation,harness_clock", log)
            ops = log.read_text().split()
            self.assertNotIn("set_clock", ops)
            self.assertNotIn("concurrent", ops)
            for sid in ("D22-CON-001", "D22-CS4-003"):
                line = [json.loads(x) for x in (Path(tmp) / "out" / "transcripts" / "adapter.jsonl").read_text().splitlines()
                        if json.loads(x)["scenario"] == sid][0]
                self.assertEqual(line["steps"], [])


class SourceControlRedactionTests(unittest.TestCase):
    HASH = "0123456789abcdef" * 2 + "01234567"

    def test_default_mode_drops_vcs_metadata_and_commit_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            out = Path(tmp) / "out"
            b = _run(root, out, env={**CONCRETE_VERSION, "FAKE_ADAPTER_BUILD_VCS": "1"})
            build = b["adapter"]["capabilities_verbatim"]["build"]
            self.assertEqual(sorted(build), ["go_version", "note"])
            self.assertEqual(build["note"], "built from <commit-hash> (<commit-hash>)")
            text = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
            self.assertNotIn(self.HASH, text)
            self.assertNotIn("vcs.", text)
            # runner-owned SHA-256 fields are intact and the bundle still verifies
            self.assertRegex(b["integrity"]["bundle_body_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(b["fixtures"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(b["scenario_manifest"]["scenario_set_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(b["suite"]["integrity"]["live_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(b["spec"]["revision"], "draft2.2")
            self.assertEqual(b["adapter"]["capabilities_verbatim"]["spec_revision"], "draft2.2")
            self.assertEqual(verify_bundle(out, root), [])

    def test_opt_in_mode_keeps_them_and_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            out = Path(tmp) / "out"
            args = argparse.Namespace(adapter_command=FAKE, adapter_cwd=None, output_dir=str(out), diagnostic=False,
                                      scenario=None, include_local_detail=True)
            old = dict(os.environ)
            os.environ["FAKE_ADAPTER_BUILD_VCS"] = "1"
            os.environ.update(CONCRETE_VERSION)
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    run_draft22(root, load_manifest(root, "draft2.2"), args)
            finally:
                os.environ.clear()
                os.environ.update(old)
            b = json.loads((out / BUNDLE_FILE).read_text(encoding="utf-8"))
            build = b["adapter"]["capabilities_verbatim"]["build"]
            self.assertEqual(build["vcs.revision"], self.HASH)
            self.assertIn("vcs.time", build)
            self.assertTrue(b["run_options"]["local_detail_included"])
            self.assertIn("should be reviewed before sharing", buf.getvalue())
            self.assertIn("should be reviewed before sharing", (out / "latest.md").read_text(encoding="utf-8"))
            self.assertTrue(b["claim_supporting"], b["claim_support_blockers"])

    def test_default_mode_has_no_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_suite(Path(tmp) / "suite", "1.0.0")
            _run(root, Path(tmp) / "out", env=CONCRETE_VERSION)
            self.assertNotIn("review", (Path(tmp) / "out" / "latest.md").read_text(encoding="utf-8").lower().split("claim scope")[0])

    def test_redactor_metadata_unit(self):
        r = Redactor()
        got = r.metadata({"spec_revision": "draft2.2", "build": {"vcs.revision": "a" * 40, "commit": "abc" + "1234", "x": "see " + "abc" + "12" + "34" + "def"}})
        self.assertEqual(got, {"spec_revision": "draft2.2", "build": {"x": "see <commit-hash>"}})
        self.assertEqual(Redactor(enabled=False).metadata({"vcs": "git"}), {"vcs": "git"})


if __name__ == "__main__":
    unittest.main()
