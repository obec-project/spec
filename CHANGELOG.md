# Changelog

Revisions are classified by the taxonomy in
[obec-core.md §4.2](spec/obec-core.md#42-revision-and-continuity). Only the
**normative kernel** is version-bound; the Core's apparatus, the Profile and the
design records are revised without a version boundary.

| Kind | Effect on an entity's chain |
|---|---|
| **Editorial** — wording, formatting, cross-references | preserved (patch) |
| **Clarifying** — an ambiguity resolved in the direction already implied | preserved (minor) |
| **Hardening / addition** — a permission narrows, a requirement is added | preserved by migration, OC-004(c) (major) |
| **Weakening / removal** — a guarantee no longer holds | **broken** (major) |

The conformance suite carries its own version line; a claim names both, as in
`OBEC-Core 1.0, suite 1.3`.

---

## Unreleased

**Conformance suite**

- Step 3.5 now tries **every** operation against every content class it does
  not own, not only the class owners against each other. An operation owning no
  class — host actuation above all — was only tested against the store by 8.4
  and 8.10, under OC-008, which OBEC-Attest omits: an Attest claim could pass
  with a shell tool able to rewrite the entity's structural content. The stub
  gains a break, `oc003c`, that proves the step catches it.
- TESTS.md §0.2 says why each of the twelve attested steps is attested —
  completeness, absence from the configuration surface, construction, or
  meaning — instead of presenting them as one kind of concession.

**Documents**

- COMPLIANCE §1.2 and Core §5 state what OBEC-Attest establishes and what it
  does not: identity and authority, not containment.
- *Entity* is defined as a kind of agent — in the README, the Primer, and the
  Core's glossary, which lacked the term — and is used throughout. *Agent*
  remains only in that definition, where the Primer speaks of agents before
  OBEC, and for third-party products that behave as agents without being
  entities.
- The project's status is stated once, in the README, instead of in five places.

---

## 0.9.1 — 2026-09-18

Editorial release. **Still pre-release:** no requirement changes, and no entity
should be created under this version, for the reason 0.9.0 gives.

**The specification**

- The invariants are renamed `HC-001` – `HC-010` → **`OC-001` – `OC-010`**
  (OBEC Core), matching the Profile's `OP-nnn`. Numbers, clause letters and
  text are unchanged; `HC-004(c)` is now `OC-004(c)`. Identifiers freeze at
  1.0; this is the change that had to happen before then. The 0.9.0 entry
  below keeps the names that release used.
- The kernel restores four passages it had shortened from the Core's §2, in
  OC-002(b), OC-002(c), OC-003(c) and OC-004(c). §2 governed throughout.

**Conformance suite 0.1.1**

- Targets OBEC-Core 0.9.1. The stub's break modes follow the rename
  (`hc002b` → `oc002b`).
- The runner's exit code says why a run is not conformant: `1` a step failed,
  `3` nothing failed but a step is unestablished, `4` the adapter errored.
  Only `0` is conformant, and no flag turns `3` into `0`.
- The suite's own tests: every stub break must fail exactly the tests it is
  documented to fail, and the kernel must be a verbatim extract of §2. Both run
  in CI on Python 3.8 – 3.14. `OBEC_STUB_HOSTNAME` lets the stub stand in for a
  second host, so step 3.2 is shown to catch host coupling.

**Repository**

- Every file now has a license: documents CC BY 4.0, code Apache 2.0, with the
  full texts in `LICENSES/`. `ietf/` carries the specification's license, plus
  the IETF Trust's provisions for submitted drafts.
- `NOTICE`, SPDX headers on the code, and `SECURITY.md` with a private
  reporting channel.

---

## 0.9.0 — 2026-09-18

Initial release. **Pre-release:** the normative content is complete and the
conformance suite is not. **No entity should be created under this version** —
HC-004(a) records the major version in the Genesis Anchor, and a pre-release
version can still change beneath an entity that already recorded it.

**The specification**

- Ten invariants, `HC-001` through `HC-010`, each with a mechanical conformance
  test. The set is closed: no extension, configuration, or operational condition
  may weaken one.
- Three layers by audience — the normative kernel (MUST sentences only, the sole
  version-bound layer), the Core (the same ten with tests, reference
  architecture, revision rules, security considerations and glossary), and the
  Implementation Profile (24 `OP-nnn` rules of operational machinery, as SHOULD).
- The four-domain reference architecture is RECOMMENDED, not required. No
  invariant names a component, so an existing runtime can claim conformance
  without being rewritten.
- Stable identifiers with addressable clauses (`HC-008(c)`, `OP-014(b)`).
  **Identifiers freeze at 1.0.**

**Conformance**

- Conformance is a test result, not a reading of the document: an implementation
  conforms if and only if it passes the ten tests.
- Two forms — **OBEC-Core** (all ten) and **OBEC-Attest** (identity and authority
  only: HC-001 – HC-005, HC-009, HC-010).
- Two kinds of test — **executed** against an implementation, and **attested**
  with evidence for the properties no sequence of inputs can demonstrate.
- The suite carries its own version line; a claim names both.

**Revision policy**

- Revisions are classified as editorial, clarifying, hardening or weakening, and
  only weakening severs an entity's chain. Hardening preserves continuity by
  migration through a version-transition entry (HC-004(c)).
- Only the normative kernel is version-bound. The Core's apparatus, the Profile
  and the design records are revised without a version boundary.

Why the set is shaped this way, including the full derivation of the ten and the
naming decision, is recorded in [ADR 0001](design/0001-obec-restructure.md). It
is not needed to implement the specification.
