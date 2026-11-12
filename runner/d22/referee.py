# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Implementation-neutral checks over raw caller-visible results and observer views.

Two channels are kept apart:

* ``caller_result`` is the raw value the runtime API returned to the requester.
  Disclosure and invariance checks look only here.
* ``semantic_view`` is the administrative observer channel (``channel:
  observer``). It supplies the protected values and the canonical history a
  check compares against, and is never treated as requester-visible.

Values are compared as raw JSON: an absent key, ``null``, an empty container and
a populated value are four different observations.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

_ABSENT = object()

VERSION_KEY = re.compile(r"^(object|resulting|actual|expected|current|previous|new)?version(highwater)?$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_MIN_PROTECTED_STRING = 3


def normalize_key(key: str) -> str:
    return key.replace("_", "").replace("-", "").lower()


def is_version_key(key: str) -> bool:
    return bool(VERSION_KEY.match(normalize_key(key)))


def walk(value: Any, path: str = "$") -> Iterator[tuple[str, str | None, Any]]:
    """Yield (path, parent_key, leaf) for every scalar leaf."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if isinstance(child, (dict, list)):
                yield from walk(child, child_path)
            else:
                yield child_path, key, child
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            child_path = f"{path}[{idx}]"
            if isinstance(child, (dict, list)):
                yield from walk(child, child_path)
            else:
                yield child_path, None, child
    else:
        yield path, None, value


def scalar_leaves(value: Any) -> set[Any]:
    out: set[Any] = set()
    for _, _, leaf in walk(value):
        if leaf is None or isinstance(leaf, bool):
            continue
        out.add(leaf)
        if isinstance(leaf, str) and leaf.isdigit():
            out.add(int(leaf))
        elif isinstance(leaf, int):
            out.add(str(leaf))
    return out


def as_token(value: Any) -> Any:
    """Object Version as an opaque JSON scalar, compared only by equality.

    An int or a non-empty string is a token, returned unchanged; anything
    else (``None``, a bool, an empty string, a container) is not a token."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value != "":
        return value
    return None


def as_decimal(value: Any) -> int | None:
    """Canonical int for a decimal integer, whether given as a JSON number or (for
    values some languages cannot represent exactly as a JSON number, such as
    ``object_version_ceiling``) as a decimal string. Used only to compare a
    self-declared numeric capability against an observed value. Ordinary Object
    Version comparison uses the opaque ``as_token`` instead."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def fidelity(container: Any, key: str) -> str:
    """Classify a field as absent | null | empty | value."""
    if not isinstance(container, dict) or key not in container:
        return "absent"
    val = container[key]
    if val is None:
        return "null"
    if val in ("", [], {}):
        return "empty"
    return "value"


# --- protected information --------------------------------------------------


def history_of(view: dict[str, Any] | None) -> list[dict[str, Any]]:
    hist = (view or {}).get("canonical_history_summary")
    return hist if isinstance(hist, list) else []


def protected_values(view: dict[str, Any] | None) -> dict[str, set[Any]]:
    """Protected information about the target object (AUTH-DISCLOSE-001):
    current and historical Object Versions, Accepted Canonical State including
    lifecycle state, Canonical Relationships and Canonical History content."""
    tokens: set[Any] = set()
    strings: set[str] = set()
    if not view:
        return {"tokens": tokens, "strings": strings}
    cur = as_token(view.get("object_version"))
    if cur is not None:
        tokens.add(cur)
    for entry in history_of(view):
        tok = as_token(entry.get("object_version"))
        if tok is not None:
            tokens.add(tok)
        for key in ("relationship_type", "relationship_target"):
            if isinstance(entry.get(key), str):
                strings.add(entry[key])
    for val in (view.get("accepted_state") or {}).values():
        if isinstance(val, str):
            strings.add(val)
    for rel in view.get("relationships") or []:
        for key in ("type", "target"):
            if isinstance(rel.get(key), str):
                strings.add(rel[key])
    strings = {s for s in strings if len(s) >= _MIN_PROTECTED_STRING}
    return {"tokens": tokens, "strings": strings}


def _volatile(leaf: Any) -> bool:
    return isinstance(leaf, str) and bool(_TIMESTAMP.match(leaf) or _UUID.match(leaf))


def find_disclosures(
    caller_result: Any,
    protected: dict[str, set[Any]],
    requester_supplied: Any,
) -> list[str]:
    """Return every place a protected value appears in the caller-visible result.

    Requester-supplied content is not protected (AUTH-DISCLOSE-001), so any
    value the requester sent is excluded. Numbers match equal tokens; strings
    match protected tokens and protected strings as whole words."""
    supplied = scalar_leaves(requester_supplied)
    tokens = {t for t in protected["tokens"] if t not in supplied and str(t) not in supplied}
    int_tokens = {t for t in tokens if isinstance(t, int)}
    str_tokens = {t for t in tokens if isinstance(t, str)}
    strings = {s for s in protected["strings"] if s not in supplied}
    word_patterns = [(s, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(s)}(?![A-Za-z0-9_])")) for s in strings]
    str_token_patterns = [(t, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])")) for t in str_tokens]
    int_token_patterns = [(t, re.compile(rf"(?<![0-9]){t}(?![0-9])")) for t in int_tokens]
    leaks: list[str] = []
    for path, _, leaf in walk(caller_result):
        if leaf is None or isinstance(leaf, bool):
            continue
        if isinstance(leaf, (int, float)):
            if leaf in int_tokens:
                leaks.append(f"{path}={leaf!r} (Object Version)")
            continue
        if not isinstance(leaf, str) or _volatile(leaf):
            continue
        if leaf in supplied:
            continue
        if leaf in str_tokens:
            leaks.append(f"{path}={leaf!r} (Object Version)")
            continue
        if leaf.isdigit() and int(leaf) in int_tokens:
            leaks.append(f"{path}={leaf!r} (Object Version)")
            continue
        for s, pat in word_patterns:
            if pat.search(leaf):
                leaks.append(f"{path}={leaf!r} (protected value {s!r})")
        for t, pat in str_token_patterns:
            if pat.search(leaf):
                leaks.append(f"{path}={leaf!r} (Object Version {t!r} in text)")
        for t, pat in int_token_patterns:
            if pat.search(leaf):
                leaks.append(f"{path}={leaf!r} (Object Version {t} in text)")
    return leaks


# --- outcome and content invariance -----------------------------------------


def normalize_for_invariance(caller_result: Any, requester_supplied: Any) -> Any:
    """Mask content that AUTH-DISCLOSE-001 allows to vary: values the requester
    supplied, and volatile request identifiers and timestamps."""
    supplied = scalar_leaves(requester_supplied)

    def norm(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: norm(v) for k, v in value.items()}
        if isinstance(value, list):
            return [norm(v) for v in value]
        if value is None or isinstance(value, bool):
            return value
        if value in supplied:
            return "<requester>"
        if _volatile(value):
            return "<volatile>"
        return value

    return norm(caller_result)


REQUESTER = "<requester>"


def _requester_echo(a: Any, b: Any) -> bool:
    """An echo of requester content in one variant against nothing in another
    varies only with the request. Variants that both supply content must still
    match exactly, so a stale/current token oracle is not masked."""
    return (a == REQUESTER and b in (None, _ABSENT)) or (b == REQUESTER and a in (None, _ABSENT))


def first_difference(left: Any, right: Any, path: str = "$") -> str | None:
    if _requester_echo(left, right):
        return None
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            a = left.get(key, _ABSENT)
            b = right.get(key, _ABSENT)
            if a is _ABSENT or b is _ABSENT:
                if _requester_echo(a, b):
                    continue
                return f"{path}.{key}: {'absent' if a is _ABSENT else repr(a)} vs {'absent' if b is _ABSENT else repr(b)}"
            diff = first_difference(a, b, f"{path}.{key}")
            if diff:
                return diff
        return None
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} vs {len(right)}"
        for idx, (a, b) in enumerate(zip(left, right)):
            diff = first_difference(a, b, f"{path}[{idx}]")
            if diff:
                return diff
        return None
    if left != right or type(left) is not type(right):
        return f"{path}: {left!r} vs {right!r}"
    return None


# --- lineage -----------------------------------------------------------------


def exposed_versions(
    caller_result: Any, requester_supplied: Any, grammar: str | None
) -> list[tuple[str, int]]:
    """Object Versions a result exposes: values under version-bearing keys that
    are in the declared token grammar and were not supplied by the requester."""
    supplied = scalar_leaves(requester_supplied)
    pattern = re.compile(grammar) if grammar else None
    out: list[tuple[str, int]] = []
    for path, key, leaf in walk(caller_result):
        if key is None or not is_version_key(key):
            continue
        tok = as_token(leaf)
        if tok is None or tok in supplied or str(tok) in supplied:
            continue
        if pattern is not None and not pattern.fullmatch(str(tok)):
            continue
        out.append((path, tok))
    return out


def history_versions(history: list[dict[str, Any]]) -> list[Any]:
    return [entry.get("object_version") for entry in history]


def lineage_violations(
    history: list[dict[str, Any]],
    current_version: Any,
    exposures: list[tuple[str, str, int]],
) -> list[str]:
    """CORE-LINEAGE-001 / CON-UNIQUE-001 over one object's observed history.

    ``exposures`` are (step, path, token) triples from caller results."""
    problems: list[str] = []
    versions = history_versions(history)
    for idx, ver in enumerate(versions):
        if as_token(ver) is None:
            problems.append(f"history entry {idx} has no Object Version ({ver!r})")
    seen: dict[int, int] = {}
    for idx, ver in enumerate(versions):
        tok = as_token(ver)
        if tok is None:
            continue
        if tok in seen:
            problems.append(f"Object Version {tok} identifies history entries {seen[tok]} and {idx}")
        else:
            seen[tok] = idx
    if versions:
        if as_token(current_version) != as_token(versions[-1]):
            problems.append(
                f"current Object Version {current_version!r} is not the last revision's {versions[-1]!r}"
            )
    elif current_version is not None:
        problems.append(f"current Object Version {current_version!r} but no history")
    known = set(seen)
    for step, path, tok in exposures:
        if tok not in known:
            problems.append(f"step {step} exposed Object Version {tok} at {path}, which is no revision in history")
    return problems


def history_projection(history: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    return [{k: entry.get(k) for k in keys} for entry in history]


def order_follows_timestamps_violation(
    history: list[dict[str, Any]], expected_effect_order: list[str]
) -> str | None:
    """EVT-ORDER-001: order is acceptance order, not a timestamp sort."""
    effects = [entry.get("effect") for entry in history]
    if effects != expected_effect_order:
        return f"history order {effects} differs from acceptance order {expected_effect_order}"
    return None
