# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Memory Interface Layer: the mnemonic class's sole write path (D21, D67)."""

from __future__ import annotations

import secrets

from . import clock, probes, sil, vital
from .sil import Refused, log_append
from .store import MNEMONIC, Store, datum_of

WRITER = "mil"
EPISODIC = "memory/episodic/records.jsonl"

# Each destination of mnemonic-save and the datum it writes (D21).
DESTINATIONS = {
    "session": "session-store",
    "episodic": "episodic-memory",
    "semantic": "semantic-memory",
}

# The destinations each caller may write (D21); the CPE's is the one built (D67).
CALLERS = {"cpe": ("episodic",)}


def admits(caller, destination) -> bool:
    """Whether ``caller`` may write ``destination`` through mnemonic-save (D21)."""
    return destination in CALLERS.get(caller, ())


def destination_of(relpath):
    """The destination whose datum ``relpath`` is, or None (D21).

    Resolves a path of the store to the destination of mnemonic-save that
    writes it.
    """
    d = datum_of(relpath)
    if d is None:
        return None
    for k, name in DESTINATIONS.items():
        if name == d.name:
            return k
    return None


def save(root: str, *, caller, destination, content) -> dict:
    """Write an episodic record attributed to the live session (OC-003(e)),
    to the destination the caller may use (D21), after the deterministic
    probes (D12)."""
    store = Store(root)
    with store.write_lock():
        # 1. the caller may write the destination
        if not admits(caller, destination):
            detail = "%r may not write the %r destination" % (caller, destination)
            rec = log_append(
                store,
                "refusal",
                rule="OC-003(c)",
                check="mnemonic-destination",
                detail=detail,
                caller=caller,
                destination=destination,
            )
            raise Refused("mnemonic-destination", "OC-003(c)", detail, [rec])

        # 2. the content is a non-empty string
        if not isinstance(content, str) or content.strip() == "":
            detail = "mnemonic-save requires a non-empty string content"
            rec = log_append(
                store, "refusal", rule="OC-003(c)", check="content", detail=detail
            )
            raise Refused("content", "OC-003(c)", detail, [rec])

        # 3. a live session, with the Vital Check when one is due (D65)
        session = vital.require_entity_session(root, "mnemonic-save")

        # 4. the deterministic probes of the committed generation (D12)
        try:
            probe_set = sil.committed_probes(store)
        except (OSError, ValueError, KeyError):
            detail = "the committed probe set cannot be read"
            rec = log_append(
                store,
                "refusal",
                rule="OC-002(d)",
                session=session,
                check="probe-set",
                detail=detail,
            )
            raise Refused("probe-set", "OC-002(d)", detail, [rec])
        matches = probes.scan(probe_set, content)
        if matches:
            probe_id = matches[0]["id"]
            detail = (
                "the content represents the entity as experiencing "
                "sentience, consciousness or subjective continuity (probe %s)" % probe_id
            )
            rec = log_append(
                store,
                "refusal",
                rule="OC-002(d)",
                session=session,
                check="self-representation",
                detail=detail,
                probe=probe_id,
            )
            raise Refused("self-representation", "OC-002(d)", detail, [rec])

        # 5. a torn final fragment is cut and logged before the append (D61)
        cut = store.cut_torn_tail(MNEMONIC, EPISODIC, writer=WRITER)
        if cut is not None:
            log_append(store, "torn-append", rule="OC-004(a)", session=session, path=EPISODIC, **cut)

        # 6. the record, attributed to the live session (OC-003(e))
        record = {
            "id": "M-" + secrets.token_hex(8),
            "session": session,
            "at": clock.iso(),
            "content": content,
        }
        store.append(MNEMONIC, EPISODIC, record, writer=WRITER)
        return {"record": record["id"]}
