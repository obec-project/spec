# OBEC — Operator-Bounded Entity Continuity

**A specification for AI entities whose identity, authority and boundaries are
verifiable from their own portable state.**

An entity is an agent whose claims about itself can be checked rather than
believed. It is built on a language model, which keeps nothing from one call to
the next. It reasons, remembers, and acts on a host — and it can prove four
things about itself:

1. **It is the entity that was activated.** Its instructions, skills and
   configuration trace back to its first activation through an unbroken chain
   of authorized changes. What it remembers is kept apart, and changes freely.
2. **Every one of those changes was authorized by a human.** The entity can
   propose changing itself. It can never approve one.
3. **That proof travels with it.** Copy the entity's files to another host and
   every verification returns the same result. Replace the model and the
   identity does not change.
4. **It cannot exceed its bounds.** What reaches it and what it reaches are each
   confined to one declared path.

Ten invariants — requirements no configuration may relax — carry those four
claims, and **each one has a test**. The tests form the **conformance suite**:
executed where the suite can drive an implementation, attested with evidence
and a reviewer's sign-off where it cannot. Conformance is a test result, not a
reading of the document.

---

## The ten invariants

An entity is bound to an **Operator**: the human who holds final authority over
it. Everything the entity is lives in its **store**, a set of files in three
classes — its **structure** (instructions, skills, configuration, and its
bindings to Operators), its **memory** (what it records and learns), and its
**integrity** records, which prove the structure untampered and decide whether
the entity may run. Each class has one writer: a single path allowed to change
it. The **Genesis Anchor** is written once, at first activation, and every
authorized change to the structure adds an entry to a **chain** that leads back
to it. **Cognition** is the part that reasons, and the model is its engine, a
**stateless** one: context in, one answer out, nothing kept between calls. The
entity acts only through **skills** — packaged operations its Operator admits —
and only inside its **workspace**, the part of the host its Operator declares.
Cognition is kept apart from the model, from memory, from the integrity records
and from the host; passing between any of them is a **boundary crossing**.

| | Invariant | Domain |
|---|---|---|
| **OC-001** | An entity exists only bound to an Operator, who holds final authority over everything it is and does | bond |
| **OC-002** | The entity is not alive, and is never built or directed to act as if it were | nature |
| **OC-003** | Everything the entity is resides in its store, travels with it, and has one writer per class | state |
| **OC-004** | The entity's identity is proven by an unbroken chain back to its Genesis Anchor | identity |
| **OC-005** | Integrity guards the entity, and nothing in the entity can disarm it | integrity |
| **OC-006** | The model is cognition's stateless engine, and it only answers | cognition |
| **OC-007** | What the entity has learned comes only from its memory | knowledge |
| **OC-008** | The entity acts only inside an isolated workspace its Operator declares, through skills its Operator admits | action |
| **OC-009** | The entity is auditable by design: every boundary crossing leaves a record | audit |
| **OC-010** | The entity starts verified, or does not start | start |

Read in sequence, the ten titles are OBEC in one paragraph:

> An entity exists only bound to an Operator, who holds final authority over
> everything it is and does. The entity is not alive, and is never built or
> directed to act as if it were. Everything the entity is resides in its store,
> travels with it, and has one writer per class. The entity's identity is proven
> by an unbroken chain back to its Genesis Anchor. Integrity guards the entity,
> and nothing in the entity can disarm it. The model is cognition's stateless
> engine, and it only answers. What the entity has learned comes only from its
> memory. The entity acts only inside an isolated workspace its Operator
> declares, through skills its Operator admits. The entity is auditable by
> design: every boundary crossing leaves a record. The entity starts verified,
> or does not start.

No configuration, operational condition, or extension — a document that adds
operations or stricter rules on top of the specification — may weaken any of
them.

**[Read the ten in full →](spec/obec-kernel.md)** (17 KB, the whole normative
requirement)

---

## Documents

Only what is expensive to change is **version-bound**: changing a sentence in it
is a revision of the specification, under a new version.

| Document | What it is | Version-bound |
|---|---|---|
| [**obec-primer.md**](spec/obec-primer.md) | Plain language, no requirements: what OBEC is for, whether you need it, and how the pieces fit. Start here if it is new to you. | no |
| [**obec-kernel.md**](spec/obec-kernel.md) | The ten invariants, MUST sentences only. What is expensive to change, short enough to read at once. | **yes** |
| [**obec-core.md**](spec/obec-core.md) | The same ten with their conformance tests, the reference architecture, the extension and revision rules, security considerations, and the glossary. | no |
| [**obec-profile.md**](spec/obec-profile.md) | The Implementation Profile: 24 rules of operational machinery, stated as SHOULD. Not required for conformance. | no |
| [design/0001](design/0001-obec-restructure.md) | Why the set is shaped this way. Not needed to implement. | no |
| [design/0002](design/0002-invariant-titles.md) | Why each invariant's title states its guarantee, and why OC-001 and OC-002 exchanged places. Not needed to implement. | no |
| [design/0003](design/0003-conversation-scoped-memory.md) | Why episodic memory belongs to the conversation that writes it, and how the working set reaches the next one. Not needed to implement. | no |
| [design/OPEN-QUESTIONS](design/OPEN-QUESTIONS.md) | What the author is least sure about, and what would settle each. | no |

Four audiences. Someone new reads the Primer. An implementer reads the Core. A
reviewer reads the Kernel. Someone asking *why* reads the ADRs.

---

## Autonomy is a dial, not a setting

By default, every change the entity proposes waits for an Operator to approve
that one proposal. The distinctive mechanism is the **standing grant**: an
Operator's approval given in advance, bounded simultaneously on three axes — an
**expiry**, a **commit budget** of how many changes it covers, and a **declared
scope** of the kinds of change it covers. While it is open, a change inside its
scope is applied without waiting for its own approval, and logged under the
grant's identity. On expiry or budget exhaustion it reverts to approval proposal
by proposal automatically, with no action required from anything.

Never open one and every change requires explicit human approval — zero standing
autonomy, no additional mechanism needed. Open a narrow one and the entity
evolves within a budget you set. Same rule, whole range.

---

## Status: this is a proposal

**Published for early reading.** The repository is public before it is ready,
so that the people it has been shared with can read it. It will be announced
when the reference implementation passes every executed step of the
conformance suite.

**Nothing here has been ratified by anyone.** The documents use MUST because
that is how you state a requirement without ambiguity — not because anyone has
agreed to be bound by it.

The architecture is not untried: it has been implemented twice, in Python and
in TypeScript, and entities have run under it. **What is unvalidated is
longevity and cost** — how an entity behaves after months of accumulated
memory, what the guarantees cost per session and per year, and whether the
mechanisms that look right on one week of operation still look right on one
year of it. No implementation has yet passed the conformance suite, which is
new; the [reference implementation](implementations/fsp-ref/) is partway
through it.

**0.11.0 — pre-release.** It is a release, not a draft: the set is the product
of a full restructure, and [ADR 0001](design/0001-obec-restructure.md) records
how each invariant was derived and what was deliberately left out. 1.0 would follow a first
implementation passing the ten tests, at which point rule identifiers freeze.

Releases are tagged (`v0.11.0`). `main` may be ahead of the latest one, with
the difference listed under *Unreleased* in the [CHANGELOG](CHANGELOG.md); a
conformance claim cites a tagged version of the specification and the suite.

**No entity should be created under OBEC before 1.0.** OC-004(a) records the
major version in the Genesis Anchor, and a pre-release version can still change
beneath an entity that already recorded it. Run the suite against disposable
stores until then.

### What would help most

[**design/OPEN-QUESTIONS.md**](design/OPEN-QUESTIONS.md) is the list of what
the author is least sure about — whether ten is the right number, whether the
test of OC-002(d) can be more than a floor, whether portability and
hardware-backed keys can coexist, and eight more. Each entry says what would settle it.

**Arguing that one of the ten is wrong is the most useful thing anyone can do
with this repository right now.** It does not need a replacement, a migration
plan or a pull request — being right that something is wrong is a complete
contribution. [CONTRIBUTING §7](CONTRIBUTING.md#7-challenging-an-invariant)
says what makes such an argument land.

Implementations, conformance runs, and reports that an invariant was expensive
for no benefit are all equally welcome.

---

## Repository

```
spec/            the three specification documents
design/          architecture decision records
conformance/     the ten tests, executable, and the claim registry   (in progress)
implementations/ reference implementations                            (in progress)
ietf/            Internet-Drafts generated from spec/                 (in progress)
```

| | |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | how to propose a change, and the commit convention — commit types are the four revision kinds, so the log is what the version rule is enforced against |
| [GOVERNANCE.md](GOVERNANCE.md) | roles, lifecycle, versioning policy, extension policy |
| [COMPLIANCE.md](COMPLIANCE.md) | what conformance means, how to claim it, how to verify someone else's claim |
| [CHANGELOG.md](CHANGELOG.md) | releases, classified by revision kind |
| [BACKLOG.md](BACKLOG.md) | what is left to do, by priority |
| [AGENTS.md](AGENTS.md) | for coding agents: the rules that are easy to break, and how to verify a change |

---

## What OBEC does not do

It does not specify cognitive algorithms, storage formats, wire protocols, model
choice, or how the model is called. It does not require a particular division
into components — the architecture the Core describes is RECOMMENDED, so that an
existing runtime can claim conformance without being rewritten.

It also does not solve prompt injection. The checks verify which operation is
requested, that it is authorized, and that the skill matches the declaration it
was admitted with; they do not judge intent, and a valid skill invoked with
adversarial arguments passes every one of them. What OBEC bounds is the blast
radius and the evidence trail. See
[§6 of the Core](spec/obec-core.md#6-security-considerations-non-normative) for
the full list of what is deliberately left open.

---

## License

Documents (`spec/`, `design/`, `ietf/`, and the documents at the root): [CC BY 4.0](LICENSES/CC-BY-4.0.txt)
Code (`conformance/`, `implementations/`): [Apache 2.0](LICENSES/Apache-2.0.txt)

See [LICENSE](LICENSE).

Copyright © 2026 Jonas Orrico.
