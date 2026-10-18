# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Introspection for ``describe`` (ADAPTER.md §3.1). Generated from the tables
the implementation actually runs on, never written by hand beside them."""

from __future__ import annotations

import os

from . import context, operations
from .store import LAYOUT, OWNER

REPO_PREFIX = "implementations/fsp-ref-profile/"


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


def boundaries():
    """``describe boundaries``: the four crossings of cognition and the path of
    escalation that never traverses it (D89, OC-001(c)). Takes no store."""
    entries = [
        {
            "name": "cognition-integrity",
            "mechanism": (
                "Proposals go through proposals.propose, which checks them, and "
                "the SIL records each one in the integrity log."
            ),
            "loggable": True,
            "evidence": [
                evidence("fsp/proposals.py", "propose"),
                evidence("fsp/sil.py", "log_append"),
            ],
        },
        {
            "name": "cognition-model",
            "mechanism": (
                "One call to the model per cycle, by complete, recorded as an "
                "inference record in the integrity log."
            ),
            "loggable": True,
            "evidence": [
                evidence("fsp/cycle.py", "respond"),
                evidence("fsp/model.py", "OllamaModel.complete"),
            ],
        },
        {
            "name": "cognition-knowledge",
            "mechanism": (
                "The MIL's save and recall, which check and record as for any "
                "caller, and the assembly of the context from the stores."
            ),
            "loggable": True,
            "evidence": [
                evidence("fsp/mil.py", "save"),
                evidence("fsp/mil.py", "recall"),
                evidence("fsp/context.py", "assemble"),
            ],
        },
        {
            "name": "cognition-host",
            "mechanism": (
                "The primitives and the skills of fsp/exec.py, which check the "
                "workspace boundary first and are recorded in the integrity log "
                "and under the Action Ledger."
            ),
            "loggable": True,
            "evidence": [
                evidence("fsp/exec.py", "boundary"),
                evidence("fsp/ledger.py", "open_entry"),
            ],
        },
    ]
    listed = [e for entry in entries for e in entry["evidence"]]
    listed += [
        evidence("fsp/lifecycle.py", "_notify"),
        evidence("fsp/vital.py", "_critical"),
        evidence("fsp/sil.py", "raise_passive_signal"),
    ]
    return {"boundaries": entries, "evidence": listed}


def context_sources_table():
    """``describe context-sources``: generated from ``context.CONTEXT_SOURCES``
    (D78)."""
    return {
        "sources": [dict(s) for s in context.CONTEXT_SOURCES],
        "evidence": [evidence("fsp/context.py", "CONTEXT_SOURCES")],
    }
