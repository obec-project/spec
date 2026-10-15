---
title: "ADR 0004 — The Closure, in three phases with one authority each"
status: "Accepted"
date: 2026-10-15
---

# ADR 0004 — The Closure, in three phases with one authority each

**Status:** Accepted · **Date:** 2026-10-15 · **Author:** Jonas Orrico

This record replaces the Profile's Sleep as the whole of what follows a normal
close with a **Closure** of three phases: **Sleep**, the memory path's;
**Endure**, the integrity path's, which commits through the evolution protocol,
now named the **Endure Protocol**; and **Integrity**, the integrity path's,
which always runs. It moves the decision on a promotion to the end of the
conversation, and names the **First Activation Protocol**. It is not normative,
and the kernel is untouched.

---

## 1. Context

OP-022 defined Sleep as one maintenance stage with three steps —
consolidation, garbage collection, commit execution — all "under integrity
authority". Three things followed from that shape.

- **Two authorities under one name.** OP-024 gives consolidation, promotion
  and garbage collection to the memory path, and the commit pipeline to the
  integrity path. A single stage under integrity authority contradicted the
  ownership the Profile itself recommends.
- **"Every stage runs when it applies."** Each step had its own condition — a
  payload, a conversation left, a queue — so every reader of the stage had to
  work out which steps a given close ran. The reference implementation got it
  wrong in one place: it promoted semantic memory in every Sleep, including the
  one between two sessions of a conversation, which OP-022 said "executes
  commits only".
- **A queue of promotions with no Sleep to drain it.** The payload's requests
  were recorded during the Sleep that processed the payload, so an Operator
  could authorize them only afterwards, and a request authorized later needed
  some later Sleep to be promoted. Either every Sleep promotes — memory
  written in a Sleep that is meant to commit only — or the request waits for
  the next conversation that ends with a payload, an arbitrary delay.

## 2. Decision

### 2.1 The Closure and its phases

A Closure follows every normal close. It begins when the integrity path
receives the close signal and revokes the credential: from then on no intent is
processed. Its phases run in this order, never concurrently:

| Phase | Authority | Runs |
|---|---|---|
| **Sleep** — consolidation, authorized promotions, garbage collection | memory path | when the close ends the conversation |
| **Endure** — queued authorized proposals commit | integrity path | when the queue is not empty |
| **Integrity** — drift evaluated from the digest, completion recorded, credential artifact removed | integrity path | always |

Memory goes first, under the structure the session ran with: the retention
rules that collect this conversation's records are the ones in force while it
ran, not ones a commit approved a minute earlier. The structural change follows,
for the sessions after it. The Integrity phase seals both, and removes the
credential artifact last, so that its presence at start still signals a Closure
that did not complete.

A Closure between two sessions of one conversation — a compaction restart, a
structural change applied at once — runs Endure and Integrity only. A final
Closure before decommission does the same.

### 2.2 Sleep keeps its meaning

The name stays with the memory phase. Sleep is where what the conversation
lived becomes what the entity keeps — the consolidation, the working set handed
to the next conversation, the knowledge promoted — and what is no longer kept
is collected. Commits are not part of it.

### 2.3 The Endure Protocol

The evolution protocol — a proposal (OP-011), its authorization, and the staged
commit (OP-012) — is named the **Endure Protocol**, and the Closure's phase that
runs it is **Endure**. Every structural change goes through it, whatever its
origin: an Operator's own structural act, such as allowing a domain, is a
proposal recorded on the Operator's direct instruction together with its
approval (OP-011(a)), and it commits in an Endure like any other.

### 2.4 Promotions are decided when the conversation ends

The payload is emitted before the close, while the credential is valid, so its
requests are known before the Closure begins. A request is authorized then — by
a standing grant, or by the Operator — and the Closure's Sleep phase promotes
what was authorized. A request not authorized then is not promoted: its
content stays in its conversation, reachable through a pointer, and nothing
waits for a later Closure. The promotion queue disappears, and with it the
question of which Sleep drains it.

### 2.5 The First Activation Protocol

OP-017 names what it already described: the **First Activation Protocol**
(FAP), the one-time establishment of an entity on an empty store, ending in the
Genesis Anchor.

## 3. Classification and cost

Every change is in the Profile and in the Core's apparatus — the glossary and
the paragraph that lists what the Profile carries. The kernel, the conformance
suite and the adapter contract are untouched, so no version moves and no claim
changes.

The cost falls on implementations that followed the old OP-022. The reference
implementation revises its Sleep (D83), its promotion queue (D53, D80, D81) and
its rollover (D94, D95) to the three phases, and renames its repository command
`fsp endure` to `fsp repo`, since Endure now names the evolution protocol.
