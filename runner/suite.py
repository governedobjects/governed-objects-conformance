# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Suite identity: version (single source), suite-owned fixtures and the integrity manifest.

The suite version lives only in the ``VERSION`` file. ``SUITE-MANIFEST.json`` records the
SHA-256 of every file that defines suite behavior (runner code, scenarios, manifests,
fixtures, protocol, VERSION, SUITE.json) at release time. A run that finds the live files
different from the manifest is diagnostic only and cannot support a conformance claim."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
MANIFEST_NAME = "SUITE-MANIFEST.json"
# Paths (relative to the suite root) that define suite behavior.
INTEGRITY_ROOTS = ("runner", "scenarios", "fixtures", "protocol")
INTEGRITY_FILES = ("VERSION", "SUITE.json")


def suite_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def read_version(root: Path) -> str:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.match(version):
        raise ValueError(f"VERSION {version!r} is not a semantic version")
    return version


def is_prerelease(version: str) -> bool:
    m = SEMVER.match(version)
    return bool(m and m.group(4))


def read_suite(root: Path) -> dict[str, Any]:
    return json.loads((root / "SUITE.json").read_text(encoding="utf-8"))


def integrity_files(root: Path) -> list[str]:
    files: list[str] = [f for f in INTEGRITY_FILES if (root / f).is_file()]
    for top in INTEGRITY_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                files.append(path.relative_to(root).as_posix())
    return sorted(set(files))


def compute_integrity(root: Path) -> dict[str, Any]:
    files = {rel: sha256_file(root / rel) for rel in integrity_files(root)}
    combined = sha256_bytes("".join(f"{k}\0{v}\n" for k, v in sorted(files.items())).encode())
    return {"sha256": combined, "files": files}


def write_integrity_manifest(root: Path) -> dict[str, Any]:
    data = {"suite_version": read_version(root), "algorithm": "sha256", **compute_integrity(root)}
    (root / MANIFEST_NAME).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def check_integrity(root: Path) -> dict[str, Any]:
    """Compare live suite files with the recorded release manifest."""
    live = compute_integrity(root)
    path = root / MANIFEST_NAME
    result: dict[str, Any] = {"live_sha256": live["sha256"], "manifest_file": MANIFEST_NAME}
    if not path.is_file():
        return {**result, "status": "missing", "recorded_sha256": None, "differences": [f"{MANIFEST_NAME} not found"]}
    recorded = json.loads(path.read_text(encoding="utf-8"))
    diffs: list[str] = []
    if recorded.get("suite_version") != read_version(root):
        diffs.append(f"VERSION {read_version(root)} != recorded suite_version {recorded.get('suite_version')}")
    rec_files = recorded.get("files", {})
    for rel in sorted(set(rec_files) | set(live["files"])):
        if rel not in live["files"]:
            diffs.append(f"missing: {rel}")
        elif rel not in rec_files:
            diffs.append(f"unrecorded: {rel}")
        elif rec_files[rel] != live["files"][rel]:
            diffs.append(f"modified: {rel}")
    return {
        **result,
        "status": "verified" if not diffs else "modified",
        "recorded_sha256": recorded.get("sha256"),
        "differences": diffs[:50],
    }


def load_fixtures(root: Path) -> tuple[dict[str, Any], str]:
    """The suite-owned fixture definitions and their canonical SHA-256."""
    suite = read_suite(root)
    definition = json.loads((root / suite["fixtures"]).read_text(encoding="utf-8"))
    return definition, sha256_bytes(canonical_json(definition))


def scenario_set_digest(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """SHA-256 over the manifest, every scenario source it selects, the requirement map,
    the inherited map and the fixture definitions."""
    rels = set()
    for key in ("inherited_scenario_roots",):
        for r in manifest.get(key, []):
            rels.update(p.relative_to(root).as_posix() for p in (root / r).rglob("*.json"))
    rels.update(p.relative_to(root).as_posix() for p in (root / manifest["draft22_scenario_root"]).rglob("*.json"))
    rels.add(manifest["requirements_path"])
    rels.add(manifest["inherited_map_path"])
    rels.add(read_suite(root)["fixtures"])
    rels.add(manifest["manifest_path"])
    files = {rel: sha256_file(root / rel) for rel in sorted(rels)}
    return {
        "sha256": sha256_bytes("".join(f"{k}\0{v}\n" for k, v in sorted(files.items())).encode()),
        "file_count": len(files),
    }
