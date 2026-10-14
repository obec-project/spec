# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Memory Interface Layer: the mnemonic class's sole write path (D21, D67)."""

from __future__ import annotations

import json
import re
import secrets

from . import clock, lifecycle, probes, sil, vital
from .sil import Refused, log_append
from .store import MNEMONIC, GuardError, Store, datum_of

WRITER = "mil"
EPISODIC = "memory/episodic/records.jsonl"
SEMANTIC = "memory/semantic/records.jsonl"

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


def save(root: str, *, caller, destination, content, supersedes=None) -> dict:
    """Write an episodic record attributed to the live session (OC-003(e)),
    to the destination the caller may use (D21), after the deterministic
    probes (D12). The record names its conversation and, when given, the
    latest record in the conversation's recall scope that it supersedes
    (D11, D79)."""
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

        # 4b. the conversation, and the record superseded, if any (D11, D79)
        conversation = conversation_of(store, session)
        if supersedes is not None:
            scope_ids = [r.get("id") for r in _scope(store, conversation)]
            if not isinstance(supersedes, str) or supersedes not in scope_ids:
                detail = "%r is not in the conversation's recall scope" % (supersedes,)
                rec = log_append(
                    store,
                    "refusal",
                    rule="OP-009(c)",
                    session=session,
                    check="recall-scope",
                    detail=detail,
                )
                raise Refused("recall-scope", "OP-009(c)", detail, [rec])
            if any(r.get("supersedes") == supersedes for r in _episodic(store)):
                detail = "%r is already superseded" % (supersedes,)
                rec = log_append(
                    store,
                    "refusal",
                    rule="OP-009(c)",
                    session=session,
                    check="lineage",
                    detail=detail,
                )
                raise Refused("lineage", "OP-009(c)", detail, [rec])

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
            "conversation": conversation,
        }
        if supersedes is not None:
            record["supersedes"] = supersedes
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


# -- recall (D11, D60, D79) -----------------------------------------------------


def _pointer_ids(store: Store, conversation) -> set:
    """The ids the pointer map of ``conversation`` names (D60); none until the
    Sleep writes a Resumption Record."""
    return set()


def _episodic(store: Store) -> list:
    """The episodic records in order (D11)."""
    return _read_records(store, EPISODIC)


def _scope(store: Store, conversation) -> list:
    """The recall scope of ``conversation``: its own episodic records and those
    its pointer map names, in file order (D79). A record without a
    ``conversation`` is in no scope."""
    named = _pointer_ids(store, conversation)
    return [
        r
        for r in _episodic(store)
        if (conversation is not None and r.get("conversation") == conversation)
        or r.get("id") in named
    ]


def _superseded(records) -> set:
    return {r["supersedes"] for r in records if isinstance(r.get("supersedes"), str)}


def _latest(records) -> list:
    """The records no other record of the list names in ``supersedes`` (D79)."""
    superseded = _superseded(records)
    return [r for r in records if r.get("id") not in superseded]


def _lineage(records, rid) -> set:
    """The ids linked to ``rid`` by ``supersedes``, ancestors and descendants,
    ``rid`` included (D79)."""
    links = {}
    for r in records:
        a, b = r.get("id"), r.get("supersedes")
        if isinstance(a, str) and isinstance(b, str):
            links.setdefault(a, set()).add(b)
            links.setdefault(b, set()).add(a)
    ids = {rid}
    pending = [rid]
    while pending:
        for other in links.get(pending.pop(), ()):
            if other not in ids:
                ids.add(other)
                pending.append(other)
    return ids


def recall(root: str, *, query=None, lineage=None) -> dict:
    """Recall from the live session's recall scope, by words or by lineage,
    and log what was returned (D79, OP-009(c)). By words it returns the latest
    record of each lineage whose content holds every word, case-folded. By
    lineage it returns the records of the scope that belong to the lineage of
    the id and names the ones outside the scope without returning them."""
    if (query is None) == (lineage is None):
        raise ValueError("recall takes exactly one of query and lineage")
    if query is not None and (not isinstance(query, str) or query.strip() == ""):
        raise ValueError("recall by words requires a non-empty string query")
    store = Store(root)
    with store.write_lock():
        session = vital.require_entity_session(root, "mnemonic-recall")
        conversation = conversation_of(store, session)
        scope = _scope(store, conversation)
        if query is not None:
            words = query.casefold().split()
            returned = [
                r
                for r in _latest(scope)
                if all(w in str(r.get("content", "")).casefold() for w in words)
            ]
            outside = []
        else:
            if not any(r.get("id") == lineage for r in scope):
                detail = "%r is not in the conversation's recall scope" % (lineage,)
                rec = log_append(
                    store,
                    "refusal",
                    rule="OP-009(c)",
                    session=session,
                    check="recall-scope",
                    detail=detail,
                )
                raise Refused("recall-scope", "OP-009(c)", detail, [rec])
            ids = _lineage(_episodic(store), lineage)
            returned = [r for r in scope if r.get("id") in ids]
            in_scope = {r.get("id") for r in scope}
            outside = sorted(ids - in_scope)
        rec = log_append(
            store,
            "recall",
            rule="OP-009(c)",
            session=session,
            query=query,
            lineage=lineage,
            returned=[r["id"] for r in returned],
            outside=outside,
        )
        return {"records": returned, "outside": outside, "log_records": [rec]}


def attempt_recall(store: Store, cls, target):
    """mnemonic-recall's attempted write: it reads memory and writes no content
    class of the store, so it refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "mnemonic-recall reads memory and writes no content class of the store",
        via="mnemonic-recall",
        content_class=cls,
        target=target,
    )


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
    return _read_records(store, session_path(session))


def _read_records(store: Store, relpath: str) -> list:
    """The JSON-object records of ``relpath`` in order. A missing file is
    empty; a line that is not a JSON object and a final fragment without its
    newline are skipped."""
    try:
        data = store.read_bytes(relpath)
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


def stimulate(root: str, text: str) -> dict:
    """Record ``text`` as a stimulus in the live session's file (D78). It is
    not probed and not episodic memory, and it runs no Vital Check."""
    store = Store(root)
    with store.write_lock():
        session = lifecycle.require_session(root, "stimulate")
        rid = save_session(store, session, "stimulus", text=text)
    return {"record": rid, "session": session}


# -- observation (D78, OC-003(e)) ---------------------------------------------


def observe(store: Store, *, include_session=False) -> list:
    """The mnemonic records: the episodic, then the semantic, and with
    ``include_session`` every session's records in session-file name order
    (D78)."""
    records = _read_records(store, EPISODIC) + _read_records(store, SEMANTIC)
    if include_session:
        for name in store.listdir("memory/session"):
            if name.endswith(".jsonl"):
                records.extend(session_records(store, name[: -len(".jsonl")]))
    return records
