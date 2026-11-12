# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""A fake THIRD-PARTY adapter: the in-memory protocol fake behind an NDJSON stdin/stdout loop.

It is launched only through ``--adapter-command`` (no runner support code knows about it).
FAKE_ADAPTER_MODE selects a deliberately incomplete adapter for negative tests:

* ``no-declaration``  capabilities lack the self-declaration
* ``no-ack``          define_fixture_types does not echo fixtures_sha256

Other environment switches (used by the release-rule self-tests):

* ``FAKE_ADAPTER_VERSION``    the declared implementation version (default ``dev-fake``, a
  placeholder, so a run with the default never supports a claim)
* ``FAKE_ADAPTER_HANG_ON``    an op name; the first request with that op never answers
  (the marker file ``FAKE_ADAPTER_HANG_MARK`` records that it already hung once)
* ``FAKE_ADAPTER_BUILD_PATH`` a string placed in the optional ``build`` object, to test redaction
* ``FAKE_ADAPTER_CLAIM_EXTRA`` comma-separated capability names declared true (for example ``harness_clock``)
* ``FAKE_ADAPTER_BUILD_VCS``   places source-control keys and a commit hash in the ``build`` object
* ``FAKE_ADAPTER_LOG``         file that records the ``op`` of every request received
* ``FAKE_ADAPTER_FAULTS``      comma-separated fault names from fake_runtime.FAULTS
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_runtime import FakeClient  # noqa: E402


# Synthetic commit hash, built at run time so no hash literal sits in the file.
FAKE_COMMIT = "0123456789abcdef" * 2 + "01234567"


def main() -> None:
    mode = os.environ.get("FAKE_ADAPTER_MODE", "")
    faults = set(filter(None, os.environ.get("FAKE_ADAPTER_FAULTS", "").split(",")))
    client = FakeClient(faults=faults)
    if mode != "no-declaration":
        client.capabilities.update(
            {
                "implementation": {"name": "fake-third-party", "version": os.environ.get("FAKE_ADAPTER_VERSION", "dev-fake")},
                "spec_version": "v0alpha1",
                "spec_revision": "draft2.2",
                "core_claimed": True,
                "profiles_claimed": [],
            }
        )
    if os.environ.get("FAKE_ADAPTER_BUILD_PATH"):
        client.capabilities["build"] = {"source": os.environ["FAKE_ADAPTER_BUILD_PATH"]}
    for name in filter(None, os.environ.get("FAKE_ADAPTER_CLAIM_EXTRA", "").split(",")):
        client.capabilities[name] = True
    if os.environ.get("FAKE_ADAPTER_BUILD_VCS"):
        client.capabilities.setdefault("build", {}).update(
            {"vcs": "git", "vcs.revision": FAKE_COMMIT, "vcs.time": "2026-01-01T00:00:00Z",
             "vcs.modified": "true", "go_version": "go1.27.3", "note": f"built from {FAKE_COMMIT} ({FAKE_COMMIT[6:13]})"}
        )
    log = os.environ.get("FAKE_ADAPTER_LOG")
    hang_on = os.environ.get("FAKE_ADAPTER_HANG_ON")
    hang_mark = os.environ.get("FAKE_ADAPTER_HANG_MARK")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        if log:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(req["op"] + "\n")
        if hang_on and req["op"] == hang_on and hang_mark and not Path(hang_mark).exists():
            Path(hang_mark).write_text("hung once\n")
            time.sleep(3600)
        resp = dict(client.request(req))
        resp["id"] = req.get("id")
        if req["op"] == "define_fixture_types" and mode != "no-ack":
            resp["fixtures_sha256"] = req.get("fixtures_sha256")
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
