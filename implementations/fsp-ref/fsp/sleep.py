# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Sleep phase of the Closure that follows a normal close (D83, OP-022)."""

from __future__ import annotations

from . import sil
from .sil import Refused, log_append
from .store import Store


def run(store: Store, session, *, rerun=False):
    """Run the Sleep of ``session`` with the write lock held (D83).

    The stages are the consolidation of a Closure Payload (D84), the garbage
    collection when the session's records end the conversation, which keeps
    everything (D84, OP-009(h)), and promotion (D81): each pending request the
    semantic ledger does not name yet goes through ``mil.promote``. A refused
    promotion is recorded and the Sleep goes on; any other failure propagates.
    ``sleep-complete`` names whether this is a re-run, what was promoted and
    refused, the payload consolidated and the digest of the Resumption Record.
    The log checkpoint belongs to the Integrity phase (D83).
    """
    from . import mil  # imported here to avoid an import cycle

    consolidated = mil.consolidate(store, session)
    if mil.conversation_left(store, session):
        log_append(
            store,
            "gc",
            rule="OP-009(h)",
            session=session,
            retention="keep-all",
            expired=[],
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
    closure = consolidated["closure"] if consolidated else None
    resumption = consolidated["resumption"] if consolidated else None
    loc = sil.log_append_located(
        store,
        "sleep-complete",
        rule="OP-022(a)",
        session=session,
        rerun=rerun,
        promoted=promoted,
        refused=refused,
        closure=closure,
        resumption=resumption,
    )
    return {
        "promoted": promoted,
        "refused": refused,
        "consolidation": consolidated,
        "closure": closure,
        "resumption": resumption,
        "log_records": [loc["id"]],
    }
