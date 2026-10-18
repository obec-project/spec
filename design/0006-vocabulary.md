---
title: "ADR 0006 — How the specification speaks of the entity"
status: "Accepted"
date: 2026-10-18
---

# ADR 0006 — How the specification speaks of the entity

**Status:** Accepted · **Date:** 2026-10-18 · **Author:** Jonas Orrico

This record sets one rule for the vocabulary of the specification and its
reference implementation. A term that implies life, experience, autonomous
continuity or a subject is not used for the entity, its parts or its
processes. The rule renames the Profile's Vital Check, Heartbeat and Sleep,
and rewrites the passages of the Primer that speak of the entity as living or
thinking. No kernel sentence changes.

---

## 1. Context

OC-002 says the entity is not alive, and is never built or directed to act as
if it were. The documents that state it describe the entity in the vocabulary
of a living thing. The Profile checks it with a Vital Check on a Heartbeat and
ends its conversations with a Sleep. The Primer calls a session "the life of
that credential", says a revocation stops the entity "mid-thought", and titles
a section "A life".

Three defects follow, of different weight.

- **Some terms assert what OC-002 forbids.** A sleep is something one wakes
  from, and waking on one's own is the self-activation OC-002(a) rules out. A
  heartbeat and vital signs are what a living thing has continuously, and in
  OBEC nothing runs unless the Operator starts a session. These terms are not
  loose metaphors: they say the opposite of the invariant.
- **In an implementation, the vocabulary reaches the model.** An
  implementation whose close is called a sleep tends to say so in the
  instructions it sends: "you will now sleep; what did you learn today?" That
  text directs the model to present itself as a subject, which OC-002 forbids
  in its title. The probes of OC-002(d) do not see it, since they read what is
  proposed and consolidated, not what the implementation writes into the
  context.
- **The text undermines its own claim.** A reader weighing whether OBEC means
  what OC-002 says, an auditor for instance, finds a specification that denies
  the entity is alive while describing its heartbeat and its sleep. The
  contradiction is easy to point at, and it costs credibility the
  specification has no reason to lose.

## 2. Decision

### 2.1 The rule

A term that implies life, experience, autonomous continuity or a subject is
not used for the entity, its parts or its processes. A term the technical
field already uses without that implication is kept, even where it was
borrowed from human life.

Two uses fall outside the rule:

- **Stating what the entity is not.** OC-002's title, "present itself as
  alive" and "an inner life" name the prohibition, and keep their words.
- **Data idioms.** State that "lives in" the store, a Skill Index "living
  only" for a session, a "live" session: computing uses these for where data
  resides and whether a session is active, and none implies a subject.

The rule joins the guiding principles of CONTRIBUTING §1, beside *terms
before use* and *vendor neutrality*.

### 2.2 What is renamed

| Was | Becomes |
|---|---|
| **Vital Check** | **Integrity Check** |
| **Heartbeat**, the recurring cycle of those checks | no term of its own: the cadence of the integrity checks |
| **Sleep**, the Closure's first phase | **Memory**, the memory path's phase, beside Endure and Integrity |

The Primer's passages are rewritten:

| Section | Was | Becomes |
|---|---|---|
| §1 | "every moment of the entity's life" | "every moment from first activation to decommission" |
| §4.1 | "the entity stops, mid-thought" | "the entity stops, mid-cycle" |
| §6 | "the quality of the thinking, not the identity of the thinker" | "the quality of the reasoning, not the identity of the entity" |
| §6.1 | "every structural change in this entity's life" | "every structural change in this entity's history" |
| §9 | the title "A life" | "Start, session, close" |
| §9 | "A session is the life of that credential"; "thinking, recalling"; "never cuts a thought in half"; "for the entity's whole life" | "A session lasts as long as that credential"; "reasoning, recalling"; "never cuts a cycle in half"; "until the entity is decommissioned" |
| §10 | "How the entity thinks"; "what reaches the thinking and what the thinking reaches, and says nothing about the thinking" | "How the entity reasons"; the same sentence with "reasoning" |

### 2.3 What is kept

| Term | Why |
|---|---|
| *memory*, *recall*, *remembers*, *episodic*, *semantic* | computing and the literature on language agents use them for stored state and its retrieval |
| *learned* | the sense of machine learning |
| *Genesis Anchor* | the idiom for the first block of a chain |
| *entity*, *persona* | technical senses; whether *entity* earns its keep against *agent* is open question 11 |
| *health signal*, *Nominal*, *Degraded*, *Critical* | the vocabulary of operations monitoring |
| *Endure* | names a protocol for changes that last, and implies no subject |
| *cognitive*, for the entity as a whole; *reasons*, for what the model does | [ADR 0007](0007-cognition.md), which renames the part that was called *cognition* |

### 2.4 In the reference implementation

fsp-ref-min follows the rule in its names and, above all, in the text it
sends to the model: the persona written at first activation, the
instructions for answering, and the request at the close. Its close consolidates; nothing in it sleeps.

fsp-ref-profile is frozen at OBEC-Core 0.12.0 and keeps its names until it is
revised, as released history keeps its names.

### 2.5 Text that changes

- **CONTRIBUTING §1:** the rule of §2.1.
- **The Profile:** the renames of §2.2, in OP-003 and in every rule, table
  and configuration entry that cites them.
- **The Core:** the same renames in §3, in the glossary of §7, whose entries
  move to their new alphabetical places, and in the Appendix.
- **The Primer:** the rewrites of §2.2.
- **ADR 0004** named the Closure's first phase *Sleep*. The name is superseded
  here, and ADR 0004 is not edited.

Unchanged: the kernel, the suite and the adapter contract, where none of
these terms appears, and the entries already in the CHANGELOG.

## 3. Classification and cost

No kernel sentence changes, so no version moves. The Profile and the Core's
apparatus are revised without a version boundary, and the suite reads none of
the renamed terms, so its version does not move either.

The cost is one pass over the Profile, about twenty-five occurrences, the
Core, about six, and the Primer, about ten. Doing it before 1.0 renames
the terms before anyone outside the project has learned them.
