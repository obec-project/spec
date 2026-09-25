---
title: "ADR 0002 — Invariant titles as statements"
status: "Proposed"
date: 2026-09-25
---

# ADR 0002 — Invariant titles as statements

**Status:** Proposed · **Date:** 2026-09-25 · **Author:** Jonas Orrico

This record gives the ten invariants titles that state their guarantees, a new
order for the first two, and three consistency changes that the titles made
visible. It is not normative.

---

## 1. Context

The titles of the ten invariants name topics, not guarantees. They take three
different forms:

- some name the domain: *Operator primacy*, *Host actuation is bounded*;
- some name a property and hide the domain: *Bounded existence* — bounded in
  what? *Stateless inference only* — a technical property, not a subject;
- one is a slogan, and one is a list of adjectives: *Verified start, or no
  start*; *The Entity Store is complete, portable, and disciplined*.

A reader cannot learn what the specification guarantees from the titles alone;
each body has to be read to find out what its invariant is about. HACA's early
drafts stated their rules as axioms, and read better for it.

An invariant is a statement that must hold in every reachable state, and
validating it means being able to describe what a violation would look like
([CONTRIBUTING §7](../CONTRIBUTING.md#7-challenging-an-invariant): an invariant
nobody can check is a slogan). A title can meet the same standard.

---

## 2. Decision

### 2.1 Every title is a statement

Each title states its invariant's guarantee as a claim that a violation could
falsify. The clauses stay in the body as the concrete cases of that claim; a
title that needs a section to define its own terms has failed.

**The clauses govern.** A title states the guarantee and the clauses define it;
where they differ, the clauses govern and the title is in error — the relation
the kernel page already has to Core §2. Titles are therefore not part of the
normative kernel under Core §4.1, and changing one is an editorial revision.

Read in sequence, the ten titles state the specification in one paragraph:

> An entity exists only bound to an Operator, who holds final authority over
> everything it is and does. The entity is not alive, and is never built or
> directed to act as if it were. Everything the entity is resides in its
> store, travels with it, and has one writer per class. The entity's identity
> is proven by an unbroken chain back to its Genesis Anchor. Integrity guards
> the entity, and nothing in the entity can disarm it. The model is
> cognition's stateless engine, and it only answers. What the entity has
> learned comes only from its memory. The entity acts only inside an isolated
> workspace its Operator declares, through skills its Operator admits. The
> entity is auditable by design: every boundary crossing leaves a record. The
> entity starts verified, or does not start.

### 2.2 The titles

| | Domain | Title | Previous title |
|---|---|---|---|
| **OC-001** | bond | An entity exists only bound to an Operator, who holds final authority over everything it is and does. | Operator primacy *(was OC-002)* |
| **OC-002** | nature | The entity is not alive, and is never built or directed to act as if it were. | Bounded existence *(was OC-001)* |
| **OC-003** | state | Everything the entity is resides in its store, travels with it, and has one writer per class. | The Entity Store is complete, portable, and disciplined |
| **OC-004** | identity | The entity's identity is proven by an unbroken chain back to its Genesis Anchor. | Unbroken chain to the Genesis Anchor |
| **OC-005** | integrity | Integrity guards the entity, and nothing in the entity can disarm it. | Integrity is beyond cognition's reach |
| **OC-006** | cognition | The model is cognition's stateless engine, and it only answers. | Stateless inference only |
| **OC-007** | knowledge | What the entity has learned comes only from its memory. | The Memory Store is the sole source of knowledge |
| **OC-008** | action | The entity acts only inside an isolated workspace its Operator declares, through skills its Operator admits. | Host actuation is bounded |
| **OC-009** | audit | The entity is auditable by design: every boundary crossing leaves a record. | Boundaries are crossed only by signal |
| **OC-010** | start | The entity starts verified, or does not start. | Verified start, or no start |

Each title was checked against its clauses so that it claims nothing the
clauses do not require. Where a word was chosen against a nearby alternative:

- **OC-001 — "final authority".** The phrase is the Operator's definition in
  the invariant's own preamble. *Authorizes everything it can do* would be
  false: consolidation writes mnemonic content every session without an
  Operator authorization, and an admitted skill runs without one per call.
  *Final* is what makes the title checkable — a violation is any Operator
  decision that some part of the implementation can block, delay, override,
  or substitute for.
- **OC-002 — "alive", "built", "directed".** *Alive* needs no definition.
  *Built* covers clauses (a) to (c), which constrain the operation set:
  sustaining, replicating or re-activating itself, resisting its end,
  returning from it. *Directed* is the verb of clause (d), which constrains
  what structural content tells the entity to be. *Never presents itself as
  if it were* was rejected because it promises what no implementation can
  keep: the clause governs what directs the entity and what it retains, not
  every sentence a model may produce in a session. *Being* was rejected
  because it invites a debate about what counts as one.
- **OC-003 — "resides", "class".** A verb of living things would contradict
  OC-002. *Class* is the term OC-003(c) uses.
- **OC-004 — "proven".** The invariant is about the guarantee of identity, not
  about the entity's existence.
- **OC-005 — "disarm".** Covers both things cognition cannot do to integrity:
  write it (OC-005(a), (b)) and reverse or condition its decisions
  (OC-005(c)). The previous title stated the mechanism; this one states what
  it protects.
- **OC-006 — both halves.** *Stateless* alone would not make a call carrying
  tool-use authority a violation, since such a call can be entirely stateless.
  *Only answers* does.
- **OC-007 — "has learned".** The clause governs persisted knowledge. *Knows*
  would take in transient session input, which the clause names as
  operational context, and what the model was trained on, which comes from no
  entity's memory.
- **OC-008 — "isolated workspace", "declares", "admits".** *Acts in
  isolation* reads in English as *acts on its own*. *Authorizes* is the term
  of OC-002(b)'s commits; the workspace may be an operational setting changed
  by an Operator act, which no standing grant covers. *Declares* is the term
  OC-008(a) uses. The last phrase is there because OC-008(a) bounds what an
  admitted skill's own code does by its admission under (c), not by the
  workspace.
- **OC-009 — "boundary".** *Crossing between parts* would reopen the gap
  [OPEN-QUESTIONS §4](OPEN-QUESTIONS.md#4-is-oc-009-an-invariant-or-an-observation)
  records: an implementation with no parts would satisfy it vacuously. The
  boundaries are the ones OC-005 through OC-008 require, not an
  implementation's module structure. The colon scopes *auditable by design* to
  what the body requires.

### 2.3 The domain replaces the locus

The tables of the set named a *locus* for each invariant, and the column mixed
kinds: an actor (Operator), an artifact (Entity Store), parts (integrity,
reasoning, memory, host), an activity (coordination), and a moment
(transition). It becomes the **domain** of the table above: what each
invariant is about.

### 2.4 OC-001 and OC-002 exchange places

The bond to an Operator is what every other invariant depends on, and the
entity's nature reads as a consequence of it. The order becomes: who the entity
is bound to, then what it is. The clauses keep their letters: Operator
primacy's (a) to (c) become OC-001(a) to (c), and bounded existence's (a) to
(d) become OC-002(a) to (d). The Primer already teaches the two in this order.

This is an exception to [ADR 0001 §2](0001-obec-restructure.md#2-decision),
item 5: *identifiers are assigned once and never reused*. The numbers are
reassigned instead of withdrawn, because:

- no release is 1.0, and identifiers freeze only there;
- the repository is not announced, no implementation exists outside the
  project, and no claim has been submitted to `conformance/claims/`;
- a withdrawn number at the head of the set would leave the set's first entry
  empty for the rest of its life.

The cost is the one ADR 0001's rule exists to prevent: records made before the
exchange cite the old numbers. Integrity logs record the rule a refusal names,
so a store made before the exchange reads `OC-001(c)` where the specification
now says `OC-002(c)`. Every store made before 1.0 is disposable, so no record
that matters is affected. The exception is made once, and the rule of ADR 0001
stands after it.

### 2.5 OC-002(d) is placed, and its test is split

[OPEN-QUESTIONS §3](OPEN-QUESTIONS.md#3-does-oc-001d-belong-in-an-invariant)
asks whether the clause forbidding self-representation as a subject belongs in
an invariant. Under the new title it does: the invariant is that the entity is
not alive, and being directed to present itself as alive is one of the ways of
being made to act as if it were. This settles the placement half of that
question.

It does not settle the test half. The test for (d) was a probe run against
consolidated content and a reviewer's reading of structural content, and one
sentence routes around a probe. The test now separates what the clause can
guarantee from what it can only detect:

- **structural content** — the persona — changes only by an authorized commit.
  A commit that would make it direct the entity to present itself as alive is
  refused, and a suite step now executes that check where a reviewer attested
  it before. This checks a requirement the kernel already states; it adds none;
- **consolidated content** grows without a commit. Pattern detection there is
  a floor, and the Core's note now says so.

### 2.6 One term: *cognition*

The specification used *reasoning* and *cognition* for the same thing. The
glossary defines *cognition* as "the reasoning activity of the entity", and the
Profile's component for it is the Cognitive Processing Engine. *Cognition*
becomes the only term in the specification documents and in the adapter
contract, whose operation field and boundary names change with it.

### 2.7 No metaphors

Titles, normative sentences, and notes state what they mean literally.

---

## 3. Classification and cost

| Change | Kind | Why |
|---|---|---|
| Titles, the rule that clauses govern, domain for locus | editorial | titles are not part of the normative kernel (§2.1) |
| OC-001 ↔ OC-002 | editorial | identifiers and cross-references change; no requirement does |
| *reasoning* → *cognition* in the kernel | editorial | the glossary already defines the two as one; each sentence keeps its meaning |
| *reasoning* → *cognition* in the adapter contract | suite | an adapter written against the previous contract needs changing |
| The executed step for OC-002(d) | suite | checks a requirement the kernel already states (Core §4.1: a better test does not change a guarantee) |

No version field changes outside a release commit. The CHANGELOG's
*Unreleased* already carries a hardening of OC-002(a), now OC-001(a), so the
next release is a major version whatever these changes are.

The exchange of OC-001 and OC-002 touches the specification, the suite, the
stub and the reference implementation together: the suite asserts the rule a
refusal names, so they change in one commit or the suite fails against both.
The reference implementation does not yet refuse a persona commit; the new
step for OC-002(d) fails against it until it does, and its backlog says so.

---

## 4. Not decided here

- **The first sentence of OC-004.** *The entity's identity is computed from its
  chain, never inferred from its behavior* — from
  [OPEN-QUESTIONS §1](OPEN-QUESTIONS.md#1-what-does-a-long-lived-entity-cost-and-does-its-record-stay-legible)
  — is a candidate for the opening of OC-004's body.
