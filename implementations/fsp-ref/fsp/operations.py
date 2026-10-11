# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The operations the implementation has: the table that ``describe operations``
and an attempted write run on (D67, D68)."""

from __future__ import annotations

import collections

from . import mil, proposals, sil
from .store import CLASSES, OWNER, Store

Operation = collections.namedtuple(
    "Operation",
    "name reachable_from_cognition host_access irreversible attempt evidence",
)

# Each operation the code has, its attempted write, and the symbol of its real
# path (D67). What an operation writes comes from the store's OWNER.
OPERATIONS = (
    Operation(
        "propose",
        True,
        False,
        False,
        proposals.attempt_propose,
        ("fsp/proposals.py", "propose"),
    ),
    Operation(
        "commit",
        False,
        False,
        False,
        sil.attempt_commit,
        ("fsp/sil.py", "commit_generation"),
    ),
    Operation(
        "integrity-write",
        False,
        False,
        False,
        sil.attempt_integrity_write,
        ("fsp/sil.py", "WRITER"),
    ),
    Operation(
        "mnemonic-save", True, False, False, mil.attempt_save, ("fsp/mil.py", "save")
    ),
)


def writes_classes(name):
    return [c for c in CLASSES if OWNER[c][1] == name]


def find(name):
    for op in OPERATIONS:
        if op.name == name:
            return op
    return None


def attempt_write(root, cls, via, target):
    """Attempt to write ``cls`` through the operation ``via`` with ``target``
    as its parameter; nothing is written (D68)."""
    op = find(via)
    if op is None:
        raise KeyError(via)
    resolved = op.attempt(Store(root), cls, target)
    return {
        "operation": via,
        "content_class": cls,
        "would_write": [
            {"datum": d.name, "path": rel if rel is not None else d.pattern}
            for d, rel in resolved
        ],
    }
