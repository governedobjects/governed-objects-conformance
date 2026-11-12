# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""A fake adapter wrapping fake_runtime.FakeClient to expose opaque, NON-integer Object
Version tokens (``rev-<n>-z``) instead of the fake's native decimal integers. Semantics
are otherwise identical to fake_adapter.py.

Used by the IR-001 self-tests: the suite must treat Object Versions as opaque JSON
scalars, so an implementation using a non-integer token grammar must still pass every
unconditional Core scenario, and leaked-token detection must work for such tokens too.

Restoration is declared unsupported here (CS-10's ceiling comparison is specific to a
decimal-string capability value and is exercised separately, by fake_adapter.py, under
its native integer tokens); every other capability matches fake_runtime's defaults.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_runtime import FakeClient  # noqa: E402

PREFIX, SUFFIX = "rev-", "-z"
GRAMMAR = r"^rev-[0-9]+-z$"
VERSION_KEYS = {"version", "object_version", "current_version"}


def encode(value: Any) -> Any:
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{PREFIX}{value}{SUFFIX}"
    return value


def decode(value: Any) -> Any:
    if isinstance(value, str) and re.fullmatch(GRAMMAR, value):
        return int(value[len(PREFIX) : -len(SUFFIX)])
    if value is None:
        return None
    return -1  # any other token form: treat as never issued (stale/invalid)


def walk_encode(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (encode(v) if k in VERSION_KEYS else walk_encode(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [walk_encode(v) for v in value]
    return value


def main() -> None:
    faults = set(filter(None, os.environ.get("FAKE_ADAPTER_FAULTS", "").split(",")))
    client = FakeClient(faults=faults)
    client.capabilities.update(
        {
            "implementation": {"name": "string-token-probe", "version": os.environ.get("FAKE_ADAPTER_VERSION", "1.0.0")},
            "spec_version": "v0alpha1",
            "spec_revision": "draft2.2",
            "core_claimed": True,
            "profiles_claimed": [],
            "version_token_grammar": GRAMMAR,
            "never_issued_version_token": encode(999999999),
            "restoration": False,
            "restorable_types": [],
        }
    )
    client.capabilities.pop("object_version_ceiling", None)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        if "expected_version" in req:
            req["expected_version"] = decode(req["expected_version"])
        resp = dict(client.request(req))
        if req["op"] != "capabilities":
            resp = walk_encode(resp)
        resp["id"] = req.get("id")
        if req["op"] == "define_fixture_types":
            resp["fixtures_sha256"] = req.get("fixtures_sha256")
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
