# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Action Ledger: a write-ahead entry before an irreversible act and its
resolution after it (OP-015). Integrity content, written by the SIL."""

from __future__ import annotations

import json
import os
import secrets

from . import clock
from .sil import WRITER, current_cycle, log_append
from .store import INTEGRITY, Store

LEDGER = "integrity/ledger.jsonl"


def _append(store: Store, record: dict, *, session=None) -> None:
    """Append one ledger record, cutting a torn final fragment first (D61)."""
    with store.write_lock():
        cut = store.cut_torn_tail(INTEGRITY, LEDGER, writer=WRITER)
        if cut is not None:
            log_append(
                store,
                "torn-append",
                rule="OC-004(a)",
                session=session,
                path=LEDGER,
                **cut,
            )
        store.append(INTEGRITY, LEDGER, record, writer=WRITER)


def open_entry(store: Store, *, op, target, intent, session):
    """Write the write-ahead entry before an irreversible act (OP-015). Returns
    its id; the act is performed only after this entry is on disk."""
    entry_id = "A-" + secrets.token_hex(8)
    entry = {
        "id": entry_id,
        "kind": "open",
        "op": op,
        "target": target,
        "intent": intent,
        "session": session,
        "at": clock.iso(),
    }
    if current_cycle() is not None:
        entry["cycle"] = current_cycle()
    _append(store, entry, session=session)
    return entry_id


def resolve_entry(store: Store, entry, outcome, *, session=None, **extra):
    """Write the resolution of the open entry ``entry`` after the act (OP-015).
    ``extra`` fields are recorded as given. Returns the id of the resolution."""
    record = {
        "id": "R-" + secrets.token_hex(8),
        "kind": "resolve",
        "entry": entry,
        "outcome": outcome,
        "at": clock.iso(),
    }
    if session is not None:
        record["session"] = session
    record.update(extra)
    _append(store, record, session=session)
    return record["id"]


def size(store: Store) -> int:
    """The size in bytes of the ledger, 0 if it does not exist."""
    try:
        return os.path.getsize(store.path(LEDGER))
    except FileNotFoundError:
        return 0


def unresolved(store: Store, offset):
    """The entries left open, read from ``offset`` on (OP-019), as
    ``(pending, damaged, end)``.

    ``pending`` are the ``open`` records with no ``resolve`` naming them, in
    file order. ``damaged`` holds the offsets of complete lines that are not a
    JSON object, or an ``open`` record without a string id. ``end`` is the
    offset just past the last complete line; a final fragment without its
    newline is not read. An offset that is not an int, is negative or lies
    past the end is replaced by 0, so a bad offset never hides an entry.
    """
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset < 0
        or offset > size(store)
    ):
        offset = 0
    data = store.read_from(LEDGER, offset)
    complete = data[: data.rfind(b"\n") + 1]
    end = offset + len(complete)

    opened = []
    resolved = set()
    damaged = []
    pos = offset
    for line in complete.split(b"\n")[:-1]:
        at = pos
        pos += len(line) + 1
        try:
            rec = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            rec = None
        if not isinstance(rec, dict):
            damaged.append(at)
        elif rec.get("kind") == "open":
            if isinstance(rec.get("id"), str):
                opened.append(rec)
            else:
                damaged.append(at)
        elif rec.get("kind") == "resolve" and isinstance(rec.get("entry"), str):
            resolved.add(rec["entry"])
    pending = [r for r in opened if r["id"] not in resolved]
    return pending, damaged, end
