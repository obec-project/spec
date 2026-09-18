# OBEC — Operator-Bounded Entity Continuity

**A specification for AI entities whose identity, authority and boundaries are
verifiable from their own portable state.**

An entity is an agent whose claims about itself can be checked rather than
believed. It is built on a stateless language model. It reasons, remembers, and
acts on a host — and it can prove four things about itself:

1. **It is the entity that was activated.** Its current structural state traces
   back to first activation through an unbroken chain of authorized changes.
2. **Every change to what it is was authorized by a human.** The entity can
   propose changing itself. It can never approve one.
3. **That proof travels with it.** Move the store to another host and every
   verification returns the same result. Replace the model and the identity does
   not change.
4. **It cannot exceed its bounds.** What reaches it and what it reaches are each
   confined to one declared path.

Ten invariants carry those four claims, and **each one has a mechanical test**.
Conformance is a test result, not a reading of the document.

---

## The ten invariants

| | Invariant | |
|---|---|---|
| **OC-001** | Bounded existence | no self-perpetuation, no obstruction of the Operator, terminal decommission |
| **OC-002** | Operator primacy | the Operator exists, authorizes, and is reachable |
| **OC-003** | The Entity Store is complete, portable, and disciplined | all state inside, relocation-invariant, one writer per content class |
| **OC-004** | Unbroken chain to the Genesis Anchor | atomic commits, append-only chain, version frame |
| **OC-005** | Integrity is beyond cognition's reach | the verified cannot reach the verifier |
| **OC-006** | Stateless inference only | the model is infrastructure and holds nothing |
| **OC-007** | The Memory Store is the sole source of knowledge | no side channel into cognition |
| **OC-008** | Host actuation is bounded | one execution path, inside a declared workspace |
| **OC-009** | Boundaries are crossed only by signal | every required boundary is observable |
| **OC-010** | Verified start, or no start | the entity never begins operating unverified |

No extension, configuration, or operational condition may weaken any of them.

**[Read the ten in full →](spec/obec-kernel.md)** (15 KB, the whole normative
requirement)

---

## Documents

| Document | What it is | Version-bound |
|---|---|---|
| [**obec-primer.md**](spec/obec-primer.md) | Plain language, no requirements: what OBEC is for, whether you need it, and how the pieces fit. Start here if it is new to you. | no |
| [**obec-kernel.md**](spec/obec-kernel.md) | The ten invariants, MUST sentences only. What is expensive to change, short enough to read at once. | **yes** |
| [**obec-core.md**](spec/obec-core.md) | The same ten with their conformance tests, the reference architecture, the extension and revision rules, security considerations, and the glossary. | no |
| [**obec-profile.md**](spec/obec-profile.md) | The Implementation Profile: 24 rules of operational machinery, stated as SHOULD. Not required for conformance. | no |
| [design/0001](design/0001-obec-restructure.md) | Why the set is shaped this way. Not needed to implement. | no |
| [design/OPEN-QUESTIONS](design/OPEN-QUESTIONS.md) | What the author is least sure about, and what would settle each. | no |

Four audiences. Someone new reads the Primer. An implementer reads the Core. A
reviewer reads the Kernel. Someone asking *why* reads the ADR.

---

## Autonomy is a dial, not a profile

The distinctive mechanism is the **standing grant**: an Operator authorization
bounded simultaneously on three axes — **expiry**, **commit budget**, and
**declared scope**. While it is open, in-scope changes commit with no
per-proposal step, logged under the grant's identity. On expiry or budget
exhaustion it reverts to per-proposal sign-off automatically, with no action
required from anything.

Never open one and every change requires explicit human approval — zero standing
autonomy, no additional mechanism needed. Open a narrow one and the entity
evolves within a budget you set. Same rule, whole range.

---

## Status: this is a proposal

**Nothing here has been ratified by anyone.** The documents use MUST because
that is how you state a requirement without ambiguity — not because anyone has
agreed to be bound by it.

The architecture is not untried: it has been implemented twice, in Python and
in TypeScript, and entities have run under it. **What is unvalidated is
longevity and cost** — how an entity behaves after months of accumulated
memory, what the guarantees cost per session and per year, and whether the
mechanisms that look right on one week of operation still look right on one
year of it. No implementation has yet run the conformance suite, which is new.

**0.9.1 — pre-release.** It is a first release rather than a first draft: the
set is the product of a full restructure, and
[ADR 0001](design/0001-obec-restructure.md) records how each invariant was
derived and what was deliberately left out. 1.0 would follow a first
implementation passing the ten tests, at which point rule identifiers freeze.

**No entity should be created under OBEC before 1.0.** OC-004(a) records the
major version in the Genesis Anchor, and a pre-release version can still change
beneath an entity that already recorded it. Run the suite against disposable
stores until then.

### What would help most

[**design/OPEN-QUESTIONS.md**](design/OPEN-QUESTIONS.md) is the list of what
the author is least sure about — whether ten is the right number, whether
OC-001(d) is an invariant or a policy, whether portability and hardware-backed
keys can coexist, and seven more. Each entry says what would settle it.

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

---

## What OBEC does not do

It does not specify cognitive algorithms, storage formats, wire protocols, model
choice, or how the inference channel is realized. It does not require a
particular component decomposition — the four-domain architecture in the Core is
RECOMMENDED, so that an existing runtime can claim conformance without being
rewritten.

It also does not solve prompt injection. The checks verify an operation's
identity, authorization and manifest; they do not judge intent, and a valid skill
invoked with adversarial arguments passes every one of them. What OBEC bounds is
the blast radius and the evidence trail. See
[§6 of the Core](spec/obec-core.md#6-security-considerations-non-normative) for
the full list of what is deliberately left open.

---

## License

Documents (`spec/`, `design/`, `ietf/`, and the documents at the root): [CC BY 4.0](LICENSES/CC-BY-4.0.txt)
Code (`conformance/`, `implementations/`): [Apache 2.0](LICENSES/Apache-2.0.txt)

See [LICENSE](LICENSE).

Copyright © 2026 Jonas Orrico.
