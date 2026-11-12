# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Adapter self-declaration (CONF-CLAIM-001 inputs), read from the ``capabilities`` response.

Everything here is SELF-DECLARED by the adapter. The runner validates the shape only; it
never inspects the implementation, its source or how it was built."""

from __future__ import annotations

from typing import Any

# A claim-supporting bundle needs a concrete implementation version. Third-party version
# formats vary, so semantic versioning is not required; only empty values and these
# placeholder prefixes (case-insensitive) are refused.
PLACEHOLDER_VERSION_PREFIXES = ("unversioned", "unknown", "dev")


def version_problem(version: object) -> str | None:
    """Why ``version`` cannot appear in a claim, or None if it is a concrete version."""
    if not isinstance(version, str) or not version.strip():
        return "implementation version is empty"
    lowered = version.strip().lower()
    for prefix in PLACEHOLDER_VERSION_PREFIXES:
        if lowered.startswith(prefix):
            return f"implementation version {version!r} is a placeholder (starts with {prefix!r})"
    return None


# Optional adapter-supplied metadata about how the adapter or implementation was built.
# The runner records it verbatim and never uses it to judge validity.
OPTIONAL_BUILD_KEY = "build"


def extract_declaration(caps: dict[str, Any], manifest: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return (declaration, problems). ``problems`` empty means the declaration is complete
    and names the revision this suite targets."""
    problems: list[str] = []
    impl = caps.get("implementation")
    name = version = None
    if not isinstance(impl, dict):
        problems.append("capabilities.implementation is missing (object with name and version expected)")
    else:
        name, version = impl.get("name"), impl.get("version")
        for key, val in (("name", name), ("version", version)):
            if not isinstance(val, str) or not val.strip():
                problems.append(f"capabilities.implementation.{key} must be a non-empty string")
    revision = caps.get("spec_revision")
    expected = manifest["spec_revision_label"]
    if revision != expected:
        problems.append(f"capabilities.spec_revision is {revision!r}, this suite targets {expected!r}")
    spec_version = caps.get("spec_version")
    if spec_version != manifest["spec_version"]:
        problems.append(f"capabilities.spec_version is {spec_version!r}, this suite targets {manifest['spec_version']!r}")
    if caps.get("core_claimed") is not True:
        problems.append("capabilities.core_claimed must be true to run the Core target")
    profiles = caps.get("profiles_claimed")
    if not isinstance(profiles, list) or not all(isinstance(p, str) for p in profiles):
        problems.append("capabilities.profiles_claimed must be a list of profile names (possibly empty)")
        profiles = []
    declaration = {
        "self_declared": True,
        "implementation": {"name": name, "version": version},
        "spec_version": spec_version,
        "spec_revision": revision,
        "core_claimed": caps.get("core_claimed"),
        "profiles_claimed": profiles,
        # Conditional-capability claims are the remaining capability fields (replay_types,
        # restoration, create_with_relationships, ...), which the scenarios' applicability
        # triggers read. They are kept in the verbatim capabilities record.
        "optional_build_metadata": caps.get(OPTIONAL_BUILD_KEY),
    }
    return declaration, problems


# The boolean conditional-capability fields scenarios trigger on (docs/adapter-guide.md).
# Non-boolean fields (version_token_grammar, declared_refusals, actors, ...) are parameters
# of a claimed capability, not claims of their own, and are not named here.
CONDITIONAL_CAPABILITY_FIELDS = (
    "replay",
    "mutable_objects",
    "unconditional_mutation",
    "relationship_add",
    "relationship_remove",
    "restart",
    "governance_reconfiguration",
    "harness_clock",
    "restoration",
    "create_with_relationships",
    "expected_version_required",
    "type_version_exposed",
    "semantic_portability_view",
    "concurrent_invocation",
)


def claimed_capabilities(caps: dict[str, Any]) -> list[str]:
    """Conditional capabilities the adapter claimed (CONF-CLAIM-001 item 3: the claim text
    must name each conditional capability claimed)."""
    return sorted(name for name in CONDITIONAL_CAPABILITY_FIELDS if caps.get(name) is True)
