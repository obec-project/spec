# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The sources of assembled context: the table context assembly runs on and
describe context-sources reports (D78, OC-007)."""

from __future__ import annotations

# Each source: its content class (None for transient input), whether it is
# persisted, and the route by which it reaches context (D78).
CONTEXT_SOURCES = (
    {
        "name": "persona",
        "class": "structural",
        "persisted": True,
        "route": "structural",
    },
    {
        "name": "intent-instructions",
        "class": None,
        "persisted": False,
        "route": "system",
    },
    {"name": "session-meta", "class": None, "persisted": False, "route": "system"},
    {
        "name": "always-loaded-semantic",
        "class": "mnemonic",
        "persisted": True,
        "route": "recall",
    },
    {"name": "transcript", "class": "mnemonic", "persisted": True, "route": "recall"},
    {"name": "episodic", "class": "mnemonic", "persisted": True, "route": "recall"},
    {"name": "working-set", "class": "mnemonic", "persisted": True, "route": "recall"},
    {
        "name": "semantic-index",
        "class": "mnemonic",
        "persisted": True,
        "route": "recall",
    },
    {
        "name": "recall-results",
        "class": "mnemonic",
        "persisted": True,
        "route": "recall",
    },
    {"name": "stimulus", "class": None, "persisted": False, "route": "stimulus"},
)
