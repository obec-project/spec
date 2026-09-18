# OBEC Governance

**Version:** 1.0 · **Status:** Active

Governance for the OBEC specification: decision-making, release management, and
conformance policy.

> **OBEC is a proposal** — see its [status](README.md#status-this-is-a-proposal).
> Governance below describes how the project is run today — by one author, in
> the open — not a settled institution. Section 10 is the intended exit from
> that.

---

## 1. Principles

- **Vendor neutrality.** No implementation defines the standard.
- **Specification first.** The normative text has authority over any
  implementation.
- **Minimalism.** Ten invariants. Growth is resisted by default.
- **Continuity is the product.** Changes are classified by what they do to an
  entity's chain, and only one class is allowed to break it.
- **Open participation** under the processes in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 2. Roles

**Specification Owner** — maintains architectural coherence, approves releases
and status transitions, resolves disputes. The repository founder serves as
Specification Owner. This is a description of who is currently doing the work,
not a claim of standing: while OBEC is a proposal, the role's real authority is
over the document, and anyone is free to disagree with it in public or to fork
it.

**Maintainers** — review pull requests, propose revisions, maintain
documentation. Maintainers do not unilaterally change an invariant.

**Contributors** — submit issues, changes, RFCs, and conformance claims.

---

## 3. Specification lifecycle

Each document declares a status:

| Status | Meaning |
|---|---|
| **Working Draft** | under active development; not stable |
| **Pre-release** | normative content complete, conformance suite incomplete. **No entity should be created under a pre-release version** (§5.2) |
| **Proposed Standard** | feature complete, internally consistent, and proven implementable by at least one implementation passing the full conformance suite |
| **Stable** | maturity demonstrated by adoption beyond the reference implementation |
| **Deprecated** | superseded, or scheduled for removal in a future major version |

Status changes require explicit approval by the Specification Owner.

OBEC-Core is currently **Pre-release at 0.9.1**, and no status above that has
been claimed. Promotion to Proposed Standard requires the version to advance to
1.0.0 and the first implementation to pass the ten conformance tests. Rule
identifiers freeze at 1.0.

The most useful thing that can happen before then is for someone to show that
one of the ten invariants is wrong. [design/OPEN-QUESTIONS.md](design/OPEN-QUESTIONS.md)
lists where the author expects that to be found, and
[CONTRIBUTING §7](CONTRIBUTING.md#7-challenging-an-invariant) says how to argue
it.

---

## 4. Versioning

Semantic versioning: `MAJOR.MINOR.PATCH`. What determines the increment is the
revision taxonomy of [Core §4.2](spec/obec-core.md#42-revision-and-continuity),
not the size of the diff.

| Revision kind | Increment | Entity continuity |
|---|---|---|
| **editorial** | PATCH | preserved |
| **clarify** | MINOR | preserved |
| **harden** / addition | **MAJOR** | preserved by migration (OC-004(c)) |
| **weaken** / removal | **MAJOR** | **broken** |

Two consequences follow, and they are what distinguish this policy from ordinary
SemVer:

**A major version is not automatically a break.** Hardening the specification
advances the major version because the invariant set changed, but an existing
entity migrates across it: the migration is an Operator-authorized
version-transition entry in the chain, verified against the target version before
it commits. Every entry remains interpretable under the version in force at its
position.

**Only weakening severs continuity.** If an entity could migrate to a version
that weakens an invariant, then "no extension, configuration, or operational
condition may weaken this" would have an obvious hole. A weakening release is
therefore not migratable, and every entity under the prior version ends its line
there.

### 4.1 What is version-bound

Only the **normative kernel** — the MUST and MUST NOT sentences of Core §2, and
the clause structure addressing them. The Core's tests and notes, the
Implementation Profile, the design records, and this document are apparatus: they
are revised without a version boundary.

### 4.2 The conformance suite versions separately

A better test does not change a guarantee; it checks it more closely. The suite
carries its own version line, and a claim names both, as in
`OBEC-Core 1.0, suite 1.3`.

---

## 5. Change management

### 5.1 Normative changes

A normative pull request MUST identify its revision kind, include rationale,
state continuity impact, update the affected conformance test, and update the
kernel and the Core identically in the same change.

A **weaken** change additionally requires explicit approval by the Specification
Owner, a migration note, and a statement of what guarantee is lost.

Non-normative edits — grammar, formatting, Profile rules, tooling — merge without
a formal review cycle.

### 5.2 Entity safety during pre-release

OC-004(a) records the major version in the Genesis Anchor. A pre-release version
can still change beneath an entity that already recorded it, and the remedy would
be a weakening release that severs the chain. **No entity should be created under
a pre-release version.**

---

## 6. Conformance policy

A system may claim:

- **OBEC-Core conformant** — it passes the ten conformance tests of
  [Core §2](spec/obec-core.md).
- **OBEC-Attest** — it passes the subset covering identity and authority
  (OC-001 – OC-005, OC-009, OC-010), without the operational containment
  invariants. An implementation claiming OBEC-Attest MUST NOT claim OBEC-Core.
- **OBEC-Core + \<extension names\>** — it additionally satisfies each active
  extension's own conformance requirements.

**Conformance is a test result, not a reading of the document.** A claim must be
accompanied by suite output stating which tests were executed and which were
attested (see [COMPLIANCE.md](COMPLIANCE.md)).

Reference implementations are non-normative. Matching one does not establish
conformance; diverging from one does not establish non-conformance.

Following the Implementation Profile is not required for conformance.

---

## 7. Extension policy

Extensions are specified in their own documents, each with its own conformance
requirements on top of the ten. An extension MUST:

- declare the OBEC-Core version it targets;
- add capability or harden a rule, and never weaken one;
- class every artifact it adds within OC-003(c) and follow its write rules;
- declare whether it is experimental or stable.

The invariant set is closed. No extension may add to it, weaken it, or
reinterpret it, and no combination of active extensions may violate one.

---

## 8. RFCs and design records

Major architectural changes begin as an RFC in `ietf/` when the audience is
external, or as an ADR in `design/` when the decision is the project's own. Both
must include motivation, proposed specification text, continuity analysis, and
security considerations. Acceptance requires explicit approval by the
Specification Owner.

---

## 9. Intellectual property

OBEC is released under the licenses in [LICENSE](LICENSE). Contributors agree
their contributions may be redistributed under them. The project does not accept
proprietary or patent-encumbered normative requirements without explicit
disclosure.

---

## 10. Future governance

If OBEC reaches multi-stakeholder adoption, governance may transition to a
foundation or steering group. Such a transition requires a public governance
proposal, a defined voting structure, and a transparent leadership selection
process. Until then governance remains centralized under the Specification Owner.

---

## 11. Final authority

The normative specification text is the final authority. Implementations,
examples, and external documentation do not override it.

Within the specification, [Core §2](spec/obec-core.md) governs: the kernel is a
verbatim extract, and where the two differ the kernel is in error.
