# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Default path minimization for results bundles and reports.

By default nothing local leaves the machine in a bundle: absolute paths, the user name,
the host name and the home directory are replaced by neutral labels. ``--include-local-detail``
turns this off for private diagnostics; the bundle records which mode produced it."""

from __future__ import annotations

import getpass
import os
import platform
import re
import socket
from pathlib import Path
from typing import Any

ABS_PATH_LABEL = "<abs-path>"
WORKDIR_LABEL = "<adapter-workdir>"
# POSIX absolute paths with at least two segments, and Windows drive-letter paths.
_POSIX = r"(?<![A-Za-z0-9_.\-:/~])/(?:[^\s/\"'`<>|;,()\[\]{}=]+/)+[^\s/\"'`<>|;,()\[\]{}=]*"
_WINDOWS = r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'`<>|;,()\[\]{}=]*"
_UNC = r"\\\\[^\s\\\"']+\\[^\s\"']*"
_PATH_RE = re.compile("|".join((_POSIX, _WINDOWS, _UNC)))


def _literals() -> list[str]:
    found: set[str] = set()
    for fn in (getpass.getuser, socket.gethostname, platform.node, lambda: str(Path.home()), lambda: os.path.expanduser("~")):
        try:
            value = fn()
        except Exception:  # noqa: BLE001
            continue
        if isinstance(value, str) and len(value) >= 3 and value not in ("/", "root"):
            found.add(value)
    return sorted(found, key=len, reverse=True)


# Source-control details are dropped from adapter-supplied metadata by default.
_VCS_ANY = re.compile(r"^vcs([._\\-].*)?$", re.I)
_VCS_KEY = re.compile(r"^(vcs|scm|git|hg|svn)([._\-].*)?$|(^|[._\-])(vcs|commit|revision)([._\-]|$)", re.I)
_HASH = re.compile(r"(?<![0-9A-Za-z])(?:[0-9a-f]{40}|(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7,12})(?![0-9A-Za-z])")


class Redactor:
    """Replace local detail in any JSON-like value."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._literals = _literals() if enabled else []

    def text(self, value: str) -> str:
        if not self.enabled:
            return value
        value = _PATH_RE.sub(ABS_PATH_LABEL, value)
        for lit in self._literals:
            value = value.replace(lit, "<local>")
        return value

    def metadata(self, value: Any, *, build: bool = False) -> Any:
        """Adapter-supplied metadata. Keys naming source control (``vcs*``, and inside the
        optional ``build`` object also ``commit``/``revision``/``scm``/``git`` keys) are
        dropped, commit-hash strings are redacted, then the general redaction applies.
        ``spec_revision`` and the runner's own SHA-256 fields are never touched."""
        if not self.enabled:
            return value
        return self.apply(self._clean(value, build))

    def _clean(self, value: Any, build: bool) -> Any:
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if isinstance(k, str) and (_VCS_ANY.search(k) or (build and _VCS_KEY.search(k))):
                    continue
                out[k] = self._clean(v, build or k in ("build", "optional_build_metadata"))
            return out
        if isinstance(value, (list, tuple)):
            return [self._clean(v, build) for v in value]
        if isinstance(value, str):
            return _HASH.sub("<commit-hash>", value)
        return value

    def apply(self, value: Any) -> Any:
        if not self.enabled:
            return value
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.apply(v) for v in value]
        if isinstance(value, tuple):
            return [self.apply(v) for v in value]
        if isinstance(value, dict):
            return {(self.text(k) if isinstance(k, str) else k): self.apply(v) for k, v in value.items()}
        return value


def environment_block(*, suite_version: str, local_detail: bool, invocation: list[str], platform_string: str) -> dict[str, Any]:
    """Only what helps reproduce a run: OS family, architecture, Python version, suite version."""
    import sys

    env: dict[str, Any] = {
        "runner": "governed-objects-conformance runner (python)",
        "runner_python": sys.version.split()[0],
        "os_family": platform.system() or "unknown",
        "architecture": platform.machine() or "unknown",
        "suite_version": suite_version,
    }
    if local_detail:
        env["local_detail"] = {"platform": platform_string, "invocation": invocation}
    return env


LOCAL_DETAIL_WARNING = (
    "WARNING: this bundle was produced with --include-local-detail. It contains local machine detail "
    "(paths, platform string, invocation and source-control metadata) and should be reviewed before sharing."
)
