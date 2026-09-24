# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Introspection for ``describe`` (ADAPTER.md §3.1). Generated from the tables
the implementation actually runs on, never written by hand beside them."""

from __future__ import annotations

import os

from .store import LAYOUT, OWNER

REPO_PREFIX = "implementations/fsp-ref/"


def evidence(path: str, symbol: str) -> dict:
    return {"path": REPO_PREFIX + path, "symbol": symbol}


def state(root: str):
    root = os.path.abspath(root)
    entries = []
    for d in LAYOUT:
        entries.append(
            {
                "name": d.name,
                "class": d.cls,
                "inside_store": True,
                "path": os.path.join(root, *d.pattern.split("/")),
                "write_path": OWNER[d.cls][1],
                "form": d.form,
            }
        )
    return {
        "state": entries,
        "evidence": [evidence("fsp/store.py", "LAYOUT"), evidence("fsp/store.py", "Store._guard")],
    }
