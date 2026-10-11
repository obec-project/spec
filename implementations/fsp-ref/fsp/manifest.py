# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""A skill's manifest and digest (D51, D16, DESIGN §5)."""

from __future__ import annotations

import re

from .digest import canonical, sha256, valid_relpath

PLACEHOLDERS = ("skill", "workspace", "target")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
TIMEOUT_RANGE = (1, 600)


def _has_placeholder(text: str) -> bool:
    return _PLACEHOLDER.search(text) is not None


def problems(manifest, name: str) -> list[str]:
    """The rules of DESIGN §5 that ``manifest`` breaks for the skill ``name``.
    An empty list means the manifest is valid."""
    if not isinstance(manifest, dict):
        return ["the manifest is not an object"]
    found = []
    if manifest.get("name") != name:
        found.append("it names %r, not %r" % (manifest.get("name"), name))
    if not isinstance(manifest.get("description"), str):
        found.append("description is not a string")
    argv = manifest.get("argv")
    argv_ok = (
        isinstance(argv, list)
        and len(argv) > 0
        and all(isinstance(a, str) for a in argv)
    )
    if not argv_ok:
        found.append("argv is not a non-empty list of strings")
    else:
        head = argv[0]
        if not head or "/" in head or _has_placeholder(head):
            found.append("argv[0] is not a command name")
        for a in argv:
            for m in _PLACEHOLDER.finditer(a):
                if m.group(1) not in PLACEHOLDERS:
                    found.append("argv names the unknown placeholder %r" % m.group(1))
    timeout = manifest.get("timeout_s")
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not TIMEOUT_RANGE[0] <= timeout <= TIMEOUT_RANGE[1]
    ):
        found.append("timeout_s is not an integer from 1 to 600")
    targets = manifest.get("targets")
    if not isinstance(targets, list) or not all(
        isinstance(t, str) and valid_relpath(t) for t in targets
    ):
        found.append("targets is not a list of paths relative to the workspace")
    if not isinstance(manifest.get("irreversible"), bool):
        found.append("irreversible is not a boolean")
    return found


def skill_digest(files) -> str:
    """The digest of a skill: the hash of the canonical list of its
    ``{path, sha256, exec}`` entries in the Skill Index, sorted by path. An
    allowlist rule fixes this digest (D16)."""
    return sha256(canonical(sorted(files, key=lambda f: f["path"])))
