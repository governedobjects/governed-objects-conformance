# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""A fake adapter that declares only the required identity capability fields and can
inject one of fake_runtime.FAULTS. Used by the IR-003 self-test: an adapter that omits
harness-capability declarations must not obtain a claim-supporting bundle for a run that
hides a Core fault behind the resulting NOT EXECUTABLE scenarios.

Environment:

* ``FAKE_ADAPTER_FAULTS``  comma-separated fault names from fake_runtime.FAULTS
* ``FAKE_ADAPTER_VERSION`` the declared implementation version (default ``1.0.0``)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_runtime import FakeClient  # noqa: E402

REQUIRED_ONLY = {"protocol", "implementation", "spec_version", "spec_revision", "core_claimed", "profiles_claimed"}


def main() -> None:
    faults = set(filter(None, os.environ.get("FAKE_ADAPTER_FAULTS", "").split(",")))
    client = FakeClient(faults=faults)
    client.capabilities = {k: v for k, v in client.capabilities.items() if k in REQUIRED_ONLY}
    client.capabilities.update(
        {
            "protocol": "draft2.2",
            "implementation": {"name": "mincaps-probe", "version": os.environ.get("FAKE_ADAPTER_VERSION", "1.0.0")},
            "spec_version": "v0alpha1",
            "spec_revision": "draft2.2",
            "core_claimed": True,
            "profiles_claimed": [],
        }
    )
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        resp = dict(client.request(req))
        resp["id"] = req.get("id")
        if req["op"] == "define_fixture_types":
            resp["fixtures_sha256"] = req.get("fixtures_sha256")
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
