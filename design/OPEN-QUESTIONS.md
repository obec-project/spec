---
title: "Open questions"
status: "Living — the author's own doubts, kept in public"
date: 2026-09-18
---

# Open questions

OBEC is a **proposal**. Nothing in it has been ratified by anyone, and no
implementation has yet run the conformance suite. The normative documents use
MUST because that is how you state a requirement without ambiguity — not
because anyone has agreed to be bound by it.

The architecture is not untried. It has been implemented twice — in Python and
in TypeScript — and entities have run under both. So the questions below are
not *does this work*; they are **at what cost, for how long, and which parts
earn their keep**.

This page is the list of things the author is least sure about. It is here
because a proposal that only publishes its confident parts is asking for
applause rather than review, and because the fastest way to improve the
specification is for someone to be right about one of these.

Each entry says what is open, why it is open, and **what would settle it**.
Disagreement on any of them is a welcome issue; see
[CONTRIBUTING §7](../CONTRIBUTING.md#7-challenging-an-invariant).

---

## 1. What does a long-lived entity cost, and does its record stay legible?

This is the question the whole proposal turns on, and the one with the least
evidence behind it.

First, what it is **not**. An entity that has run for a year *should* behave
differently from the one its Genesis Anchor describes — that is accumulation
working, not decay. Identity here is not behavioral sameness: HC-004 computes
it from the store and never infers it from behavior. What the chain establishes
over that year is that **every structural change in it was authorized, and the
sequence from first activation to now is unbroken**. An entity is not supposed
to stay the same; it is supposed to be able to account for how it changed.

That leaves three real questions, and the architecture has run without anyone
answering them.

**Cost.** The per-session price of consolidation and drift detection, the
growth of the chain and the log over months, and whether start cost really
stays flat as an entity ages. The Profile requires that at OP-019, and
requiring is not measuring. An architecture that is correct and unaffordable is
not useful, and the specification currently has opinions about correctness and
none about price.

**Legibility.** The value proposition is that *"show me every structural change
this entity underwent and who authorized each"* has a short answer.
Mechanically that holds at any length — verification is a walk. But a chain of
several thousand authorized entries is **verifiable without being auditable**,
and a record no human can read is a weaker guarantee than the specification
implies. At what length does it stop being readable, and is the answer
tooling or a different record?

**Anchor staleness.** Semantic probes are assembled at first activation and
change only through an authorized commit. An entity that legitimately grows for
a year drifts away from anchors nobody thought to update. The drift gate then
either blocks learning that should happen, or gets relaxed until it gates
nothing. Which of the two occurs in practice is unknown, and the specification
offers no guidance on maintaining probes over a long life.

**What would settle it:** an entity operated continuously for months, with
numbers — start latency against chain length, consolidation time per session,
store growth per session — plus the chain itself, so that someone can try to
read it; and a record of how often drift fired and whether it was right.

---

## 2. Is ten the right number?

Ten came from applying two filters mechanically to 88 inherited requirements:
*can this be given a test?* and *could a configuration plausibly relax it?*
That is a defensible method, but it was applied by one person in one pass,
against an architecture whose earlier form had 88 rules — so the risk is not
that something is missing but that something survived out of habit.

**What would settle it:** an implementer reporting which invariants were
expensive for no benefit, and which guarantee they expected to find and did
not.

---

## 3. Does HC-001(d) belong in an invariant?

The clause forbidding structural content from directing the entity to present
itself as conscious is the only one in a philosophical register, and its test
is keyword matching, which is a blunt instrument that a determined author
routes around in one sentence.

Two positions, and the author holds the first only weakly:

- It belongs in HC-001 because self-representation as a subject is the same
  kind of boundary as self-perpetuation — the entity is not a locus of
  selfhood, and both clauses say so.
- It is a **policy**, not an invariant. Policies belong in the Profile, where
  a deployment can implement them as it sees fit, and putting one in the
  closed set dilutes what the set means.

**What would settle it:** a deployment where the clause did real work, or an
argument that its test can never be more than theater.

---

## 4. Is HC-009 an invariant or an observation?

"Boundaries are crossed only by signal" was promoted to the set late, and it
was immediately necessary to reformulate it so that it binds a monolithic
implementation — otherwise "there are no parts to isolate" would satisfy it
vacuously. The current form binds the four boundaries the specification
already requires.

But its test is two executed steps over a self-declared table plus one
attested step. That is thin for something in a closed set.

**What would settle it:** a construction that satisfies HC-005 through HC-008
and still violates HC-009 in a way the test catches. If no such construction
exists, HC-009 is a restatement, not an invariant.

---

## 5. Portability versus hardware-backed keys

HC-003(b) forbids any verification from depending on host-resident key
material. The planned Security extension wants hardened key management, and
the obvious hardening — a TPM, a secure enclave, a platform keystore — is
exactly what HC-003(b) forbids.

The specification currently resolves this by fiat: an extension "MUST do so in
a way that survives relocation, or it is not an extension of this document."
That is a clean rule and it may be an unsatisfiable one.

**What would settle it:** a key management construction that is both
hardware-backed and relocation-invariant. If there is none, then either
portability is not an invariant or the Security extension cannot do what it
was meant to do — and the author does not know which.

---

## 6. Are twelve attested steps too many?

Conformance is meant to be a test result rather than a reading. Twelve of the
seventy-six steps are attested — recorded with evidence and signed off by a
reviewer — and HC-006 is attested in full, because no sequence of inputs
demonstrates that nothing acts on a completion before it returns.

That is honest, but it means conformance rests partly on reviewer judgment,
which is the thing the project set out to replace.

**What would settle it:** an executable test for any currently attested step.
HC-006 is the one that matters most; a way to demonstrate the clean-completion
property from outside would materially strengthen the whole specification.

---

## 7. Is OBEC-Attest cut in the right place?

The partial form covers HC-001 – HC-005, HC-009 and HC-010, and omits the
three containment invariants. The reasoning is that identity and authority are
separable from how an entity reasons, remembers and acts.

Nobody has tried to adopt it, so the cut is a guess about where an existing
runtime would want to stop.

**What would settle it:** a runtime adopting it and reporting whether the line
fell in a useful place.

---

## 8. The version-transition mechanism is entirely unvalidated

HC-004(c) makes migration between major versions a chain event: an
Operator-authorized transition entry, verified against the target version
before it commits. It is the mechanism that makes revision survivable rather
than fatal, and it has never run, because there is no second version to
migrate to. Conformance steps 4.9 – 4.12 are unestablished for everyone.

**What would settle it:** the first version after 1.0, and an entity that
actually crosses it.

---

## 9. What are the scope categories of a standing grant?

HC-002(b) requires a standing grant to declare a **scope of change
categories**, and never says what the categories are. That is currently
implementation-defined by omission rather than by decision.

The omission may be right — categories that make sense for one deployment may
not for another. But it means two conformant implementations can have
incompatible notions of what "in scope" means, which weakens the one mechanism
this specification leans on hardest.

**What would settle it:** either a minimal taxonomy worth standardizing, or an
explicit statement that the taxonomy is the implementation's and an argument
for why that is safe.

---

## 10. Should the specification describe an architecture at all?

Section 3 of the Core describes a four-domain decomposition and marks it
RECOMMENDED. Demoting it from mandatory was the change that lets an existing
runtime conform without being rewritten, and that was clearly right.

Whether it should be in the document at all is less clear. It is the largest
non-normative section, it is what a reader most easily mistakes for a
requirement, and the predecessor's primer taught it as mandatory precisely
because it was there.

**What would settle it:** whether implementers use it. If everyone ignores it,
it is a liability; if everyone follows it, it should probably be a separate
document rather than a section that looks normative.

---

## 11. "Entity" or "agent"?

The normative text says *entity* because it is more precise: an OBEC entity is
something narrower than what the word "agent" covers in 2026. Every
introductory surface says *agent* because that is what people search for.

Carrying two words for one thing is a cost paid on every page.

**What would settle it:** evidence that the precision buys something, or that
the split confuses more readers than it serves.

---

## How to weigh in

Open an issue. Quoting the entry number is enough of a title. Disagreement
with evidence is worth more than agreement, and an argument that one of the
ten is wrong is the most valuable contribution this project can receive right
now — see [CONTRIBUTING §7](../CONTRIBUTING.md#7-challenging-an-invariant).
