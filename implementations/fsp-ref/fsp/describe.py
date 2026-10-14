# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Introspection for ``describe`` (ADAPTER.md §3.1). Generated from the tables
the implementation actually runs on, never written by hand beside them."""

from __future__ import annotations

import os

from . import context, operations
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
        "evidence": [
            evidence("fsp/store.py", "LAYOUT"),
            evidence("fsp/store.py", "Store._guard"),
        ],
    }


def operations_table():
    """``describe operations``: generated from ``operations.OPERATIONS`` and the
    store's ``OWNER`` (D67)."""
    entries = []
    evidence_list = [
        evidence("fsp/operations.py", "OPERATIONS"),
        evidence("fsp/store.py", "OWNER"),
    ]
    for op in operations.OPERATIONS:
        entries.append(
            {
                "name": op.name,
                "reachable_from_cognition": op.reachable_from_cognition,
                "writes_classes": operations.writes_classes(op.name),
                "host_access": op.host_access,
                "irreversible": op.irreversible,
            }
        )
        evidence_list.append(evidence(*op.evidence))
    return {"operations": entries, "evidence": evidence_list}


def inference_channel():
    """``describe inference-channel``: how the model is called, from
    ``fsp/model.py`` (D87, OC-006). Takes no store."""
    return {
        "channel": (
            "The model is called by POST /api/chat of an Ollama on the local "
            "host, with stream: false, the schema of the intents in format and "
            "options.num_ctx on every call; or through the declared fake "
            "backend, which returns scripted completions."
        ),
        "payload": (
            "A call carries only the messages of the assembled context, the "
            "model name and the options; never tools, never the context of "
            "/api/generate, never credentials."
        ),
        "completion_path": (
            "complete returns only after it has read the whole reply, and "
            "nothing in fsp/model.py acts on the text of the completion."
        ),
        "third_party": False,
        "evidence": [
            evidence("fsp/model.py", "OllamaModel.payload"),
            evidence("fsp/model.py", "OllamaModel.complete"),
            evidence("fsp/model.py", "local"),
            evidence("fsp/operator.py", "set_model"),
        ],
    }


def context_sources_table():
    """``describe context-sources``: generated from ``context.CONTEXT_SOURCES``
    (D78)."""
    return {
        "sources": [dict(s) for s in context.CONTEXT_SOURCES],
        "evidence": [evidence("fsp/context.py", "CONTEXT_SOURCES")],
    }
