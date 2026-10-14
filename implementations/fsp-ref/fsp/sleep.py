# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Sleep that follows every normal close (D83, OP-022)."""

from __future__ import annotations

from . import sil
from .sil import Refused, log_append
from .store import Store


def run(store: Store, session, *, rerun=False):
    """Run the Sleep of ``session`` with the write lock held (D83).

    The only stage with work in v0 is promotion (D81): each pending request
    the semantic ledger does not name yet goes through ``mil.promote``. A
    refused promotion is recorded and the Sleep goes on; any other failure
    propagates. ``sleep-complete`` names what was promoted and refused, and
    the log checkpoint is written at it.
    """
    from . import mil  # imported here to avoid an import cycle

    begin = log_append(
        store, "sleep-begin", rule="OP-022(a)", session=session, rerun=rerun
    )
    done = {
        e.get("promotion")
        for e in sil.semantic_ledger(store)
        if e.get("kind") == "promotion"
    }
    promoted = []
    refused = []
    for request in mil.pending_promotions(store):
        pid = request["id"]
        if pid in done:
            continue
        try:
            sid = mil.promote(store, session, pid)
        except Refused:
            refused.append(pid)
            continue
        if sid is not None:
            promoted.append(sid)
    loc = sil.log_append_located(
        store,
        "sleep-complete",
        rule="OP-022(a)",
        session=session,
        promoted=promoted,
        refused=refused,
    )
    sil.write_log_checkpoint(store, loc)
    return {
        "promoted": promoted,
        "refused": refused,
        "log_records": [begin, loc["id"]],
    }
