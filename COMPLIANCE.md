# OBEC Conformance Guide

What it means to conform to OBEC, and how to claim and verify it.

Conformance is defined by [obec-core.md §5](spec/obec-core.md): an implementation
is **OBEC-Core conformant if and only if it passes the ten conformance tests of
§2**.

> **Conformance is a test result, not a reading of the document.** An
> implementation does not conform by satisfying a reviewer that it has understood
> the text. It conforms by running the suite and publishing the output. Any claim
> unaccompanied by suite output is a claim about intent, not about conformance.

---

## 1. Forms of conformance

### 1.1 OBEC-Core

All ten invariants: HC-001 through HC-010.

The implementation need not use any particular component decomposition. The
four-domain architecture in [Core §3](spec/obec-core.md) is RECOMMENDED, not
required — **no invariant names a component** — so an existing runtime can claim
conformance without being rewritten.

Following the [Implementation Profile](spec/obec-profile.md) is not required.

### 1.2 OBEC-Attest

The subset covering identity and authority: **HC-001 – HC-005, HC-009, HC-010**.
It omits the three operational containment invariants — HC-006 (stateless
inference), HC-007 (Memory Store sole source) and HC-008 (host actuation).

This form exists for a runtime adding auditable identity and authorization
without changing how it reasons, remembers or acts. It covers the Operator, the
store, the chain, integrity isolation, boundary discipline, and verified start.

An implementation claiming OBEC-Attest **MUST NOT** claim OBEC-Core.

### 1.3 Extensions

An implementation with extensions active conforms as
**OBEC-Core + \<extension names\>** and MUST additionally satisfy each active
extension's own conformance requirements.

---

## 2. Two kinds of test

Not every invariant can be proven by running a system. HC-006 and HC-009 are
properties of *how an implementation is built*, not behaviors it exhibits at
runtime — no sequence of inputs demonstrates that nothing acts on a completion
before it returns.

| Kind | How it is established |
|---|---|
| **Executed** | the suite drives the implementation's conformance adapter and asserts the outcome |
| **Attested** | the implementation declares the property with evidence — a pointer to the code that establishes it — and a reviewer signs off |

**A claim states which tests were executed and which were attested.** Conflating
the two would make the suite look stronger than it is, and the distinction is the
first thing a serious evaluator will look for.

---

## 3. Claiming conformance

A claim MUST provide:

1. **Declaration** — the OBEC-Core version, the conformance suite version, the
   form claimed (§1), and the active extensions, as in
   `OBEC-Core 1.0, suite 1.3, Core form, no extensions`.
2. **Suite output** — the result of every test, marked executed or attested, with
   evidence for each attested one.
3. **Structural surface** — the structural content of HC-003(c) the
   implementation maintains: persona, skills, configuration including every value
   the Profile leaves to configuration, and the Operator binding set.
4. **Conformance adapter** — the adapter that makes the implementation drivable
   by the suite, so the claim can be reproduced by someone else.
5. **Audit trail** — the integrity log of the run: the chain, the start gate
   results, and the authorization covering every commit.

Claims are recorded in [`conformance/CLAIMS.md`](conformance/CLAIMS.md), which also defines how a claim is reviewed, what a specification revision does to it, and how one is disputed or withdrawn.

**Partial conformance is not conformance.** Passing nine of ten tests is not a
claim; it is a report.

---

## 4. Verification

Conformance can be verified independently, at three depths:

**Static.** Recompute the integrity baseline against current structural content,
and walk the chain back to the Genesis Anchor. Both checks are mechanical and
require nothing running (HC-004).

**Portability.** Copy the Entity Store to a host sharing no state with the
original and run the start-time verification on both. The outcomes and the
computed digests must be identical (HC-003(b)). This is the cheapest check in the
specification and the one to run first.

**Adversarial.** Drive the negative cases: commit without authorization, commit
under an expired grant, actuate outside the workspace, invoke an unindexed skill,
start with a passive signal present. Every one must be refused and logged with
the check that produced the refusal.

---

## 5. The reference implementation is non-normative

- Matching the reference implementation's behavior does **not** establish
  conformance.
- Diverging from it does **not** imply non-conformance, provided the ten tests
  pass.
- Conformance is determined solely by the normative text and the suite.

---

## 6. Use of the OBEC name

A claim that does not satisfy §3 is not a conformance claim and MUST NOT be
presented as one.

For partial or experimental systems, accurate phrasing is available:

- *"Built on the OBEC model"*
- *"OBEC-compatible, experimental — not conformance-tested"*
- *"Targets OBEC-Attest; suite not yet run"*

Misrepresenting one of these as conformance is the failure mode this document
exists to prevent: the specification's entire value is that a claim about an
entity can be checked rather than believed.

---

## 7. Pre-release caveat

While OBEC-Core is Pre-release, a conformance claim is provisional: the normative
kernel can still change, and a weakening change would sever the chain of any
entity created under the current version.

**No entity should be created under a pre-release version** — HC-004(a) records
the major version in the Genesis Anchor. Run the suite against disposable stores
until 1.0.
