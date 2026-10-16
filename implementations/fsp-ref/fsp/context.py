# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The sources of assembled context: the table context assembly runs on and
describe context-sources reports (D78, OC-007), and the assembly itself, by
priority within a budget (D88)."""

from __future__ import annotations

import math

from . import chain, config, lifecycle, mil, model, sil
from .sil import Refused, log_append
from .store import Store

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


# -- assembly by priority within a budget (D88, OC-007) -----------------------

CHARS_PER_TOKEN = 3.5
_MEMORY_LINE = 120
_TITLES = (
    "Persona",
    "Instructions",
    "Session",
    "Always loaded",
    "Working set",
    "This conversation's memory",
    "Semantic index",
)


def tokens(text) -> int:
    """The estimate of ``text`` in tokens: characters over ``CHARS_PER_TOKEN``,
    rounded up (D88)."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def turns(records) -> list:
    """The turns of a transcript (D88): each a ``stimulus`` and the ``reply``
    and ``results`` records after it, up to the next ``stimulus``. Records
    before the first stimulus, and of other kinds, are left out."""
    found = []
    for record in records:
        kind = record.get("kind")
        if kind == "stimulus":
            found.append([record])
        elif kind in ("reply", "results") and found:
            found[-1].append(record)
    return found


def render(turn) -> list:
    """The messages of one turn, in order (D88): the stimulus as ``user``, the
    reply as ``assistant``, the results as ``user`` under a ``Results:`` line."""
    messages = []
    for record in turn:
        kind = record.get("kind")
        text = record.get("text", "")
        if kind == "stimulus":
            messages.append({"role": "user", "content": text})
        elif kind == "reply":
            messages.append({"role": "assistant", "content": text})
        elif kind == "results":
            messages.append({"role": "user", "content": "Results:\n" + text})
    return messages


def _turn_cost(turn) -> int:
    return sum(tokens(m["content"]) for m in render(turn))


def _line_cost(line) -> int:
    return tokens(line) + 1


def _section_cost(title, lines) -> int:
    """The cost of a section: its header and its lines, nothing when empty."""
    if not lines:
        return 0
    return tokens("# " + title) + 1 + sum(_line_cost(line) for line in lines)


def _always_line(record) -> str:
    return "- [%s] %s: %s (%s)" % (
        record.get("category"),
        record.get("slug"),
        record.get("content"),
        record.get("id"),
    )


def _memory_line(record) -> str:
    first = str(record.get("content", "")).split("\n")[0]
    return "- (%s) %s" % (record.get("id"), first[:_MEMORY_LINE])


def _refuse_budget(store: Store, session, needed, budget) -> Refused:
    detail = "what always goes in needs %d tokens, the budget is %d" % (needed, budget)
    rec = log_append(
        store,
        "refusal",
        rule="OC-007",
        session=session,
        check="context-budget",
        detail=detail,
    )
    return Refused("context-budget", "OC-007", detail, [rec])


def assemble(
    store: Store, session, *, num_ctx, date, instructions="", answering=True
) -> dict:
    """The messages of one call, by priority within a budget (D88, OC-007).

    What always goes in is the persona, the instructions, the session's meta,
    the first turn and the current one; when it does not fit, the call is
    refused, ``context-budget``. Then, while they fit: the always-loaded
    semantic records (dropped as D77 says), the working set, the other turns
    newest first, the conversation's memory as an index, the semantic index.
    With ``answering`` false and no turn, no turn goes in (D98).
    Deterministic; writes only a refusal."""
    budget = num_ctx - config.value(store, "answer_reserve")
    ts = turns(mil.transcript(store, session))
    if not ts and answering:
        raise ValueError("the session %s has no stimulus to answer" % session)
    first, current = (ts[0], ts[-1]) if ts else (None, None)
    conversation = mil.conversation_of(store, session)
    chosen = model.setting(store)
    persona = store.read_bytes(
        chain.gen_relpath(sil.read_head(store)["entry"]) + "/persona.md"
    )
    persona = persona.decode("utf-8", errors="replace").rstrip()

    sections = {title: [] for title in _TITLES}
    sections["Persona"] = [persona] if persona else []
    sections["Instructions"] = [instructions] if instructions else []
    sections["Session"] = [
        "session: %s" % session,
        "conversation: %s" % (conversation if conversation is not None else "none"),
        "model: %s" % (chosen["name"] if chosen is not None else "none"),
        "date: %s" % date,
    ]
    used = sum(_section_cost(t, sections[t]) for t in _TITLES)
    if first is not None:
        used += _turn_cost(first)
    if current is not first:
        used += _turn_cost(current)
    if used > budget:
        raise _refuse_budget(store, session, used, budget)

    def room():
        return budget - used

    dropped = {
        "turns": [],
        "always_loaded": [],
        "working_set": [],
        "episodic": [],
        "index": [],
    }

    # Always-loaded semantic records: all, or fewer by D77's order.
    loaded = mil.always_loaded(store)
    kept = list(loaded)
    victims = [
        r
        for c in reversed(mil.always_loaded_categories(store))
        for r in loaded
        if r.get("category") == c
    ]
    while kept and _section_cost("Always loaded", [_always_line(r) for r in kept]) > (
        room()
    ):
        victim = victims.pop(0)
        kept = [r for r in kept if r is not victim]
        dropped["always_loaded"].append(victim.get("id"))
    sections["Always loaded"] = [_always_line(r) for r in kept]
    used += _section_cost("Always loaded", sections["Always loaded"])

    def add(title, line):
        """Add ``line`` to ``title`` when it fits; say whether it did."""
        nonlocal used
        cost = _section_cost(title, sections[title] + [line]) - _section_cost(
            title, sections[title]
        )
        if cost > room():
            return False
        sections[title].append(line)
        used += cost
        return True

    # The working set: the pointer map's records that are the latest of their
    # lineage, in the map's order.
    latest = {r.get("id"): r for r in mil._latest(mil._scope(store, conversation))}
    named = []
    for entry in mil.pointer_map(store, conversation)["entries"]:
        rid = entry.get("id") if isinstance(entry, dict) else None
        if rid in latest and rid not in named:
            named.append(rid)
    included = set()
    for rid in named:
        if add("Working set", "- (%s) %s" % (rid, latest[rid].get("content"))):
            included.add(rid)
        else:
            dropped["working_set"].append(rid)

    # The other turns, newest first; the first that does not fit ends them.
    middle = ts[1:-1]
    taken = []
    for turn in reversed(middle):
        cost = _turn_cost(turn)
        if cost > room():
            break
        taken.append(turn)
        used += cost
    taken.reverse()
    dropped["turns"] = [t[0].get("id") for t in middle[: len(middle) - len(taken)]]

    # The conversation's own records, as an index of id and first line.
    if conversation is not None:
        own = [
            r
            for r in mil._latest(mil._scope(store, conversation))
            if r.get("conversation") == conversation and r.get("id") not in included
        ]
        for record in reversed(own):
            if not add("This conversation's memory", _memory_line(record)):
                dropped["episodic"].append(record.get("id"))

    for item in mil.semantic_index(store):
        line = "- (%s) [%s] %s" % (item["id"], item["category"], item["slug"])
        if not add("Semantic index", line):
            dropped["index"].append(item["id"])

    system = "\n\n".join(
        "# %s\n%s" % (t, "\n".join(sections[t])) for t in _TITLES if sections[t]
    )
    messages = [{"role": "system", "content": system}]
    if first is not None:
        messages.extend(render(first))
    for turn in taken:
        messages.extend(render(turn))
    if current is not first:
        messages.extend(render(current))
    return {
        "messages": messages,
        "estimate": sum(tokens(m["content"]) for m in messages),
        "budget": budget,
        "dropped": dropped,
    }


def record_truncation(store: Store, session, assembled):
    """Record what ``assemble`` left out, once per change (D88): a
    ``context-truncated`` session record when the turns or the always-loaded
    records dropped differ from the session's last one, and a notice to the
    Operator for each always-loaded record that newly left (D66). Returns the
    id of the record written, or ``None``. Called with the store lock held."""
    dropped = assembled["dropped"]
    entry = {
        "dropped_from": dropped["turns"][0] if dropped["turns"] else None,
        "dropped_to": dropped["turns"][-1] if dropped["turns"] else None,
        "always_loaded": dropped["always_loaded"],
    }
    last = None
    for record in mil.session_records(store, session):
        if record.get("kind") == "context-truncated":
            last = record
    if last is None:
        if entry == {"dropped_from": None, "dropped_to": None, "always_loaded": []}:
            return None
    elif all(last.get(key) == value for key, value in entry.items()):
        return None
    rid = mil.save_session(
        store, session, "context-truncated", **entry, budget=assembled["budget"]
    )
    before = last.get("always_loaded") if last is not None else None
    before = before if isinstance(before, list) else []
    new = [i for i in entry["always_loaded"] if i not in before]
    if new:
        cred = lifecycle._read_credential(store)
        binding = cred.get("binding") if isinstance(cred, dict) else None
        lifecycle._notify(store, binding, "context-dropped", new)
    return rid
