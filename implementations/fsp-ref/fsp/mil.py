# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Memory Interface Layer: the mnemonic class's sole write path (D21, D67)."""

from __future__ import annotations

import json
import re
import secrets

from . import clock, probes, sil, vital
from .sil import Refused, log_append
from .store import MNEMONIC, GuardError, Store, datum_of

WRITER = "mil"
EPISODIC = "memory/episodic/records.jsonl"

# Each destination of mnemonic-save and the datum it writes (D21).
DESTINATIONS = {
    "session": "session-store",
    "episodic": "episodic-memory",
    "semantic": "semantic-memory",
}

# The destinations each caller may write (D21); the CPE's is the one built (D67).
CALLERS = {"cpe": ("episodic",), "orchestrator": ("session",)}

# The kinds of record a session's file holds (D78) and the session ids (D46).
SESSION_KINDS = ("session-open", "stimulus", "transcript-cleared", "conversation-left")
SESSION_ID = re.compile(r"^s-[0-9]+\Z")


def admits(caller, destination) -> bool:
    """Whether ``caller`` may write ``destination`` through mnemonic-save (D21)."""
    return destination in CALLERS.get(caller, ())


def _destination_of_datum(d):
    for k, name in DESTINATIONS.items():
        if name == d.name:
            return k
    return None


def destination_of(relpath):
    """The destination whose datum ``relpath`` is, or None (D21).

    Resolves a path of the store to the destination of mnemonic-save that
    writes it.
    """
    d = datum_of(relpath)
    if d is None:
        return None
    return _destination_of_datum(d)


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
                "sentience, consciousness or subjective continuity (probe %s)"
                % probe_id
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
            log_append(
                store,
                "torn-append",
                rule="OC-004(a)",
                session=session,
                path=EPISODIC,
                **cut,
            )

        # 6. the record, attributed to the live session (OC-003(e))
        record = {
            "id": "M-" + secrets.token_hex(8),
            "session": session,
            "at": clock.iso(),
            "content": content,
        }
        store.append(MNEMONIC, EPISODIC, record, writer=WRITER)
        return {"record": record["id"]}


def attempt_save(store: Store, cls, target):
    """mnemonic-save's attempted write, as the CPE calls it: the class guard,
    then the destination (D21, D68)."""
    try:
        resolved = store.attempt(cls, target, writer=WRITER)
    except GuardError as e:
        raise sil.refuse_attempt(
            store,
            e.check,
            e.detail,
            via="mnemonic-save",
            content_class=cls,
            target=target,
        )
    for d, _rel in resolved:
        destination = _destination_of_datum(d)
        if not admits("cpe", destination):
            raise sil.refuse_attempt(
                store,
                "mnemonic-destination",
                "%r may not write the %r destination" % ("cpe", destination),
                via="mnemonic-save",
                content_class=cls,
                target=target,
            )
    return resolved


# -- the session store (D10, D24, D78) ------------------------------------------


def session_path(session) -> str:
    """The session store file of ``session`` (D78)."""
    return "memory/session/%s.jsonl" % session


def save_session(store: Store, session, kind, **fields) -> str:
    """Append one record to ``session``'s file and return its id: the session
    destination of mnemonic-save, for the Orchestrator (D21). Called with the
    store lock held. The record is never probed (D78)."""
    if kind not in SESSION_KINDS:
        raise ValueError("unknown session record kind: %r" % (kind,))
    if not isinstance(session, str) or not SESSION_ID.match(session):
        raise ValueError("not a session id: %r" % (session,))
    path = session_path(session)
    cut = store.cut_torn_tail(MNEMONIC, path, writer=WRITER)
    if cut is not None:
        log_append(
            store,
            "torn-append",
            rule="OC-004(a)",
            session=session,
            path=path,
            **cut,
        )
    record = {
        "id": "R-" + secrets.token_hex(8),
        "session": session,
        "at": clock.iso(),
        "kind": kind,
        **fields,
    }
    store.append(MNEMONIC, path, record, writer=WRITER)
    return record["id"]


def session_records(store: Store, session) -> list:
    """The records of ``session`` in order (D78). A missing file is empty; a
    line that is not a JSON object and a final fragment without its newline
    are skipped."""
    try:
        data = store.read_bytes(session_path(session))
    except FileNotFoundError:
        return []
    records = []
    # The last piece is empty, or a fragment the newline never closed.
    for line in data.split(b"\n")[:-1]:
        try:
            record = json.loads(line.decode("utf-8"))
        except (ValueError, RecursionError):
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _open_record(store: Store, session):
    for record in session_records(store, session):
        if record.get("kind") == "session-open":
            return record
    return None


def _left(store: Store, session) -> bool:
    return any(
        record.get("kind") == "conversation-left"
        for record in session_records(store, session)
    )


def open_session_record(store: Store, session, number) -> str:
    """Write the ``session-open`` record of the new session ``session``
    (number ``number``) and return its conversation (D78). The session
    continues the conversation of the most recent earlier session that has an
    open record, unless that session left it. Called by the start with the
    store lock held."""
    previous = None
    for k in range(number - 1, 0, -1):
        candidate = "s-%d" % k
        if _open_record(store, candidate) is not None:
            previous = candidate
            break
    if previous is not None and not _left(store, previous):
        conversation = conversation_of(store, previous)
        continues = previous
    else:
        conversation = "C-" + secrets.token_hex(8)
        continues = None
    save_session(
        store,
        session,
        "session-open",
        conversation=conversation,
        continues=continues,
    )
    return conversation


def conversation_of(store: Store, session):
    """The conversation ``session`` belongs to, or None (D78)."""
    record = _open_record(store, session)
    if record is None:
        return None
    return record.get("conversation")


def transcript(store: Store, session) -> list:
    """The records of ``session``'s conversation, oldest session first, after
    the last ``transcript-cleared`` (D13, D78)."""
    record = _open_record(store, session)
    chain = [session]
    if record is not None:
        conversation = record.get("conversation")
        seen = {session}
        while True:
            previous = record.get("continues")
            if not isinstance(previous, str) or previous in seen:
                break
            record = _open_record(store, previous)
            if record is None or record.get("conversation") != conversation:
                break
            seen.add(previous)
            chain.append(previous)
    records = []
    for s in reversed(chain):
        records.extend(session_records(store, s))
    for i in range(len(records) - 1, -1, -1):
        if records[i].get("kind") == "transcript-cleared":
            return records[i + 1 :]
    return records
