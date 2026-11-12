# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Target selection. The specification identity of each target is stated once, in the
``targets`` list of ``SUITE.json``; the scenario manifest does not repeat it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runner import suite

DEFAULT_SPEC_REVISION = "draft2.2"


def targets(repo_root: Path) -> list[dict[str, Any]]:
    return list(suite.read_suite(repo_root)["targets"])


def supported_revisions(repo_root: Path | None = None) -> tuple[str, ...]:
    return tuple(t["spec_revision"] for t in targets(repo_root or suite.suite_root()))


def load_manifest(repo_root: Path, spec_revision: str = DEFAULT_SPEC_REVISION) -> dict[str, Any]:
    matching = [t for t in targets(repo_root) if t["spec_revision"] == spec_revision]
    if not matching:
        raise ValueError(f"unsupported spec revision: {spec_revision!r}; this suite targets {supported_revisions(repo_root)}")
    target = matching[0]
    with (repo_root / target["scenario_manifest"]).open(encoding="utf-8") as fh:
        data = json.load(fh)
    # The specification identity comes only from SUITE.json.
    data["spec_version"] = target["spec_version"]
    data["spec_revision"] = target["spec_revision"]
    data["spec_revision_label"] = target["spec_revision"]
    data["profile_scope"] = target["profile_scope"]
    data["manifest_path"] = target["scenario_manifest"]
    return data
