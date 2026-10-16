# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Memory Interface Layer: the mnemonic class's sole write path (D21, D67)."""

from __future__ import annotations

import json
import re
import secrets

from . import chain, clock, config, lifecycle, probes, proposals, sil, vital
from .digest import canonical, sha256
from .sil import Refused, log_append
from .store import MNEMONIC, GuardError, Store, datum_of

WRITER = "mil"
EPISODIC = "memory/episodic/records.jsonl"
SEMANTIC = "memory/semantic/records.jsonl"
PENDING = "memory/semantic/pending.jsonl"

# The categories of a semantic record (D77).
CATEGORIES = ("rule", "guidance", "operator", "project", "reference", "knowledge")

# Each destination of mnemonic-save and the datum it writes (D21).
DESTINATIONS = {
    "session": "session-store",
    "episodic": "episodic-memory",
    "semantic": "semantic-memory",
}

# The destinations each caller may write (D21); the CPE's is the one built (D67).
CALLERS = {"cpe": ("episodic",), "orchestrator": ("session",)}

# The kinds of record a session's file holds (D78) and the session ids (D46).
SESSION_KINDS = (
    "session-open",
    "stimulus",
    "transcript-cleared",
    "compaction",
    "conversation-left",
    "closure-payload",
    "reply",
    "results",
    "results-discarded",
    "context-truncated",
    "cycle",
    "model-fingerprint",
)
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


def save(
    root: str, *, caller, destination, content, supersedes=None, quotes=None
) -> dict:
    """Write an episodic record attributed to the live session (OC-003(e)),
    to the destination the caller may use (D21), after the deterministic
    probes (D12). The record names its conversation and, when given, the
    latest record in the conversation's recall scope that it supersedes
    (D11, D79). The probes run on ``content`` only; ``quotes``, a list of
    ``{record, text}``, are verified against the stimuli of the conversation's
    transcript and kept outside the probes (D86)."""
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

        # 3a. the quotes: literal parts of the transcript's stimuli (D86)
        if quotes is not None:
            problem = _quote_problem(store, session, quotes)
            if problem is not None:
                rec = log_append(
                    store,
                    "refusal",
                    rule="OP-005(a)",
                    session=session,
                    check="quote",
                    detail=problem,
                )
                raise Refused("quote", "OP-005(a)", problem, [rec])

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
        if quotes:
            record["quotes"] = quotes
        if sil.current_cycle() is not None:
            record["cycle"] = sil.current_cycle()
        store.append(MNEMONIC, EPISODIC, record, writer=WRITER)
        return {"record": record["id"]}


def _quote_problem(store: Store, session, quotes):
    """Why ``quotes`` are not verified quotes of the transcript's stimuli, or
    None when each is a literal part of the stimulus it names (D86)."""
    if not isinstance(quotes, list):
        return "quotes must be a list"
    for q in quotes:
        if (
            not isinstance(q, dict)
            or set(q) != {"record", "text"}
            or not isinstance(q["record"], str)
            or not isinstance(q["text"], str)
            or q["text"].strip() == ""
        ):
            return "a quote is {record, text}, both strings, text not empty"
    stimuli = {
        r["id"]: r.get("text")
        for r in transcript(store, session)
        if r.get("kind") == "stimulus"
    }
    for q in quotes:
        held = stimuli.get(q["record"])
        if not isinstance(held, str) or q["text"] not in held:
            return "%r is not a literal part of a stimulus of the transcript (%s)" % (
                q["text"],
                q["record"],
            )
    return None


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


# -- promotion requests (D53, D77, D80) ----------------------------------------


def promotion_digest(slug, category, content, supersedes) -> str:
    """The digest of a promotion's text: what the Operator's authorization
    names (D53, D80)."""
    return sha256(
        canonical(
            {
                "slug": slug,
                "category": category,
                "content": content,
                "supersedes": supersedes,
            }
        )
    )


def _check_promotion(store: Store, session, slug, category, content, *, binding=None):
    """The checks a promotion's text passes, whether it is the entity's request
    or the Operator's edit: slug, category, content, then the probes of the
    committed generation (OP-009(f), OC-002(d), D77). A refusal is logged with
    the session and, when given, the binding, and raised."""
    who = {}
    if session is not None:
        who["session"] = session
    if binding is not None:
        who["binding"] = binding

    def refuse(rule, check, detail, **extra):
        rec = log_append(
            store, "refusal", rule=rule, check=check, detail=detail, **who, **extra
        )
        return Refused(check, rule, detail, [rec])

    if (
        not isinstance(slug, str)
        or slug.strip() == ""
        or len(slug) > 120
        or "\n" in slug
    ):
        raise refuse(
            "OP-009(f)",
            "slug",
            "a slug is a non-empty single line of at most 120 characters",
        )
    if category not in CATEGORIES:
        raise refuse(
            "OP-009(f)",
            "category",
            "%r is not a category of semantic memory" % (category,),
        )
    if not isinstance(content, str) or content.strip() == "":
        raise refuse("OP-009(f)", "content", "a promotion requires a non-empty content")
    try:
        probe_set = sil.committed_probes(store)
    except (OSError, ValueError, KeyError):
        raise refuse("OC-002(d)", "probe-set", "the committed probe set cannot be read")
    for text in (slug, content):
        matches = probes.scan(probe_set, text)
        if matches:
            probe_id = matches[0]["id"]
            raise refuse(
                "OC-002(d)",
                "self-representation",
                "the promotion represents the entity as experiencing "
                "sentience, consciousness or subjective continuity (probe %s)"
                % probe_id,
                probe=probe_id,
            )


def request_promotion(
    store: Store,
    session,
    *,
    slug,
    category,
    content,
    supersedes=None,
    sources=(),
    closure=None,
    index=None,
) -> str:
    """Record a request to promote a memory to semantic memory and return its
    id (D53, D77, D80). It writes only the pending file: the promotion itself
    waits for the Operator's authorization. A request made from a Closure
    Payload names it in ``closure`` and the promotion's position in ``index``
    (D84). Called with the store lock held."""
    _check_promotion(store, session, slug, category, content)
    if supersedes is not None and not isinstance(supersedes, str):
        detail = "supersedes is a record id or absent"
        rec = log_append(
            store,
            "refusal",
            rule="OP-009(f)",
            session=session,
            check="supersedes",
            detail=detail,
        )
        raise Refused("supersedes", "OP-009(f)", detail, [rec])
    if not isinstance(sources, (list, tuple)) or not all(
        isinstance(s, str) for s in sources
    ):
        detail = "sources is a list of strings"
        rec = log_append(
            store,
            "refusal",
            rule="OP-009(f)",
            session=session,
            check="sources",
            detail=detail,
        )
        raise Refused("sources", "OP-009(f)", detail, [rec])
    cut = store.cut_torn_tail(MNEMONIC, PENDING, writer=WRITER)
    if cut is not None:
        log_append(
            store,
            "torn-append",
            rule="OC-004(a)",
            session=session,
            path=PENDING,
            **cut,
        )
    record = {
        "id": "PP-" + secrets.token_hex(8),
        "session": session,
        "conversation": conversation_of(store, session),
        "at": clock.iso(),
        "slug": slug,
        "category": category,
        "content": content,
        "supersedes": supersedes,
        "sources": list(sources),
        "digest": promotion_digest(slug, category, content, supersedes),
    }
    if closure is not None:
        record["closure"] = closure
        record["index"] = index
    store.append(MNEMONIC, PENDING, record, writer=WRITER)
    return record["id"]


def pending_promotions(store: Store) -> list:
    """The promotion requests in order (D80)."""
    return _read_records(store, PENDING)


# -- promotion (D53, D81) -------------------------------------------------------


def semantic_records(store: Store) -> list:
    """The semantic records in order (D53, D81)."""
    return _read_records(store, SEMANTIC)


# -- reading semantic memory through its ledger (D77, D82) ----------------------

# The categories always loaded when the head generation's config.json names none
# (D77).
ALWAYS_LOADED = ("rule", "guidance", "operator")


def _sid(item):
    """The ``id`` of a semantic record or ledger entry, or None when it is not a
    string (D82)."""
    rid = item.get("id")
    return rid if isinstance(rid, str) else None


def semantic_check(store: Store) -> dict:
    """Read the semantic records and the ledger once and compare them (D82,
    OP-009(f)). Returns ``records`` (all, in file order), ``sealed`` (those
    whose first ``promotion`` entry carries the digest of the record's
    canonical form, in file order), ``retracted`` (the ids with a
    ``retraction`` entry) and ``findings`` (``{type, id}``: ``semantic-unsealed``
    and ``semantic-digest`` per record in file order, then ``semantic-missing``
    per entry in ledger order)."""
    records = semantic_records(store)
    ledger = sil.semantic_ledger(store)
    first = {}
    retracted = set()
    for entry in ledger:
        if _sid(entry) is None:
            continue
        if entry.get("kind") == "promotion":
            first.setdefault(_sid(entry), entry)
        elif entry.get("kind") == "retraction":
            retracted.add(_sid(entry))
    sealed = []
    findings = []
    for record in records:
        entry = first.get(_sid(record))
        if entry is None:
            findings.append({"type": "semantic-unsealed", "id": _sid(record)})
        elif entry.get("digest") != sha256(canonical(record)):
            findings.append({"type": "semantic-digest", "id": _sid(record)})
        else:
            sealed.append(record)
    present = {_sid(r) for r in records}
    for entry in ledger:
        rid = _sid(entry)
        if entry.get("kind") == "promotion" and rid is not None and rid not in present:
            findings.append({"type": "semantic-missing", "id": rid})
    return {
        "records": records,
        "sealed": sealed,
        "retracted": retracted,
        "findings": findings,
    }


def semantic_live(check: dict) -> list:
    """The records of ``check["sealed"]`` that are not retracted and that no
    semantic record names in ``supersedes`` (D82)."""
    superseded = _superseded(check["records"])
    return [
        r
        for r in check["sealed"]
        if r.get("id") not in check["retracted"] and r.get("id") not in superseded
    ]


def always_loaded_categories(store: Store) -> list:
    """The categories context assembly loads whole: ``always_loaded`` of the
    head generation's ``config.json`` when it is a non-empty list of distinct
    categories, else ``ALWAYS_LOADED`` (D77, D82)."""
    try:
        config = store.read_json(
            chain.gen_relpath(sil.read_head(store)["entry"]) + "/config.json"
        )
        listed = config["always_loaded"]
    except (OSError, ValueError, KeyError, TypeError):
        return list(ALWAYS_LOADED)
    if (
        isinstance(listed, list)
        and listed
        and all(isinstance(c, str) and c in CATEGORIES for c in listed)
        and len(set(listed)) == len(listed)
    ):
        return list(listed)
    return list(ALWAYS_LOADED)


def always_loaded(store: Store) -> list:
    """The live records of the always-loaded categories, grouped in the order
    of ``always_loaded_categories`` and in file order within each (D77, D82)."""
    live = semantic_live(semantic_check(store))
    return [
        r
        for c in always_loaded_categories(store)
        for r in live
        if r.get("category") == c
    ]


def semantic_index(store: Store) -> list:
    """``{id, slug, category}`` of the live records outside the always-loaded
    categories, newest first (D77, D82)."""
    loaded = always_loaded_categories(store)
    live = semantic_live(semantic_check(store))
    return [
        {"id": r.get("id"), "slug": r.get("slug"), "category": r.get("category")}
        for r in reversed(live)
        if r.get("category") not in loaded
    ]


def _promotion_refusal(store: Store, session, check, detail) -> Refused:
    rec = log_append(
        store,
        "refusal",
        rule="OP-009(f)",
        session=session,
        check=check,
        detail=detail,
    )
    return Refused(check, "OP-009(f)", detail, [rec])


def _ledger_entry(record, promotion_id, authorization) -> dict:
    return {
        "kind": "promotion",
        "id": record["id"],
        "digest": sha256(canonical(record)),
        "promotion": promotion_id,
        "authorization": authorization,
    }


def promote(store: Store, session, promotion_id):
    """Promote the pending request ``promotion_id`` to semantic memory and
    return the id of the record, or None while the request stays pending
    (D53, D81). Writes what the authorization names, once: the log record, the
    semantic record, then the ledger entry. A promotion a crash interrupted
    between the last two is completed, not repeated. The probes and
    ``supersedes`` are checked before the authorization is consumed, so a
    refused promotion spends no window budget. Called with the store lock
    held."""
    request = next(
        (r for r in pending_promotions(store) if r.get("id") == promotion_id), None
    )
    if request is None:
        return None

    ledger = sil.semantic_ledger(store)
    for entry in ledger:
        if entry.get("kind") == "promotion" and entry.get("promotion") == promotion_id:
            return entry["id"]
    auth = proposals.read_auth(store)
    decision = auth["promotions"].get(promotion_id)
    decision = decision if isinstance(decision, dict) else {}

    done = next(
        (r for r in semantic_records(store) if r.get("promotion") == promotion_id),
        None,
    )
    if done is not None:
        authorized = decision.get("digest", request["digest"])
        digest = promotion_digest(
            done.get("slug"),
            done.get("category"),
            done.get("content"),
            done.get("supersedes"),
        )
        if digest != authorized:
            raise _promotion_refusal(
                store,
                session,
                "semantic-ledger",
                "the semantic record %s of promotion %s does not carry the "
                "authorized text" % (done.get("id"), promotion_id),
            )
        sil.semantic_ledger_append(
            store, _ledger_entry(done, promotion_id, done.get("authorization"))
        )
        return done["id"]

    if "rejected" in decision:
        return None

    edit = decision.get("edit") if "digest" in decision else None
    if edit:
        _check_promotion(
            store,
            session,
            edit["slug"],
            edit["category"],
            edit["content"],
            binding=decision.get("binding"),
        )
    else:
        _check_promotion(
            store, session, request["slug"], request["category"], request["content"]
        )

    target = request["supersedes"]
    if target is not None:
        live = any(
            e.get("kind") == "promotion" and e.get("id") == target for e in ledger
        )
        retracted = any(
            e.get("kind") == "retraction" and e.get("id") == target for e in ledger
        )
        superseded = any(r.get("supersedes") == target for r in semantic_records(store))
        if not live or retracted or superseded:
            raise _promotion_refusal(
                store,
                session,
                "supersedes",
                "%r is not a semantic record that can be superseded" % (target,),
            )

    got = proposals.promotion_authorization(
        store, store.root, promotion_id, request, session=session
    )
    if got is None:
        return None
    text, auth_loc, grant = got
    authorization = auth_loc or grant

    record_id = "S-" + secrets.token_hex(8)
    log_append(
        store,
        "promotion",
        rule="OP-009(f)",
        session=session,
        promotion=promotion_id,
        record=record_id,
        authorization=authorization,
    )
    record = {
        "id": record_id,
        "slug": text["slug"],
        "category": text["category"],
        "content": text["content"],
        "supersedes": request["supersedes"],
        "conversation": request["conversation"],
        "session": request["session"],
        "binding": decision.get("binding") if edit else None,
        "promotion": promotion_id,
        "authorization": authorization,
        "at": clock.iso(),
    }
    cut = store.cut_torn_tail(MNEMONIC, SEMANTIC, writer=WRITER)
    if cut is not None:
        log_append(
            store,
            "torn-append",
            rule="OC-004(a)",
            session=session,
            path=SEMANTIC,
            **cut,
        )
    store.append(MNEMONIC, SEMANTIC, record, writer=WRITER)
    sil.semantic_ledger_append(
        store, _ledger_entry(record, promotion_id, authorization)
    )
    return record_id


# -- recall (D11, D60, D79) -----------------------------------------------------


def pointers_path(conversation) -> str:
    """The pointer map of ``conversation`` (D85)."""
    return "memory/pointers/%s.json" % conversation


def pointer_map(store: Store, conversation) -> dict:
    """The pointer map of ``conversation`` (D85): the file when it exists and
    has the shape, otherwise an empty map."""
    empty = {"conversation": conversation, "entries": []}
    try:
        data = store.read_json(pointers_path(conversation))
    except (OSError, ValueError, RecursionError):
        return empty
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return empty
    return data


def _pointer_ids(store: Store, conversation) -> set:
    """The ids the pointer map of ``conversation`` names (D60, D85)."""
    if conversation is None:
        return set()
    return {
        e["id"]
        for e in pointer_map(store, conversation)["entries"]
        if isinstance(e, dict) and isinstance(e.get("id"), str)
    }


def add_pointers(store: Store, conversation, ids, *, source, via, act) -> list:
    """Add ``ids`` to the pointer map of ``conversation`` and return the ids
    added (D85). An id already in the conversation's scope, or repeated in
    ``ids``, is skipped. The map is written only when something is added.
    Called with the store lock held."""
    held = {r.get("id") for r in _scope(store, conversation)}
    pointers = pointer_map(store, conversation)
    added = []
    for i in ids:
        if i in held or i in added:
            continue
        added.append(i)
        pointers["entries"].append({"id": i, "from": source, "via": via, "act": act})
    if added:
        store.replace_json(
            MNEMONIC, pointers_path(conversation), pointers, writer=WRITER
        )
    return added


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
    record of each lineage whose content holds every word, case-folded, then
    the live semantic records whose slug or content holds every word. By
    lineage it returns the records of the scope that belong to the lineage of
    the id and names the ones outside the scope without returning them; the id
    of a semantic record returns the sealed, unretracted records of its
    lineage instead (D82). The ids of the semantic records withheld are named
    in the log record and in the result."""
    if (query is None) == (lineage is None):
        raise ValueError("recall takes exactly one of query and lineage")
    if query is not None and (not isinstance(query, str) or query.strip() == ""):
        raise ValueError("recall by words requires a non-empty string query")
    store = Store(root)
    with store.write_lock():
        session = vital.require_entity_session(root, "mnemonic-recall")
        conversation = conversation_of(store, session)
        scope = _scope(store, conversation)
        check = semantic_check(store)
        if query is not None:
            words = query.casefold().split()
            returned = [
                r
                for r in _latest(scope)
                if all(w in str(r.get("content", "")).casefold() for w in words)
            ]
            for r in semantic_live(check):
                text = (
                    str(r.get("slug", "")) + "\n" + str(r.get("content", ""))
                ).casefold()
                if all(w in text for w in words):
                    returned.append(r)
            outside = []
        elif any(r.get("id") == lineage for r in check["records"]):
            sealed_ids = {r.get("id") for r in check["sealed"]}
            if lineage not in sealed_ids or lineage in check["retracted"]:
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
            ids = _lineage(check["records"], lineage)
            returned = [
                r
                for r in check["sealed"]
                if r.get("id") in ids and r.get("id") not in check["retracted"]
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
        withheld = sorted({f["id"] for f in check["findings"]}, key=str)
        rec = log_append(
            store,
            "recall",
            rule="OP-009(c)",
            session=session,
            query=query,
            lineage=lineage,
            returned=[r["id"] for r in returned],
            outside=outside,
            withheld=withheld,
        )
        return {
            "records": returned,
            "outside": outside,
            "withheld": withheld,
            "log_records": [rec],
        }


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


def conversation_left(store: Store, session) -> bool:
    """Whether ``session``'s records end its conversation (D78, D84)."""
    return _left(store, session)


def open_session_record(store: Store, session, number) -> str:
    """Write the ``session-open`` record of the new session ``session``
    (number ``number``) and return its conversation (D78). The session
    continues the conversation of the most recent earlier session that has an
    open record, unless that session left it. A session that left naming a
    conversation to resume is continued from that conversation's last session;
    one that left with a verified Resumption Record seeds the new
    conversation's pointer map (D85). Called by the start with the store lock
    held."""
    previous = None
    for k in range(number - 1, 0, -1):
        candidate = "s-%d" % k
        if _open_record(store, candidate) is not None:
            previous = candidate
            break
    fields = {}
    if previous is not None and not _left(store, previous):
        conversation = conversation_of(store, previous)
        continues = previous
    else:
        left = None
        if previous is not None:
            left = [
                r
                for r in session_records(store, previous)
                if r.get("kind") == "conversation-left"
            ][-1]
        resume = left.get("resume") if left is not None else None
        if (
            isinstance(resume, dict)
            and isinstance(resume.get("conversation"), str)
            and isinstance(resume.get("session"), str)
        ):
            conversation = resume["conversation"]
            continues = resume["session"]
        else:
            conversation = "C-" + secrets.token_hex(8)
            continues = None
            seeded = _seed(store, session, previous, conversation)
            if seeded is not None:
                fields["seeded_by"] = seeded
    save_session(
        store,
        session,
        "session-open",
        conversation=conversation,
        continues=continues,
        **fields,
    )
    return conversation


def last_session_of(store: Store, conversation, before):
    """The most recent session before number ``before`` whose ``session-open``
    names ``conversation``, or None (D85). Scans the session records."""
    for k in range(before - 1, 0, -1):
        candidate = "s-%d" % k
        if conversation_of(store, candidate) == conversation:
            return candidate
    return None


def _seed(store: Store, session, previous, conversation):
    """Seed the pointer map of the new ``conversation`` from the Resumption
    Record of the conversation ``previous`` left with a Closure Payload, and
    return that conversation, or None (D85, OP-009(e)). The record counts only
    if the log record the checkpoint locates is the ``closure-complete`` of
    ``previous`` naming this record's digest; otherwise it is discarded and
    logged. Called with the store lock held."""
    if previous is None or not any(
        r.get("kind") == "closure-payload" for r in session_records(store, previous)
    ):
        return None
    prev = conversation_of(store, previous)
    path = resumption_path(prev)
    try:
        data = store.read_bytes(path)
    except OSError:
        return None
    rec = sil.checkpoint_record(store)
    resumption = rec.get("resumption") if rec is not None else None
    if not (
        rec is not None
        and rec.get("kind") == "closure-complete"
        and rec.get("session") == previous
        and isinstance(resumption, dict)
        and resumption.get("conversation") == prev
        and resumption.get("sha256") == sha256(data)
    ):
        log_append(
            store,
            "resumption-discarded",
            rule="OP-009(e)",
            session=session,
            conversation=prev,
        )
        return None
    try:
        working_set = json.loads(data.decode("utf-8")).get("working_set")
    except (ValueError, AttributeError, RecursionError):
        working_set = None
    if not isinstance(working_set, list):
        working_set = []
    add_pointers(
        store,
        conversation,
        [i for i in working_set if isinstance(i, str)],
        source=prev,
        via="resumption",
        act=None,
    )
    return prev


def conversation_of(store: Store, session):
    """The conversation ``session`` belongs to, or None (D78)."""
    record = _open_record(store, session)
    if record is None:
        return None
    return record.get("conversation")


def _cut_transcript(store: Store, session):
    """The records of ``session``'s conversation, oldest session first, after
    the last cut, and the record that cut (D13, D78, D101): a
    ``transcript-cleared`` keeps what follows it; a ``compaction`` keeps what
    follows it, or, when its ``keep_from`` names a record before it in the
    transcript, the records from that one on, the ``compaction`` included.
    The cut is ``None`` when there is none."""
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
    kept = []
    cut = None
    for r in records:
        kind = r.get("kind")
        if kind == "transcript-cleared":
            kept = []
            cut = r
        elif kind == "compaction":
            keep_from = r.get("keep_from")
            at = next(
                (
                    i
                    for i, x in enumerate(kept)
                    if isinstance(keep_from, str) and x.get("id") == keep_from
                ),
                None,
            )
            kept = [] if at is None else kept[at:] + [r]
            cut = r
        else:
            kept.append(r)
    return kept, cut


def transcript(store: Store, session) -> list:
    """The records of ``session``'s conversation, oldest session first, after
    the last ``transcript-cleared`` or ``compaction`` (D13, D78, D101)."""
    return _cut_transcript(store, session)[0]


def compaction_summary(store: Store, session):
    """The summary of the ``compaction`` that cuts ``session``'s transcript, or
    ``None`` when the cut is a ``transcript-cleared``, there is none, or the
    summary is not a non-empty string (D101)."""
    cut = _cut_transcript(store, session)[1]
    if cut is None or cut.get("kind") != "compaction":
        return None
    summary = cut.get("summary")
    if not isinstance(summary, str) or summary.strip() == "":
        return None
    return summary


def stimulate(root: str, text: str) -> dict:
    """Record ``text`` as a stimulus in the live session's file (D78). It is
    not probed and not episodic memory, and it runs no Vital Check."""
    store = Store(root)
    with store.write_lock():
        session = lifecycle.require_session(root, "stimulate")
        rid = save_session(store, session, "stimulus", text=text)
    return {"record": rid, "session": session}


# -- leaving a conversation (D84) -----------------------------------------------

# The keys of a Closure Payload and of each promotion in it (D84).
_PAYLOAD_KEYS = {"consolidation", "working_set", "message", "promotions"}
_PROMOTION_REQUIRED = {"slug", "category", "content"}
_PROMOTION_KEYS = _PROMOTION_REQUIRED | {"supersedes", "sources"}


def resumption_path(conversation) -> str:
    """The Resumption Record of ``conversation`` (D84)."""
    return "memory/resumption/%s.json" % conversation


def _payload_shaped(payload) -> bool:
    """Whether ``payload`` has the shape of a Closure Payload (D84)."""
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        return False
    for key in ("consolidation", "message"):
        if not isinstance(payload[key], str) or payload[key].strip() == "":
            return False
    working_set = payload["working_set"]
    if not isinstance(working_set, list) or not all(
        isinstance(i, str) for i in working_set
    ):
        return False
    if len(set(working_set)) != len(working_set):
        return False
    promotions = payload["promotions"]
    if not isinstance(promotions, list):
        return False
    for p in promotions:
        if not isinstance(p, dict) or not _PROMOTION_REQUIRED <= set(p):
            return False
        if not set(p) <= _PROMOTION_KEYS:
            return False
        if not all(isinstance(p[k], str) for k in _PROMOTION_REQUIRED):
            return False
    return True


def check_closure_payload(store: Store, session, payload) -> None:
    """Check a Closure Payload before anything is written (D84). The first
    failure is logged with the session and raised: the shape (OP-009(d)), the
    pointer-map limit (OP-009(e)), the working set against the latest records
    in the conversation's scope (OP-009(c)), then the probes on the
    consolidation and the message (OC-002(d)). The promotions' own checks and
    probes run when their requests are recorded (D80). Called with the store
    lock held."""

    def refuse(rule, check, detail, **extra):
        rec = log_append(
            store,
            "refusal",
            rule=rule,
            session=session,
            check=check,
            detail=detail,
            **extra,
        )
        return Refused(check, rule, detail, [rec])

    if not _payload_shaped(payload):
        raise refuse(
            "OP-009(d)",
            "closure-payload",
            "a Closure Payload is exactly a consolidation, a working set, a "
            "message and promotions",
        )
    working_set = payload["working_set"]
    limit = config.value(store, "pointer_map_limit")
    if len(working_set) > limit:
        raise refuse(
            "OP-009(e)",
            "pointer-map-limit",
            "the working set names %d records, at most %d" % (len(working_set), limit),
        )
    latest = {
        r.get("id") for r in _latest(_scope(store, conversation_of(store, session)))
    }
    for rid in working_set:
        if rid not in latest:
            raise refuse(
                "OP-009(c)",
                "recall-scope",
                "%r is not the latest of its lineage in the conversation's "
                "recall scope" % (rid,),
            )
    try:
        probe_set = sil.committed_probes(store)
    except (OSError, ValueError, KeyError):
        raise refuse("OC-002(d)", "probe-set", "the committed probe set cannot be read")
    for text in (payload["consolidation"], payload["message"]):
        matches = probes.scan(probe_set, text)
        if matches:
            probe_id = matches[0]["id"]
            raise refuse(
                "OC-002(d)",
                "self-representation",
                "the closure represents the entity as experiencing "
                "sentience, consciousness or subjective continuity (probe %s)"
                % probe_id,
                probe=probe_id,
            )


def record_requests(store: Store, session, closure_id, payload):
    """Record the promotion requests of a Closure Payload, ``closure_id`` being
    its session record, and return ``(requests, refused)``: the request ids in
    index order and the indexes refused (D80, D84). A request already recorded
    for ``(closure_id, index)`` is reused; a refused one is logged by
    ``request_promotion`` and skipped. Called with the store lock held."""
    requests = []
    refused = []
    for i, p in enumerate(payload["promotions"]):
        existing = next(
            (
                r["id"]
                for r in pending_promotions(store)
                if r.get("closure") == closure_id and r.get("index") == i
            ),
            None,
        )
        if existing is None:
            try:
                existing = request_promotion(
                    store,
                    session,
                    slug=p["slug"],
                    category=p["category"],
                    content=p["content"],
                    supersedes=p.get("supersedes"),
                    sources=p.get("sources", ()),
                    closure=closure_id,
                    index=i,
                )
            except Refused:
                refused.append(i)
                continue
        requests.append(existing)
    return requests, refused


def consolidate(store: Store, session):
    """Consolidate the Closure Payload of ``session``, if its records hold one
    (D84), and return what was written, or None. Each thing is written once,
    however many times the Sleep runs: the consolidation as an episodic record
    naming the payload in ``closure``, and the Resumption Record, replaced
    whole. The payload's promotion requests were recorded with it (D80) and
    are found, not recorded. Then ``conversation-left`` is written if the
    records lack it. Called with the store lock held."""
    payloads = [
        r for r in session_records(store, session) if r.get("kind") == "closure-payload"
    ]
    if not payloads:
        return None
    pid = payloads[-1]["id"]
    payload = payloads[-1]["payload"]
    conversation = conversation_of(store, session)

    consolidation = next(
        (r["id"] for r in _episodic(store) if r.get("closure") == pid), None
    )
    if consolidation is None:
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
        record = {
            "id": "M-" + secrets.token_hex(8),
            "session": session,
            "at": clock.iso(),
            "content": payload["consolidation"],
            "conversation": conversation,
            "closure": pid,
        }
        store.append(MNEMONIC, EPISODIC, record, writer=WRITER)
        consolidation = record["id"]

    found = [r for r in pending_promotions(store) if r.get("closure") == pid]
    found.sort(key=lambda r: r["index"])
    requests = [r["id"] for r in found]

    rr = {
        "conversation": conversation,
        "session": session,
        "closure": pid,
        "consolidation": consolidation,
        "working_set": payload["working_set"],
        "message": payload["message"],
        "at": clock.iso(),
    }
    store.replace_json(MNEMONIC, resumption_path(conversation), rr, writer=WRITER)

    if not _left(store, session):
        save_session(store, session, "conversation-left", closure=pid)
    return {
        "closure": pid,
        "consolidation": consolidation,
        "requests": requests,
        "resumption": {
            "conversation": conversation,
            "sha256": sha256(canonical(rr)),
        },
    }


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
