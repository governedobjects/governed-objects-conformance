# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Conformance runner CLI.

Run an adapter (any implementation) against the Draft 2.2 Core target:

    python -m runner --adapter-command "<command line>" [--adapter-cwd DIR] --output-dir DIR

Verify a results bundle against this suite checkout:

    python -m runner --verify-bundle DIR

The runner is implementation-neutral: the adapter command is the only coupling.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from runner import suite
from runner.adapter_client import DEFAULT_REQUEST_TIMEOUT, DEFAULT_STARTUP_TIMEOUT
from runner.revisions import DEFAULT_SPEC_REVISION, load_manifest, supported_revisions


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m runner",
        description="Governed Objects conformance runner (Core target). Results are self-attested.",
    )
    parser.add_argument("--spec-revision", choices=list(supported_revisions()), default=DEFAULT_SPEC_REVISION)
    parser.add_argument(
        "--adapter-command",
        help="command line that starts the adapter (NDJSON over stdin/stdout); split with shell quoting rules, "
        "run without a shell",
    )
    parser.add_argument("--adapter-cwd", default=None, help="working directory for the adapter command")
    parser.add_argument("--output-dir", default=None, help="where to write the results bundle and reports")
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="mark the run diagnostic: the bundle is labelled as not supporting a conformance claim",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=None,
        metavar="ID",
        help="run only this scenario (repeatable); implies a diagnostic bundle",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT,
        metavar="SECONDS",
        help=f"per-request timeout; a request that does not answer in time is terminated and the scenario is "
        f"ADAPTER-ERROR (default {DEFAULT_REQUEST_TIMEOUT:g})",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=DEFAULT_STARTUP_TIMEOUT,
        metavar="SECONDS",
        help=f"timeout for the adapter's first response (it may need to build or load first; default "
        f"{DEFAULT_STARTUP_TIMEOUT:g})",
    )
    parser.add_argument(
        "--include-local-detail",
        action="store_true",
        help="private diagnostics only: keep local paths, the full invocation and the platform string in the "
        "bundle and reports (recorded in the bundle, with a warning; review before sharing)",
    )
    parser.add_argument("--verify-bundle", metavar="DIR", help="check a results bundle against this suite and exit")
    parser.add_argument(
        "--write-suite-manifest",
        action="store_true",
        help="maintainer release step: record SUITE-MANIFEST.json for the current suite files and exit",
    )
    args = parser.parse_args(argv)
    repo_root = suite.suite_root()

    if args.write_suite_manifest:
        data = suite.write_integrity_manifest(repo_root)
        print(f"Wrote {suite.MANIFEST_NAME}: {len(data['files'])} files, sha256 {data['sha256']}")
        return
    if args.verify_bundle:
        from runner.bundle import verify_bundle

        problems = verify_bundle(Path(args.verify_bundle).resolve(), repo_root)
        if problems:
            print("Bundle verification FAILED:")
            for p in problems:
                print(f"  - {p}")
            sys.exit(1)
        print("Bundle verification OK: consistent with this suite's files (hash check, not a signature).")
        return
    if not args.adapter_command:
        parser.error("--adapter-command is required")

    from runner.d22.cli import run_draft22

    manifest = load_manifest(repo_root, args.spec_revision)
    run_draft22(repo_root, manifest, args)


if __name__ == "__main__":
    main()
