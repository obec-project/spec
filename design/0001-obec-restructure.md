---
title: "ADR 0001 — The OBEC restructure"
status: "Accepted"
date: 2026-09-18
supersedes: "HACA-Core 0.3.0"
---

# ADR 0001 — The OBEC restructure

**Status:** Accepted · **Date:** 2026-09-18 · **Author:** Jonas Orrico

This record exists so that the shape of [OBEC-Core](../spec/obec-core.md) can be
re-derived years from now without re-deriving the argument. It is not normative
and no implementation needs to read it. The specification is self-contained; this
is why it is what it is.

---

## 1. Context

OBEC-Core replaces **HACA-Core 0.3.0**, a working draft that was never published:
private repository, one author, no external review, no deployment. It carried
**88 labeled requirements** across twelve groups, of which eight were marked Core
Invariants.

Reading the 88 against the 8 showed that the invariants *were* the specification
and most of the remaining eighty rules were one of four things: definitions,
corollaries of other rules, enforcement machinery, or engineering guidance that
had acquired a normative label. Three consequences followed from that, and they
are the substance of this record: the invariant set was re-cut and reordered, the
machinery was separated out, and the name changed.

Because HACA was never published, nothing was owed to backward compatibility.
The restructure was free at the moment it was made and would not have been six
months later.

---

## 2. Decision

HACA-Core 0.3.0 carries **88 labeled requirements** across twelve groups. Read
against the eight Core Invariants, the invariants *are* the specification and
most of the remaining eighty rules are one of four things: definitions,
corollaries of other rules, enforcement machinery, or engineering guidance that
acquired a normative label.

This proposal makes six structural changes.

**1. Ten rules, and every one is an invariant.** Each is a constraint on state or
on a procedure, and each carries a test an auditor can execute without reading
the implementation's source. Rules that could not be given such a test were
demoted to the Implementation Profile — that filter, applied mechanically, is
what produced the number ten.

The distinction 0.3.0 draws between invariants and ordinary requirements does not
survive the compression. The test for invariant status is *could a configuration
or an operational condition plausibly relax this?* — and every rule that survived
the first filter also passes the second. A rule that may be switched off by a
setting is not a guarantee; it is a default. There are no defaults here.

**2. The set is ordered by the architecture it constrains.** In 0.3.0 the
invariants are ordered by the document's section order (V1, I4, B2, B5, C10, X1,
X2, M2), which is accidental, and they are scattered through the text. Here the
set is contiguous and each block names one locus of authority:

| Invariants | Locus |
|---|---|
| OC-001, OC-002 | the **Operator** |
| OC-003, OC-004 | the **Entity Store** |
| OC-005 – OC-008 | the four **domains of operation** — integrity, reasoning, memory, host |
| OC-009 | the **coordination** between them |
| OC-010 | the **transition into operation** |

**3. Two rules join the set, and three change altitude.** Portability (OC-003(b))
and integrity isolation (OC-005) are added: portability fails silently the moment
an extension binds key material to host hardware — a likely move for the Security
extension, and one nothing in 0.3.0 prevents; and integrity content is not gated
by OC-002 (it implements OC-002; gating it by itself would be circular), so in
0.3.0 no invariant stands between cognition and the machinery that judges it.

Three of 0.3.0's rules were at the wrong altitude. **X2** (the skill gate)
describes a check *within* host actuation, not a boundary peer to it; it becomes
OC-008(c). **V6** (commit atomicity) is the mechanism that keeps the chain
unbroken across a crash; it becomes OC-004(b). **S3** (content classes and sole
writers) describes the store's internal shape; it becomes OC-003(c).

**4. The four-component decomposition becomes RECOMMENDED.** No invariant names a
component. They constrain *authority boundaries*, which any decomposition may
realize; stating the boundaries and leaving the structure free lets an existing
runtime claim conformance without being rewritten, and costs no guarantee. The
four-component architecture remains fully specified — as a reference architecture
(§3), which the reference platform realizes.

**5. Conformance becomes a criterion instead of an inventory, and identifiers
are stable.** HACA-Core §15 enumerates every label in the document, which tests
nothing; here conformance is the ten tests, executable. Rules are `OC-nnn`,
assigned once and never reused; a withdrawn rule is marked `withdrawn` and keeps
its number. The prefix names the document, as `OP-nnn` names the Profile. Drafts
through 0.9.0 used `HC-nnn`, carried over from HACA-Core; it was replaced before
publication, while identifiers could still change, because a prefix that only
the project's history explains is one every new reader has to ask about. Clauses
are addressable — `OC-008(c)` — so a conformance report names what failed rather
than which rule it belonged to.

**6. Revision stops being fatal.** Collapsing every rule into the invariant set
would, under 0.3.0 K2, make any change to any rule — wording included — a major
version that severs every existing entity's chain. That rule is the one place
0.3.0 abandons its own logic: everywhere else change is handled by making it
authorized, recorded and traceable, and only at the version boundary does it
simply decree that continuity breaks.

§4 replaces it with three mechanisms. **What is version-bound narrows** to the
normative kernel — the MUST sentences — while tests, notes and the explanatory
sections are revised freely, and the conformance suite carries its own version
line (§4.1). **Revisions are classified** as editorial, clarifying, hardening or
weakening, and only weakening breaks continuity (§4.2). **Migration becomes a
chain event**: a version-transition entry, authorized by the Operator, verified
against the target version before it commits, recorded like any other structural
change (OC-004(c)).

The net effect: correcting a sentence costs a patch; improving a test costs a
suite release; tightening a guarantee costs a major version that entities
*migrate* across; and only removing a guarantee ends an entity's line — which it
should, because a specification that can be weakened by migration cannot claim
its invariants are invariant.

---

---

## 3. Where each invariant came from

Each OBEC invariant, and the HACA-Core 0.3.0 rules whose requirement it carries.
These were `*Sources:*` lines in the specification until the specification was
made self-contained; they live here now.

| Invariant | Sources in HACA-Core 0.3.0 |
|---|---|
| **OC-001** Bounded existence | B5, L6, L11 |
| **OC-002** Operator primacy | B2, V1, V3, T1, C16, B1, B3, V2, N1, N3 |
| **OC-003** The Entity Store | S1, S2, S3, C2, C12, M3, S5, L7 |
| **OC-004** Unbroken chain | I4, I1, I2, I3, L1, V6 |
| **OC-005** Integrity beyond cognition | T2, T4, C9, S4 |
| **OC-006** Stateless inference only | C10 |
| **OC-007** Memory Store sole source | M2 |
| **OC-008** Host actuation bounded | X1, X3, X2, I14 |
| **OC-009** Signal boundaries | C3, C4 |
| **OC-010** Verified start | L2, L4 |

---

## 4. Disposition of all 88 rules

Every labeled requirement of the current specification appears exactly once.

| Disposition | Count | Meaning |
|---|---|---|
| **Retained** | 15 | Its requirement appears in §2 substantially unchanged |
| **Merged** | 29 | Absorbed into a §2 invariant, compressed or reworded |
| **Profile** | 29 | Moved to the Implementation Profile as SHOULD/RECOMMENDED |
| **Glossary** | 8 | Definitional; imposes no obligation |
| **Removed** | 5 | Derivable from a retained rule, or an observation |
| **Own document** | 2 | E3, E4 — the extension documents |

An invariant may have more than one retained source: OC-002 alone carries B2, V1
and N1. Where a rule is marked *Merged + Profile*, its guarantee was merged and
its mechanics moved; it is counted once, under Merged.

### Trust model

| Rule | Disposition | Target / reason |
|---|---|---|
| T1 | Merged | OC-002(b) — every authorization originates with an Operator |
| T2 | **Retained** | OC-005(c) |
| T3 | Removed | Observation, not testable |
| T4 | Merged | OC-005 |

### State

| Rule | Disposition | Target / reason |
|---|---|---|
| S1 | **Retained** | OC-003(a) |
| S2 | Merged | OC-003(b) |
| S3 | **Retained** | OC-003(c); integrity class also → OC-005(a) |
| S4 | Merged | OC-005 — the circularity exemption, restated as the rule's rationale |
| S5 | Merged | OC-003(d) |
| S6 | Removed | Definitional |

### Components

| Rule | Disposition | Target / reason |
|---|---|---|
| C1 | Profile | §3 — RECOMMENDED reference architecture |
| C2 | Merged | OC-003(c) |
| C3 | **Retained** | OC-009 |
| C4 | Merged | OC-009 — infrastructure holds no authority |
| C5 | Glossary | stimulus, intent |
| C6 | Glossary | cognitive cycle |
| C7 | Glossary | cycle chain |
| C8 | Profile | Operator preemption granularity |
| C9 | Merged | OC-005(b) |
| C10 | **Retained** | OC-006 |
| C11 | Glossary + §3 | |
| C12 | Merged | OC-003(c) — parameter reach |
| C13 | Glossary + §3 | |
| C14 | Profile | on-demand re-verification |
| C15 | Glossary + §3 | |
| C16 | Merged | OC-002(b) — no part may create an authorization |
| C17 | Profile | routing; no-silent-drop guarantee |

### Operator binding

| Rule | Disposition | Target / reason |
|---|---|---|
| B1 | Merged | OC-002(a) — binding set, exclusive Operator act |
| B2 | **Retained** | OC-002(a) |
| B3 | Merged + Profile | OC-002(a) — credential as enforcement; mechanics → Profile |
| B4 | Profile | operational rules: allow / deny / hold |
| B5 | **Retained** | OC-001 |

### Memory

| Rule | Disposition | Target / reason |
|---|---|---|
| M1 | Glossary | Session Store, Memory Store |
| M2 | **Retained** | OC-007 |
| M3 | Merged | OC-003(e) — session attributability |
| M4 | Profile | Closure Payload |
| M5 | Profile | semantic promotion gated by drift |
| M6 | Profile | Resumption Record |
| M7 | Profile | context-window thresholds; the restart carve-out → OC-001 note |

### Integrity

| Rule | Disposition | Target / reason |
|---|---|---|
| I1 | Merged | OC-004(a) — baseline |
| I2 | Merged | OC-004(a) — append-only log |
| I3 | Merged + Profile | OC-004(a) — chain; checkpoints → Profile |
| I4 | **Retained** | OC-004(a) |
| I5 | Profile | Vital Check cadence |
| I6 | Profile | Nominal / Degraded / Critical |
| I7 | Removed | Guidance on I6 |
| I8 | Profile | watchdog |
| I9 | Profile | drift classification |
| I10 | Profile | semantic drift, semantic digest |
| I11 | Profile | probe layers; isolation of probabilistic comparison stays MUST within the Profile |
| I12 | Profile | identity-drift detection (the guarantee is OC-004) |
| I13 | Removed | Restates OC-004 |
| I14 | Merged | OC-008(c) — Skill Index |
| I15 | Profile | mid-session pruning |

### Structural evolution

| Rule | Disposition | Target / reason |
|---|---|---|
| V1 | **Retained** | OC-002(b) |
| V2 | Merged + Profile | OC-002(b) — logging at origination; record format → Profile |
| V3 | Merged | OC-002(b) — the three bounds and automatic reversion |
| V4 | Profile | held-proposal handling |
| V5 | Profile | staged commit pipeline |
| V6 | **Retained** | OC-004(b) |

### Execution

| Rule | Disposition | Target / reason |
|---|---|---|
| X1 | **Retained** | OC-008(a) |
| X2 | **Retained** | OC-008(c) |
| X3 | Merged + Profile | OC-008(d) — logging; gate order → Profile |
| X4 | Profile | no state between executions |
| X5 | Profile | background execution |
| X6 | Profile | Action Ledger |
| X7 | Glossary | worker skill |

### Lifecycle

| Rule | Disposition | Target / reason |
|---|---|---|
| L1 | Merged + Profile | OC-004(a) — Genesis Anchor; first-activation atomicity → Profile |
| L2 | **Retained** | OC-010 |
| L3 | Profile | start load set; start cost independent of entity age |
| L4 | Merged | OC-010 — recovery before verification |
| L5 | Profile | recovery attempt threshold |
| L6 | Merged + Profile | OC-001(b) — direct intervention; close modes → Profile |
| L7 | Merged | OC-003(d) — concurrent-session conflict |
| L8 | Profile | revocation mid-cycle |
| L9 | Profile | Sleep staging |
| L10 | Profile | maintenance authority during Sleep |
| L11 | Merged | OC-001(c) — terminality |

### Operator Channel

| Rule | Disposition | Target / reason |
|---|---|---|
| N1 | **Retained** | OC-002(c) |
| N2 | Profile | active mode |
| N3 | Merged | OC-002(c) — passive signal |
| N4 | Profile | corroborated escalation of an unresponsive verifier |

### Extensions & invariant meta

| Rule | Disposition | Target / reason |
|---|---|---|
| E1 | Removed | Informational |
| E2 | Merged | §4 — extension contract |
| E3 | Own document | CMI (Cognitive Mesh Interface) |
| E4 | Own document | Security |
| K1 | Merged | §4 — closed set |
| K2 | Merged | §4 — version boundary |

---

---

## 5. The Implementation Profile

Forty-one of the 88 describe mechanism rather than guarantee. They were
consolidated into **twenty-four rules** in [obec-profile.md](../spec/obec-profile.md).

The first draft of the Profile kept them as forty-one one-to-one rules and read
as fragments. The dominant fault was different from the Core's: there the problem
was rules at the wrong altitude; here it was **one procedure cut into slices**.
Seven procedures had been split across two to four rules each — the session-close
memory flow across four, the Vital Check across two, crash recovery across two,
Sleep across two, session close across two, the probes across two, the proposal
across two. Consolidating them, moving three rules to the right section, folding
two definitions into the rules that used them, and merging checkpoints with log
compaction took 41 to 24 without dropping a sentence.

The full map follows. It lived in the Profile until the Profile was made
self-contained.

Forty-one requirements of HACA-Core 0.3.0 describe mechanism rather than
guarantee. Twenty-nine were dispositioned **Profile** in §4; six were
dispositioned **Merged + Profile** (†), their guarantee absorbed into an
invariant and their mechanics left to the Profile; six were dispositioned
elsewhere (‡) but carry operational detail that has nowhere else to live.

| 0.3.0 | Rule | 0.3.0 | Rule | 0.3.0 | Rule |
|---|---|---|---|---|---|
| C1 | OP-024 | I5 | OP-003 | V2 † | OP-011 |
| C6 ‡ | OP-001 | I6 | OP-003 | V4 | OP-011 |
| C7 ‡ | OP-001 | I8 | OP-014 | V5 | OP-012 |
| C8 | OP-002 | I9 | OP-004 | X3 † | OP-013 |
| C14 | OP-006 | I10 | OP-005 | X4 | OP-014 |
| C17 | OP-002 | I11 | OP-005 | X5 | OP-014 |
| B3 † | OP-020 | I12 | OP-004 | X6 | OP-015 |
| B4 | OP-016 | I15 | OP-006 | X7 ‡ | OP-014 |
| M4 | OP-009 | L1 † | OP-017 | N2 | OP-008 |
| M5 | OP-009 | L3 | OP-019 | N4 | OP-008 |
| M6 | OP-009 | L4 ‡ | OP-018 | | |
| M7 | OP-010 | L5 | OP-018 | | |
| I2 ‡ | OP-007 | L6 † | OP-021 | | |
| I3 † | OP-007 | L8 | OP-021 | | |
| | | L9 | OP-022 | | |
| | | L10 | OP-022 | | |
| | | L11 ‡ | OP-023 | | |

† *Merged + Profile* in §4: the guarantee is an invariant, the mechanism is in
the Profile.

‡ Dispositioned *Glossary* (C6, C7, X7) or *Merged* (I2, L4, L11) in §4;
their operational detail is in the Profile.

---

## 6. The name

**HACA** — Host-Agnostic Cognitive Architecture — was retired for two independent
reasons.

**The expansion became false.** Of its three terms, only *Host-Agnostic* survived
the restructure, and it survived by being promoted to an invariant (OC-003(b)).
*Cognitive* was never true of the document: cognitive algorithms are
implementation-defined and the specification constrains nothing about them.
*Architecture* stopped being true when the four-component decomposition was
demoted to RECOMMENDED — the document is a conformance standard whose
architecture is optional.

**The name was taken.** Searching "HACA specification" returns Huawei's HACA
authentication protocol.

**OBEC** — Operator-Bounded Entity Continuity — was chosen after seven candidates
were eliminated on collision: *Keel*, *Writ*, *Catena*, *Origo*, *Perdura*,
*Anchora*, *Auctor*. Two findings came out of that search and are worth keeping:

- Single dictionary words, including Latin ones, are exhausted in the agent space
  as of 2026. What still works is the register the attestation family uses —
  SPIFFE, Sigstore, in-toto, SLSA.
- **Acronym collision is survivable when it is in a different room, and fatal
  when it is in the same room.** MCP collides with *Master Control Program* and
  won anyway. *BEC* — the first candidate for Bounded Entity Continuity —
  collides with *Business Email Compromise* inside the security and compliance
  room, which is the audience the specification is written for. OBEC's collisions
  (a Thai education agency, the Czech word for municipality) are in other
  buildings.

The expansion is also the most accurate name considered: it encodes OC-001 and
OC-002, the two invariants the set opens with.

---

## 7. Consequences

**The invariant/requirement distinction collapsed.** Every rule that survived the
"can it be given a mechanical test?" filter also passed the "could a
configuration plausibly relax this?" filter. All ten are invariants; there are no
ordinary requirements left. A rule that may be switched off by a setting is not a
guarantee, it is a default, and there are no defaults.

**Revision became expensive, then survivable.** Because every rule is an
invariant, the version rule inherited from HACA-Core K2 would have made any
change — wording included — a major version that severs every entity's chain.
§4 replaces that with three mechanisms: what is version-bound narrows to the
normative kernel; revisions are classified and only weakening breaks continuity;
and migration becomes a chain event under OC-004(c). This is the one place
HACA-Core abandoned its own logic — everywhere else change is handled by making
it authorized, recorded and traceable — and applying that logic to the
specification's own revision was the fix.

**Adoption cost dropped.** Demoting the four-component decomposition to
RECOMMENDED is what lets an existing runtime claim conformance without being
rewritten, and it costs no guarantee: no invariant names a component. The
architecture remains fully specified as the reference decomposition, and the
reference platform realizes it.

**Three documents, three audiences.** The normative kernel (what is expensive to
change, short enough to read at once), the Core (the same rules with their tests
and rationale), and the Profile (the machinery, as SHOULD). This record is the
fourth audience — the one asking why — and it was extracted from the Core for the
same reason the other three were separated.

---

## 8. Status of the predecessor

HACA-Core 0.3.0, HACA-CMI and HACA-Security live in the HACA repository, not in
this one. OBEC replaces them and is not derived from them any further: the
reference implementation is being written from this specification alone, and
where the specification is not enough to implement from, that is a defect to
fix here rather than a reason to consult the predecessor.

The two extensions OBEC-Core names — Security and CMI — are planned and not yet
written. When they are, they will be written against OBEC-Core, not ported from
HACA-Security and HACA-CMI.

No entity should be created under OBEC before 1.0, because OC-004(a) records
the major version in the Genesis Anchor and a pre-1.0 version can still change
beneath it.
