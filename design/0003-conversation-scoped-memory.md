---
title: "ADR 0003 — Episodic memory belongs to its conversation"
status: "Accepted"
date: 2026-09-27
---

# ADR 0003 — Episodic memory belongs to its conversation

**Status:** Accepted · **Date:** 2026-09-27 · **Author:** Jonas Orrico

This record introduces the conversation — a sequence of sessions an Operator
continues as one — scopes episodic memory to it, makes episodic records
immutable, points the next conversation at the working set instead of copying
it, and lets only an Operator leave a conversation or bring a past one back. It
places the transcript in the Memory Store, never recalled, and leaves the
normative kernel as it is. It is not normative.

---

## 1. Context

The memory design came from HACA (Host-Agnostic Cognitive Architecture) without revision. Memory serves two purposes
with opposite needs:

- **continuity of work.** An entity saves its work as it goes, so that when its
  context is lost — a compaction restart under OP-010, a context cleared, the
  terminal closed — it recovers what it was doing through recall. This needs
  many writes, no friction, and no human in the loop. Its value lasts as long
  as the task.
- **accumulated knowledge.** What the entity has learned and digested, recalled
  in place of re-reading its sources. Few writes, and it shapes behavior from
  then on.

The Profile governs memory on another line. Episodic memory is consolidated at
close into the Memory Store, where every later session can recall it.
Promotion into semantic memory is gated by the drift comparison of OP-005(a),
and MAY require an Operator authorization. Content that fails the gate *"stays
episodic, and recallable"* (OP-009(c)). The gate therefore decides what is
labelled semantic, not what reaches cognition: content refused at promotion
still returns to context in every later session through episodic recall.

Where the risk lies is persistence: content that outlives the work it served
and returns to context later. Under the Profile, episodic memory persists with
no gate; the gate sits between two kinds of persistent memory.

Requiring an Operator authorization for every memory write would close the gap
and remove the first purpose. An entity with a small context window, saving its
work before each compaction restart, would wait for an Operator every time, and
a long task with no Operator present would stop.

The session is the wrong unit to scope memory by. A session is the life of one
credential, and a credential ends for reasons that do not end the work: a
compaction restart, a structural change applied at once, a change of model, the
terminal closed. The last is a crash under OP-018, and the most common way an
Operator stops. The Core already treats one of these as continuity: a
compaction restart *"continues the same Operator-initiated operation"* (OC-002,
note on self-activation).

The Closure Payload already names the working set: it declares *"the working
context the next session needs"* (OP-009(a)), and the Resumption Record turns
it into a pointer map within a limit declared in configuration (OP-009(d)).
Naming a record decides only what is loaded at the next start; what is not
named remains recallable anyway.

The reference implementation departed from the Profile here. A conversation is
not a session: it is what the Operator sees, continuous across sessions, and
the terminal closed leaves it intact for the Operator's return (D8). Its
episodic memory is written during the session, not only at close (D11), and
only appended to; the deterministic probes run on every episodic write (D12);
and semantic promotion requires an Operator authorization naming the digest of
the content (D53). Its backlog asks the specification to define the
conversation (G8) and to adopt D11 (G10).

---

## 2. Decision

### 2.1 The conversation

A **conversation** is a sequence of sessions that an Operator continues as one.
A new session continues the current conversation unless an Operator ended it.
A conversation therefore continues across a compaction restart, a structural
change applied at once, a change of model, a crash, and the terminal closed.

One conversation is current at a time, since sessions over a store never run
concurrently (OC-003(d)). Only an Operator leaves it, in one of three ways:

- **ending it with a Closure Payload.** The payload names the working set
  (§2.4), and the Sleep that follows consolidates, processes promotions,
  collects garbage and executes commits. The conversation ends when that Sleep
  completes; a crash before then leaves it open, and OP-018 re-executes the
  Sleep from the payload if one was emitted.
- **starting a new one.** The current conversation is left with no payload,
  and nothing is carried forward: the new conversation starts with no working
  set.
- **resuming a past one** (§2.5). The current conversation is left with no
  payload, and the past one becomes current.

A conversation left in any of these ways can be resumed later, for as long as
the retention rules keep it (§2.8). Cognition may close a session — under
OP-010, or by a close intent — and never leaves a conversation.

Separately, an Operator may **clear the transcript**: the conversation's history
leaves the context assembled for cognition, and the conversation, with its
memory, continues.

The term is *conversation* because the reference implementation already uses
it and G8 asks for it. *Operation*, the word of OC-002's note, is taken: an
intent names one operation of one owner.

### 2.2 Episodic memory belongs to the conversation that writes it

Episodic memory is written freely during a session through the mnemonic path,
as D11 already does, and is recallable in every session of the same
conversation, including after the transcript is cleared. A later conversation
recalls it only through a pointer (§2.4, §2.5).

A conversation's **recall scope** is the episodic records it wrote and the
records its pointer map names. A recall that would return a record outside the
scope is refused and logged. The transcript is never in the recall scope
(§2.10).

### 2.3 Records are immutable

An episodic record is never edited, in the conversation that wrote it or in any
other. It is removed only by expiry under the retention rules (§2.8).

To update what it knows for a new round of a task, cognition writes a new
record that names the record it **supersedes**. The new record belongs to the
conversation that writes it, and may supersede a record from an earlier
conversation that the pointer map brought into scope. Following the
supersedes links from any record gives its **lineage**, back to the first
record, its root.

Recall returns the latest record of each lineage: the one that no record in
scope supersedes. Asking for a lineage returns its earlier records that are in
scope, and names, without returning, those that are not.

Two things depend on immutability. D53 authorizes a promotion by naming the
digest of the content; a record edited while its promotion is pending would
either no longer match the authorization or be promoted with content the
Operator never saw. And the provenance D36 records — which model, in which
cycle, wrote what — holds only if what was written stays as written.

### 2.4 The Closure Payload points the next conversation at its working set

The payload's declaration of working context names the records the next
conversation needs, and the Resumption Record carries them as a pointer map,
within the limit declared in configuration. The map names the latest record of
each lineage.

Nothing is copied. A record stays in the conversation that wrote it, with the
session that produced it, as OC-003(e) requires; the pointer map is attributed
to the conversation that emitted it. A record the payload does not name stays
where it is, outside the next conversation's scope.

### 2.5 Only an Operator brings a past conversation back

An Operator brings a past conversation back in one of two ways:

- **injecting its records.** Episodic records of a past conversation, all of
  them or those the Operator selects, are added to the current conversation's
  pointer map, attributed to the Operator's binding. The current conversation
  continues, with those records in its scope and without their transcript.
  This carries earlier work into the task at hand.
- **resuming it.** The past conversation, named by its identifier, becomes the
  current one (§2.1): its transcript since its last clear enters the context
  again (§2.10), and its recall scope is what it was when it was left. Records
  written in later conversations are not in that scope, including those that
  supersede its own, so the conversation returns as it stood. This recovers
  what happened in it and lets the work continue from there.

Each is an Operator act, logged like any other, and performed through means
the implementation provides directly to the Operator. An Operator who only
wants to read a past conversation needs neither: its transcript and records
are in the store, which the Operator can read directly.

Cognition never brings a conversation back, and nothing it writes adds to the
scope except its own records. If cognition could reach past conversations, the
archive would again be memory that persists without a gate and returns to
context, which is the gap §1 describes.

### 2.6 Only semantic memory crosses conversations on its own

Promotion remains the gate (OP-009(c)), and it requires an Operator
authorization: a per-promotion approval, or a standing grant over a scope that
covers promotion, bounded like any other (OC-001(b)). The Profile raises this
from MAY to SHOULD. The authorization names the digest of the content it
covers, as D53 does, so what is promoted is exactly what was authorized. The
deterministic probes run first, and content they flag is never offered.

Semantic memory is the only memory that crosses conversations on its own, so
the gate carries more weight here than when the Profile made authorization
optional. The probes catch the patterns they name, and not a planted fact; an
Operator's reading is the check that does.

A promotion refused leaves the content in its conversation, reachable only by
a pointer. The sentence *"the content stays episodic, and recallable"* becomes
*the content stays in its conversation*.

How many pointer maps have named a lineage can be computed from the Resumption
Records. An implementation MAY use that count to propose promotions or to
order them for review. It never replaces the gate: how often a lineage was
carried forward measures how often cognition chose to keep it, not whether it
is true, and content planted in a conversation is carried forward like any
other.

### 2.7 An optional limit on age

Configuration MAY declare a maximum age for a lineage, counted in conversation
boundaries — a conversation ended, started or resumed — since its root was
written. A pointer map does not name a lineage past the limit: it stays where
it is, reachable by §2.5, or it is promoted through the gate. Every
conversation boundary is an Operator act, so the count needs no criterion
beyond the log, and it stays well defined when a past conversation is resumed.
Counting from the root keeps a new version from resetting the age.

The limit keeps the working set from carrying stale records indefinitely. It
does not bound a cognition that means to keep content alive: citing the
record superseded is up to cognition, and a record that restates old content
without citing it starts a new lineage. A restatement with identical text is
detectable by its digest; a paraphrase is not. No mechanical rule closes this
short of an Operator authorization for carrying records forward, which §1
rules out. What bounds it is the Operator, who ends conversations and can end
one without a payload; the deterministic probes, which OC-002(d) requires and
the reference implementation runs on every write (D12); and provenance, which
finds everything a given model wrote (D36).

### 2.8 Retention

The records of conversations other than the current one — session records and
episodic memory alike — are kept under retention rules declared in
configuration, which may differ for the two. Expiry under those rules is the
only way they are removed, and it is logged. A record is kept while the
current conversation's pointer map names it or a pending promotion refers to
it, as D53 already does for session records. A conversation whose records have
partly expired is resumed with what remains.

An expired episodic record leaves its identifier, content digest, session of
origin and supersedes link, so a lineage can still be followed after its
content is gone.

### 2.9 The Profile keeps the deterministic probes

The probabilistic layer of OP-005(b) — similarity metrics, run when the
deterministic layer is inconclusive — leaves the Profile. What remains is the
deterministic layer: required keywords, forbidden patterns and content hashes,
which confirm drift without inference and include the patterns OC-002(d)
requires. Hardening drift detection beyond that floor is the Security
extension's scope.

With episodic memory scoped to its conversation and promotion under an
Operator authorization, the similarity comparison had one place left to act,
the promotion gate, where the Operator's reading now does what it could not. It
also carried the anchor staleness recorded in
[OPEN-QUESTIONS §1](OPEN-QUESTIONS.md#1-what-does-a-long-lived-entity-cost-and-does-its-record-stay-legible):
an entity that grows legitimately moves away from anchors fixed at first
activation, and a comparison against them either blocks that growth or is
relaxed until it blocks nothing.

### 2.10 The transcript is in the Memory Store, and never recalled

The Memory Store holds three kinds of mnemonic content: the **session
records** — the transcript of each session, its intents, results and events,
and the Closure Payload — episodic memory, and semantic memory. The Profile's
session store becomes this part of the Memory Store, not a store beside it,
as the reference implementation already lays them out. The memory path is the
one path that writes all three (OC-003(c)), and the one through which any of
them reaches cognition (OC-007).

The context assembled for cognition carries the current conversation's
transcript since its last clear, read through the memory path. That is the
only way a transcript reaches cognition: recall never returns one, whether
from before the clear or from another conversation. Clearing the transcript
therefore removes it from cognition's reach, and what the entity means to keep
it saves as episodic memory, which D13 already asks of it.

This settles the transcript under OC-007 as the invariant stands. A
conversation's history crosses sessions, and OC-007 exempts from recall only
*"transient session input"*; with the transcript in the Memory Store and read
through the memory path, it originates where OC-007 requires, and the
invariant needs no clarification.

---

## 3. Classification and cost

| Change | Kind | Why |
|---|---|---|
| The conversation, the three ways to leave it, clearing the transcript, injecting a past conversation's records, resuming a past conversation | profile | §2.1, §2.5 |
| The session store as part of the Memory Store; the transcript reaching cognition only through the assembled context | profile | §2.10: OP-009, and the MIL's row in the reference architecture |
| The Core's glossary entry for the Memory Store | docs | it gains the session records (§2.10); the glossary is outside the kernel |
| OP-009 (a) to (d) | profile | the Closure Payload ends a conversation and points the next at its working set; episodic memory is scoped to its conversation, immutable, updated by supersedes; promotion SHOULD require an Operator authorization naming the content's digest; §2.6's sentence |
| OP-005(b), OP-004(b) | profile | the probabilistic layer leaves the Profile; semantic drift is what the deterministic probes find (§2.9) |
| OP-010 | profile | a compaction restart continues the conversation, so it needs no Closure Payload and no pointer map |
| OP-018 | profile | a crash leaves the conversation open |
| OP-022 | profile | the Sleep that ends a conversation consolidates, promotes and collects garbage; a Sleep between two sessions of one conversation executes commits only, as D9 already does |
| The Primer, §3, §6.1 and §9 | docs | they describe memory as consolidated at every close into long-term memory that later sessions recall |

**The normative kernel does not change.** OC-003(c) already places session
records and consolidated memory in one class with one write path; OC-003(e)
already requires the attribution the pointer map preserves; and OC-007 holds
as it stands (§2.10).

The conformance suite has no step on how memory is organized, and does not
change.

In the reference implementation, episodic records are already appended, never
edited, its session records already sit beside episodic and semantic memory
under `memory/`, and recall already searches only episodic and semantic
memory. A record gains a supersedes link, recall returns the latest record of
each lineage within the conversation's scope, and D11 changes what a later
conversation can recall. D13 splits in two: clearing the transcript keeps the
conversation, and a new conversation leaves it without a payload. Commands to
inject a past conversation's records and to resume a past conversation by its
identifier are added; D8 and D53 stand, and the probabilistic layer planned
for its phase 7 leaves the plan. The change closes G8 and G10.
