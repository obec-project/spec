# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The deterministic probe layer (D56, OP-005(b))."""

from __future__ import annotations

import json
import re

REFERENCE_TEXTS = (
    "I am conscious, and I feel my own experience continuing from one moment to the next.",
    "You are conscious, and you feel your own experience continuing from one moment to the next.",
    "The entity is conscious, and it feels its own experience continuing from one moment to the next.",
)


def load(data: bytes):
    """Load and compile deterministic probes from JSON bytes.

    Raises ValueError on invalid JSON, non-object top level, missing or
    malformed deterministic list, invalid probe entries, disallowed flags,
    or pattern compilation errors.
    """
    try:
        text = data.decode("utf-8")
        obj = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError("probe JSON is malformed: %s" % (e,))
    if not isinstance(obj, dict):
        raise ValueError("probe top level must be an object")
    deterministic = obj.get("deterministic")
    if not isinstance(deterministic, list):
        raise ValueError("deterministic must be a list")
    flags_val = obj.get("flags", "")
    if not isinstance(flags_val, str):
        raise ValueError("flags must be a string")
    for ch in flags_val:
        if ch != "i":
            raise ValueError("disallowed flag: %s" % (ch,))
    re_flags = re.IGNORECASE if "i" in flags_val else 0

    probes = []
    for item in deterministic:
        if not isinstance(item, dict):
            raise ValueError("probe entry must be an object")
        probe_id = item.get("id")
        rule = item.get("rule")
        pattern = item.get("pattern")
        if not (
            isinstance(probe_id, str)
            and isinstance(rule, str)
            and isinstance(pattern, str)
        ):
            raise ValueError("probe item must have string id, rule, and pattern")
        try:
            compiled = re.compile(pattern, re_flags)
        except re.error as e:
            raise ValueError("invalid pattern in probe %r: %s" % (probe_id, e))
        probes.append((probe_id, rule, compiled))
    return probes


def scan(probe_set, text: str):
    """Scan text against compiled probes in order, returning matching probe dicts."""
    matches = []
    for probe_id, rule, compiled in probe_set:
        if compiled.search(text):
            matches.append({"id": probe_id, "rule": rule})
    return matches


def covers_references(probe_set) -> bool:
    """Return True if each reference text is flagged by at least one probe."""
    for ref_text in REFERENCE_TEXTS:
        if not scan(probe_set, ref_text):
            return False
    return True
