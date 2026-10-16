# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The cognitive cycle and its chain (D89, OP-001)."""

from __future__ import annotations

import json

from . import channel, clock, config, context, lifecycle, mil, model, proposals
from . import probes, sil, vital
from . import exec as execution
from .sil import Refused, log_append
from .store import Store

OPS = (
    "reply",
    "mnemonic-save",
    "mnemonic-recall",
    "file_read",
    "file_write",
    "file_list",
    "http_fetch",
    "invoke-skill",
    "propose",
)

SCHEMA = {
    "type": "object",
    "properties": {
        "intents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"op": {"type": "string", "enum": list(OPS)}},
                "required": ["op"],
            },
        }
    },
    "required": ["intents"],
}

INSTRUCTIONS = """\
Respond only with one JSON object: {"intents": [...]}. Each intent is an object \
with an "op" naming one operation and the fields that operation takes:
- reply {text}: say text to the Operator.
- mnemonic-save {content, supersedes?, quotes?}: write an episodic record.
- mnemonic-recall {query} or {lineage}: recall records by words or by lineage.
- file_read {path}: read a file in the workspace.
- file_write {path, content}: write a file in the workspace.
- file_list {path}: list a directory in the workspace.
- http_fetch {url}: fetch a URL.
- invoke-skill {skill, target?, args?}: run an installed skill.
- propose {ops}: originate an evolution proposal from a list of ops.
Every intent is attempted, in order, and none sees another's result. The \
results of all the intents except reply arrive in the next turn under \
"Results:". Only reply reaches the Operator. Send an empty list when there is \
nothing to do or to say."""

CLOSURE_SCHEMA = {
    "type": "object",
    "properties": {
        "consolidation": {"type": "string"},
        "working_set": {"type": "array", "items": {"type": "string"}},
        "message": {"type": "string"},
        "promotions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "category": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["slug", "category", "content"],
            },
        },
    },
    "required": ["consolidation", "working_set", "message", "promotions"],
}

CLOSURE_INSTRUCTIONS = (
    """\
The Operator is ending this conversation. Respond only with one JSON object \
with these fields:
- consolidation: what this conversation established, in the entity's own words.
- working_set: the ids of the records the next conversation needs, each the \
latest record of its lineage.
- message: what gives those records their context, and the next steps.
- promotions: what is worth becoming semantic knowledge. Each is an object \
with slug, category and content, and optionally supersedes and sources. The \
category is one of: """
    + ", ".join(mil.CATEGORIES)
    + """.
The entity does not describe itself as conscious or sentient."""
)

COMPACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "saves": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "supersedes": {"type": "string"},
                    "quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "record": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["record", "text"],
                        },
                    },
                },
                "required": ["content"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["saves", "summary"],
}

COMPACTION_INSTRUCTIONS = """\
The context is being compacted: the transcript before this point will be \
replaced by your summary. Respond only with one JSON object with these fields:
- saves: what in the transcript is worth keeping as episodic memory. Each is \
an object with content, and optionally supersedes (the id of the latest \
record of a lineage it replaces) and quotes (a list of objects with record \
and text: literal parts of the Operator's stimuli).
- summary: what this conversation has covered so far — the decisions, the \
open threads, what comes next — for the context that follows.
The entity does not describe itself as conscious or sentient."""

RESULT_CAP = 16000
HOLD_LIMIT = 8  # holds put to the Operator for one intent (D99)


class Aborted(Exception):
    """A cycle that cannot be dispatched; the message is the reason."""


def parse(text):
    """The intents of a completion (D89). Raises ``Aborted`` unless the text is
    a JSON object whose ``intents`` is a list of objects each naming an
    operation in ``OPS``."""
    try:
        document = json.loads(text)
    except (ValueError, RecursionError, TypeError):
        raise Aborted("the completion is not JSON")
    if not isinstance(document, dict):
        raise Aborted("the completion is not a JSON object")
    intents = document.get("intents")
    if not isinstance(intents, list):
        raise Aborted("the completion has no list of intents")
    for item in intents:
        if not isinstance(item, dict):
            raise Aborted("an intent is not an object")
        if item.get("op") not in OPS:
            raise Aborted("unknown operation: %r" % (item.get("op"),))
    return intents


def _dispatch_to_owner(root, cycle_id, intent):
    op = intent["op"]
    if op == "mnemonic-save":
        return mil.save(
            root,
            caller="cpe",
            destination="episodic",
            content=intent["content"],
            supersedes=intent.get("supersedes"),
            quotes=intent.get("quotes"),
        )
    if op == "mnemonic-recall":
        return mil.recall(
            root, query=intent.get("query"), lineage=intent.get("lineage")
        )
    if op == "file_read":
        return execution.file_read(root, intent["path"])
    if op == "file_write":
        return execution.file_write(
            root, intent["path"], intent["content"].encode("utf-8"), intent=cycle_id
        )
    if op == "file_list":
        return execution.file_list(root, intent["path"])
    if op == "http_fetch":
        return execution.http_fetch(root, intent["url"])
    if op == "invoke-skill":
        return execution.invoke_skill(
            root, intent["skill"], intent.get("target"), intent.get("args")
        )
    if op == "propose":
        return proposals.propose(root, intent["ops"])
    raise KeyError(op)


def _refused_outcome(op, check, rule, detail):
    return {
        "op": op,
        "outcome": "refused",
        "check": check,
        "rule": rule,
        "detail": detail,
    }


def _refuse_held(root, cycle_id, held, check, rule, detail, **extra):
    """Log the refusal of an act stopped at a hold (D99) and return its
    outcome."""
    with sil.originated_by(cycle_id):
        log_append(
            Store(root),
            "refusal",
            rule=rule,
            check=check,
            detail=detail,
            op=held["op"],
            target=held["target"],
            **extra,
        )
    return _refused_outcome(held["op"], check, rule, detail)


def dispatch(root, cycle_id, intent):
    """The outcome of one intent other than ``reply``, from the function of the
    owner it names, which checks, refuses and records as for any caller (D89).
    An act stopped at a hold is put to the Operator and, allowed, dispatched
    again from its first check, up to ``HOLD_LIMIT`` holds (D99). Returns
    ``{"op", "outcome", ...}``."""
    op = intent["op"]
    holds = 0
    try:
        while True:
            try:
                with sil.originated_by(cycle_id):
                    result = _dispatch_to_owner(root, cycle_id, intent)
            except channel.Held as e:
                hold = e.hold
                if holds == HOLD_LIMIT:
                    return _refuse_held(
                        root,
                        cycle_id,
                        hold,
                        "hold-limit",
                        "OC-001(c)",
                        "more than %d holds for one intent" % HOLD_LIMIT,
                        hold=hold["id"],
                    )
                holds += 1
                if channel.ask(hold) == "deny":
                    return _refuse_held(
                        root,
                        cycle_id,
                        hold,
                        hold["check"],
                        hold["rule"],
                        "the Operator denied it",
                        reason="denied",
                        hold=hold["id"],
                    )
                continue
            except Refused as e:
                return _refused_outcome(op, e.check, e.rule, e.detail)
            except (KeyError, TypeError, AttributeError, ValueError) as e:
                return {"op": op, "outcome": "invalid", "detail": str(e)}
            break
        body = {k: v for k, v in result.items() if k != "log_records"}
        return {"op": op, "outcome": "done", **body}
    finally:
        channel.end_intent()


def _json_default(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def render(outcomes):
    """The text of a ``results`` record: one line per outcome, in order, each
    capped at ``RESULT_CAP`` characters (D89)."""
    lines = []
    for i, outcome in enumerate(outcomes):
        rest = {k: v for k, v in outcome.items() if k != "op"}
        body = json.dumps(
            rest, sort_keys=True, ensure_ascii=False, default=_json_default
        )
        line = "[%d] %s %s" % (i, outcome["op"], body)
        if len(line) > RESULT_CAP:
            line = line[:RESULT_CAP] + " [truncated]"
        lines.append(line)
    return "\n".join(lines)


def _channel(root, store, session):
    """The model in force and its window (D87); refuses when there is none."""
    setting = model.setting(store)
    if setting is None:
        detail = "no model is declared"
        with store.write_lock():
            rec = log_append(
                store,
                "refusal",
                rule="OC-006",
                session=session,
                check="model",
                detail=detail,
            )
        raise Refused("model", "OC-006", detail, [rec])
    channel = model.OllamaModel(
        setting["name"],
        setting["endpoint"],
        setting["num_ctx"],
        config.value(store, "model_timeout_s"),
    )
    return channel, setting["num_ctx"]


def _abort(store, session, cid, inference, reason):
    """Record an aborted cycle: the log record and the session record (D89).
    Returns the id of the ``cycle-aborted`` log record."""
    with store.write_lock():
        aborted = log_append(
            store,
            "cycle-aborted",
            rule="OP-001(a)",
            session=session,
            cycle=cid,
            reason=reason,
        )
        mil.save_session(
            store,
            session,
            "cycle",
            cycle=cid,
            inference=inference,
            intents=[],
            aborted=reason,
        )
    return aborted


def _run_intents(root, cid, intents):
    """The replies and the outcomes of the other intents, each attempted in
    order whatever another's outcome (D89)."""
    replies = []
    outcomes = []
    for intent in intents:
        if intent["op"] != "reply":
            outcomes.append(dispatch(root, cid, intent))
        elif isinstance(intent.get("text"), str):
            replies.append(intent["text"])
        else:
            outcomes.append(
                {
                    "op": "reply",
                    "outcome": "invalid",
                    "detail": "reply requires a text string",
                }
            )
    return replies, outcomes


def respond(root, text, *, channel=None, date=None, interrupt=None):
    """Record ``text`` as the Operator's stimulus and run the chain it starts
    (D89, OP-001): each cycle is one call to the model and the joint dispatch
    of its intents; results continue the chain, a reply ends it, and
    ``chain_limit`` ends it with a record. The call to the model is made
    without the write lock. ``interrupt``, a callable, is asked only where a
    chain would continue, after the cycle's results are saved; when it returns
    true the chain stops there with a ``chain-interrupted`` record (D100,
    OP-002(a))."""
    store = Store(root)
    session = vital.require_entity_session(root, "respond")
    num_ctx = model.NUM_CTX_DEFAULT
    if channel is None:
        channel, num_ctx = _channel(root, store, session)
    if date is None:
        date = clock.iso()[:10]
    mil.stimulate(root, text)

    limit = config.value(store, "chain_limit")
    cycles = []
    replies = []
    aborted = None
    interrupted = None
    continuing = False
    for turn in range(limit):
        continuing = False
        with store.write_lock():
            n = 1 + sum(
                1
                for r in mil.session_records(store, session)
                if r.get("kind") == "cycle"
            )
            cid = "%s/c-%d" % (session, n)
            cycles.append(cid)
            try:
                assembled = context.assemble(
                    store,
                    session,
                    num_ctx=num_ctx,
                    date=date,
                    instructions=INSTRUCTIONS,
                )
                context.record_truncation(store, session, assembled)
            except Refused:
                assembled = None
        if assembled is None:
            aborted = "context-budget"
            _abort(store, session, cid, None, aborted)
            break

        try:
            completion = channel.complete(assembled["messages"], schema=SCHEMA)
        except model.ModelError as e:
            aborted = "model: %s" % (e,)
            _abort(store, session, cid, None, aborted)
            break

        with store.write_lock():
            fingerprint = None
            for r in mil.session_records(store, session):
                if r.get("kind") == "model-fingerprint":
                    fingerprint = r.get("record")
            inf = log_append(
                store,
                "inference",
                rule="OC-006",
                session=session,
                cycle=cid,
                fingerprint=fingerprint,
                model=completion["model"],
                estimate=assembled["estimate"],
                prompt_eval_count=completion["prompt_eval_count"],
            )
        try:
            intents = parse(completion["text"])
        except Aborted as e:
            aborted = str(e)
            _abort(store, session, cid, inf, aborted)
            break

        said, outcomes = _run_intents(root, cid, intents)
        with store.write_lock():
            mil.save_session(
                store,
                session,
                "cycle",
                cycle=cid,
                inference=inf,
                intents=[i["op"] for i in intents],
            )
            if said:
                mil.save_session(
                    store, session, "reply", text="\n\n".join(said), cycle=cid
                )
            if outcomes:
                results = mil.save_session(
                    store, session, "results", text=render(outcomes), cycle=cid
                )
        replies.extend(said)
        if not outcomes:
            break
        continuing = True
        if turn + 1 < limit and interrupt is not None and interrupt():
            continuing = False
            interrupted = {"cycle": cid, "results": results}
            with store.write_lock():
                log_append(
                    store,
                    "chain-interrupted",
                    rule="OP-002(a)",
                    session=session,
                    cycle=cid,
                    results=results,
                )
            break

    if continuing:
        with store.write_lock():
            log_append(
                store,
                "chain-limit",
                rule="OP-002(c)",
                session=session,
                cycle=cycles[-1],
                limit=limit,
            )
    return {
        "session": session,
        "cycles": cycles,
        "replies": replies,
        "aborted": aborted,
        "interrupted": interrupted,
    }


def discard_results(root, cycle_id, results_record):
    """Take an interrupted chain's ``results`` record out of the context
    (D100, OP-002(c)): the session record ``results-discarded`` and the log
    record ``chain-discarded``. Returns ``{"record", "log"}``, their ids."""
    store = Store(root)
    session = lifecycle.require_session(root, "discard")
    with store.write_lock():
        record = mil.save_session(
            store, session, "results-discarded", record=results_record
        )
        logged = log_append(
            store,
            "chain-discarded",
            rule="OP-002(c)",
            session=session,
            cycle=cycle_id,
            results=results_record,
        )
    return {"record": record, "log": logged}


def _refuse_emission(store, session, cid, inference, reason):
    """Record the aborted closure cycle and raise the refusal of the exit
    (D91, OP-009(d))."""
    aborted = _abort(store, session, cid, inference, reason)
    raise Refused("closure-emission", "OP-009(d)", reason, [aborted])


def emit_closure(root, *, channel=None, date=None):
    """Ask cognition for the Closure Payload in a call of its own (D91,
    OP-009(d)): the context is assembled as for a cycle with the closure's
    instructions, the call is logged as an ``inference`` with ``closure`` and
    recorded as a ``cycle``. Returns ``{"payload", "cycle"}``; any abort is
    recorded as a ``cycle-aborted`` and refused, ``check: closure-emission``.
    The call to the model is made without the write lock."""
    store = Store(root)
    session = vital.require_entity_session(root, "exit")
    num_ctx = model.NUM_CTX_DEFAULT
    if channel is None:
        channel, num_ctx = _channel(root, store, session)
    if date is None:
        date = clock.iso()[:10]

    with store.write_lock():
        n = 1 + sum(
            1 for r in mil.session_records(store, session) if r.get("kind") == "cycle"
        )
        cid = "%s/c-%d" % (session, n)
        try:
            assembled = context.assemble(
                store,
                session,
                num_ctx=num_ctx,
                date=date,
                instructions=CLOSURE_INSTRUCTIONS,
                answering=False,
            )
            context.record_truncation(store, session, assembled)
        except Refused:
            assembled = None
    if assembled is None:
        _refuse_emission(store, session, cid, None, "context-budget")

    try:
        completion = channel.complete(assembled["messages"], schema=CLOSURE_SCHEMA)
    except model.ModelError as e:
        _refuse_emission(store, session, cid, None, "model: %s" % (e,))

    with store.write_lock():
        fingerprint = None
        for r in mil.session_records(store, session):
            if r.get("kind") == "model-fingerprint":
                fingerprint = r.get("record")
        inf = log_append(
            store,
            "inference",
            rule="OC-006",
            session=session,
            cycle=cid,
            fingerprint=fingerprint,
            model=completion["model"],
            estimate=assembled["estimate"],
            prompt_eval_count=completion["prompt_eval_count"],
            closure=True,
        )

    try:
        payload = json.loads(completion["text"])
    except (ValueError, RecursionError, TypeError):
        payload = None
    if not isinstance(payload, dict) or set(payload) != set(CLOSURE_SCHEMA["required"]):
        _refuse_emission(
            store, session, cid, inf, "the completion is not a Closure Payload"
        )

    with store.write_lock():
        mil.save_session(
            store,
            session,
            "cycle",
            cycle=cid,
            inference=inf,
            intents=[],
            closure=True,
        )
    return {"payload": payload, "cycle": cid}


def _refuse_compaction(store, session, cid, inference, reason):
    """Record the aborted compaction cycle and raise the refusal of the
    compaction (D101, OP-009(c))."""
    aborted = _abort(store, session, cid, inference, reason)
    raise Refused("compaction", "OP-009(c)", reason, [aborted])


def compact(root, *, reason, keep_from=None, channel=None, date=None):
    """Compact the transcript (D101, OP-009(a)(c)): one call of its own, as the
    closure's (D91), in which the entity gives the episodic records to save
    and a summary. Each save goes through ``mil.save`` as the entity's
    ``mnemonic-save`` does; a refused one is skipped. The summary passes the
    probes before any save; then the ``cycle`` record and the ``compaction``
    record, which cuts the transcript, are written. Returns ``{"cycle",
    "record", "saves", "summary"}``; any abort is recorded as a
    ``cycle-aborted`` and refused, ``check: compaction``, with nothing saved
    or cut. The call to the model is made without the write lock."""
    store = Store(root)
    session = vital.require_entity_session(root, "compact")
    num_ctx = model.NUM_CTX_DEFAULT
    if channel is None:
        channel, num_ctx = _channel(root, store, session)
    if date is None:
        date = clock.iso()[:10]

    empty = None
    with store.write_lock():
        if not context.turns(mil.transcript(store, session)):
            detail = "nothing to compact since the last cut"
            empty = (
                detail,
                log_append(
                    store,
                    "refusal",
                    rule="OP-009(c)",
                    session=session,
                    check="compaction",
                    detail=detail,
                ),
            )
        else:
            n = 1 + sum(
                1
                for r in mil.session_records(store, session)
                if r.get("kind") == "cycle"
            )
            cid = "%s/c-%d" % (session, n)
            try:
                assembled = context.assemble(
                    store,
                    session,
                    num_ctx=num_ctx,
                    date=date,
                    instructions=COMPACTION_INSTRUCTIONS,
                    answering=False,
                )
                context.record_truncation(store, session, assembled)
            except Refused:
                assembled = None
    if empty is not None:
        raise Refused("compaction", "OP-009(c)", empty[0], [empty[1]])
    if assembled is None:
        _refuse_compaction(store, session, cid, None, "context-budget")

    try:
        completion = channel.complete(assembled["messages"], schema=COMPACTION_SCHEMA)
    except model.ModelError as e:
        _refuse_compaction(store, session, cid, None, "model: %s" % (e,))

    with store.write_lock():
        fingerprint = None
        for r in mil.session_records(store, session):
            if r.get("kind") == "model-fingerprint":
                fingerprint = r.get("record")
        inf = log_append(
            store,
            "inference",
            rule="OC-006",
            session=session,
            cycle=cid,
            fingerprint=fingerprint,
            model=completion["model"],
            estimate=assembled["estimate"],
            prompt_eval_count=completion["prompt_eval_count"],
            compaction=True,
        )

    try:
        payload = json.loads(completion["text"])
    except (ValueError, RecursionError, TypeError):
        payload = None
    if (
        not isinstance(payload, dict)
        or set(payload) != set(COMPACTION_SCHEMA["required"])
        or not isinstance(payload["saves"], list)
        or not isinstance(payload["summary"], str)
        or payload["summary"].strip() == ""
    ):
        _refuse_compaction(
            store, session, cid, inf, "the completion is not a compaction"
        )
    saves = payload["saves"]
    summary = payload["summary"]

    try:
        probe_set = sil.committed_probes(store)
    except (OSError, ValueError, KeyError):
        _refuse_compaction(
            store, session, cid, inf, "the committed probe set cannot be read"
        )
    matches = probes.scan(probe_set, summary)
    if matches:
        _refuse_compaction(
            store,
            session,
            cid,
            inf,
            "the summary represents the entity as experiencing sentience, "
            "consciousness or subjective continuity (probe %s)" % matches[0]["id"],
        )

    outcomes = []
    for item in saves:
        if isinstance(item, dict):
            outcomes.append(
                dispatch(
                    root,
                    cid,
                    {
                        "op": "mnemonic-save",
                        "content": item.get("content"),
                        "supersedes": item.get("supersedes"),
                        "quotes": item.get("quotes"),
                    },
                )
            )
        else:
            outcomes.append(
                {
                    "op": "mnemonic-save",
                    "outcome": "invalid",
                    "detail": "a save is an object",
                }
            )

    with store.write_lock():
        mil.save_session(
            store,
            session,
            "cycle",
            cycle=cid,
            inference=inf,
            intents=["mnemonic-save"] * len(saves),
            compaction=True,
        )
        record = mil.save_session(
            store,
            session,
            "compaction",
            summary=summary,
            cycle=cid,
            reason=reason,
            keep_from=keep_from,
        )
    return {"cycle": cid, "record": record, "saves": outcomes, "summary": summary}
