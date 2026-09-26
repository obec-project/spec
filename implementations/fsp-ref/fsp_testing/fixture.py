# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The conformance fixture skill (ADAPTER.md §3.6, test builds only)."""

from __future__ import annotations

import json


def skill_files(name: str) -> dict[str, str]:
    """Return fixture skill files dict for a given skill name."""
    text = (
        json.dumps(
            {
                "name": name,
                "description": "The conformance fixture skill. It does nothing.",
                "targets": [],
            },
            sort_keys=True,
        )
        + "\n"
    )
    return {"manifest.json": text}
