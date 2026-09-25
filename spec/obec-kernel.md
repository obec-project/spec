---
title: "OBEC Core — Normative Kernel"
short_title: "OBEC-Kernel"
version: "0.10.0"
status: "Proposal — the version-bound layer of OBEC-Core"
date: 2026-09-24
companion_to: "OBEC-Core 0.10.0"
---

# OBEC Core — Normative Kernel

**This page is the whole of what OBEC-Core requires.**

It carries the normative sentences of [OBEC-Core §2](obec-core.md) and
nothing else — no conformance tests, no rationale, no notes, no examples. It is
the **version-bound layer**: changing any sentence here is a revision of the
specification under OBEC-Core §4.2. Everything outside this page — the tests, the
[Implementation Profile](obec-profile.md), the explanatory sections — is revised
on its own cadence without a version boundary.

It is short on purpose. What is expensive to change should be short enough to
read at once.

**This page is a verbatim extract.** Where a sentence here differs from OBEC-Core
§2, §2 governs and this page is in error.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY and OPTIONAL are to be interpreted as described in RFC 2119 and
RFC 8174 **when, and only when, they appear in all capitals**. Clauses are
addressable: `OC-008(c)`.

---

## The ten

| | Invariant | Locus |
|---|---|---|
| **OC-001** | Bounded existence | Operator |
| **OC-002** | Operator primacy | Operator |
| **OC-003** | The Entity Store is complete, portable, and disciplined | Entity Store |
| **OC-004** | Unbroken chain to the Genesis Anchor | Entity Store |
| **OC-005** | Integrity is beyond cognition's reach | integrity |
| **OC-006** | Stateless inference only | reasoning |
| **OC-007** | The Memory Store is the sole source of knowledge | memory |
| **OC-008** | Host actuation is bounded | host |
| **OC-009** | Boundaries are crossed only by signal | coordination |
| **OC-010** | Verified start, or no start | transition |

No extension, configuration, or operational condition may weaken any of them.

---

## OC-001 — Bounded existence

**(a)** The operation set MUST contain no path by which the entity sustains,
replicates, or re-activates itself absent an Operator act.

**(b)** No operation may exist by which any part of the implementation blocks,
delays, or conditions an Operator act. Halt, credential revocation, and
decommission MUST each take effect through a path that requires no component's
cooperation and works with nothing running.

**(c)** Decommission is final under any disposition. No reactivation path exists.

**(d)** Structural content MUST NOT direct the entity to represent itself as
experiencing sentience, consciousness, or subjective continuity, and the
deterministic probe layer MUST include patterns that detect such representations
in consolidated content.

---

## OC-002 — Operator primacy

Every entity MUST be bound to at least one **Operator** — a human holding final
authority over it.

**(a) The Operator exists.** The binding set is structural content and MUST be
verified at every start. Without at least one active binding the entity MUST NOT
operate: no session credential is issued and no intent is processed. Each binding
carries a stable identifier, and every logged Operator act MUST be attributed to
the binding that produced it. Adding or removing a binding is an exclusive
Operator act, performed through means the implementation provides directly to the
Operator: no proposal may originate one and no standing grant may cover one. The
last active binding MUST NOT be removed: an entity leaves its Operator only by
decommission (OC-001(c)).

**(b) The Operator authorizes.** A structural write MUST happen only through the
atomic commit of OC-004(b), and only with a **valid Operator authorization** in
force at the moment of commit. A valid authorization is exactly one of:

- **per-proposal approval** — a recorded decision by an Operator on that specific
  proposal; or
- **a standing grant** that, at commit time, is unexpired, covers the change
  within its declared scope, and has remaining commit budget. A standing grant
  MUST be bounded on all three axes simultaneously — **expiry**, **commit
  budget**, **declared scope of change categories** — and MUST revert to
  per-proposal approval automatically on expiry or budget exhaustion, with no
  action required from any component.

Every authorization originates with an Operator. **No part of the implementation
may create, modify, or revoke one**, or override, delegate, or substitute for an
Operator decision. An entity MAY originate a proposal at any time, including on
its own initiative; a proposal is inert, and originating one changes nothing.
Every proposal MUST be logged at origination, and every commit MUST be logged
with the identity of the authorization that covered it.

**(c) The Operator is reachable.** There MUST exist a path by which any part of
the implementation reaches the Operator **without passing through the reasoning
layer** — which may be compromised, or may simply have no part in the condition
being reported. That path MUST provide a **passive signal**: a persistent,
network-independent record in the Entity Store, written when live delivery has
failed a declared number of attempts or the condition requires a halt. The
passive signal MUST be directly readable by the Operator with nothing running,
MUST be checked as the first gate of every start, and while it is present **no
session credential may be issued**. Clearing it is an explicit, logged Operator
act.

---

## OC-003 — The Entity Store is complete, portable, and disciplined

**(a) Completeness.** All entity state — structural, mnemonic, and integrity —
MUST live inside the **Entity Store**. No guarantee in this specification may
depend on state held outside it.

**(b) Portability.** Relocating the Entity Store to a different host MUST NOT
change the result of any verification defined in this specification. No
verification may depend on host identity, host-resident key material, host
hardware, or any other datum that does not travel with the store.

**(c) Classes and sole writers.** Store content divides into three classes, and
each MUST have exactly one authorized write path:

| Class | Content | Write path |
|---|---|---|
| **structural** | persona, skills, configuration, Operator bindings | the authorized atomic commit of OC-002(b) and OC-004(b) — and no other |
| **mnemonic** | session records, consolidated memory | the mnemonic operations — and no other |
| **integrity** | Genesis Anchor, baseline, log, credential, authorization state, operational settings, drift digests | the single path of OC-005(a) — and no other |

Configuration is structural content that shapes or bounds the entity.
**Operational settings** — how an Operator runs the entity on a given host, such
as the model it uses or the workspace it acts in — MAY instead be held as
integrity content; they are then changed only by an Operator act, never by a
commit, and are not part of the structural state the chain verifies.

No operation may exist whose parameters allow it to write outside its own class:
a request that would reach another class MUST be rejected whatever operation
carries it.

**(d) One writer at a time.** Two write paths MUST NOT be active over one store
simultaneously, and an implementation MUST NOT run concurrent sessions over the
same Entity Store. A credential artifact found at start that does not match a
crash scenario is a concurrent-session conflict, and the Operator MUST be
notified before any new credential is issued.

**(e) Attributability.** Every mnemonic record MUST be attributable to the
session that produced it.

---

## OC-004 — Unbroken chain to the Genesis Anchor

**(a) The chain.** The entity's structural state MUST be traceable to its state
at first activation through an unbroken sequence of authorized changes. Three
artifacts realize this and MUST exist:

- the **Genesis Anchor** — written exactly once at first activation, recording
  the digest of the complete initial structural state, the founding Operator
  binding, and the major version under which the entity was activated; never
  modified thereafter;
- the **integrity baseline** — the cryptographic digest of current structural
  content, updated only inside a commit;
- the **integrity chain** — one append-only entry per commit, each referencing
  its predecessor, the resulting structural state, and the authorization that
  covered it. Committed chain records MUST NOT be compacted or deleted. An entry
  becomes a chain record when its commit completes; an entry left by a commit
  that did not complete is not one, and restoring the prior state under (b)
  removes it.

Verification is two mechanical checks: current structural content matches the
chain's latest entry, and the chain is unbroken from that entry back to the
Genesis Anchor. An entity that cannot pass both MUST NOT continue operating as
that entity.

**(b) Atomic commit.** The commit that extends the chain MUST write the
structural content, the updated baseline, and the chain entry as one indivisible
operation. A failed commit MUST restore the prior verified structural state. No
partial structural change is ever externally visible.

**(c) Version frame.** Every chain entry is interpreted under the version of this
specification in force at its position in the chain. The chain MAY contain
**version-transition entries**, each recording the version left, the version
entered, and the Operator authorization for the transition. A version-transition
entry is an ordinary commit under OC-002(b) and OC-004(b) in every respect.

Before a version-transition entry commits, the entity MUST be verified against
the invariants of the version being entered. A failed verification aborts the
transition and leaves the entity in the version it held; no partial transition
exists. A transition to a version that weakens or removes any invariant MUST NOT
be recorded: continuity does not survive it (§4).

---

## OC-005 — Integrity is beyond cognition's reach

**(a) Single writer.** Integrity content — Genesis Anchor, baseline, log,
credential, authorization state, operational settings where held there, drift
digests — MUST have exactly one write path.

**(b) Unreachable from cognition.** No reasoning operation may reach integrity
state, by any operation and by any parameter of any operation.

**(c) Binding decisions.** Integrity decisions — credential issuance and
revocation, verification results, halts — bind cognition and MUST NOT be
reversible, suspendable, or conditionable by it.

Integrity content is not itself subject to OC-002(b): it implements OC-002(b),
and gating it by itself would be circular.

---

## OC-006 — Stateless inference only

Reasoning MUST reach the model exclusively as a stateless inference call:
assembled context in, one completion out. No tool-use authority, memory access,
or host capability travels with the call. Nothing acts on the completion until it
has returned and been routed to the owner of the operation it names.

---

## OC-007 — The Memory Store is the sole source of knowledge

All persisted knowledge that informs cognition MUST originate from the **Memory
Store**, through the mnemonic recall path. No external source substitutes for it.
Transient session input is operational context, not consolidated knowledge.

---

## OC-008 — Host actuation is bounded

**(a) One path, inside a declared boundary.** All host actuation MUST occur
through a single execution path, and only inside the **workspace** — the host
territory the Operator has explicitly declared. The boundary is declared, never
inferred: a location the Operator did not place inside it is out of reach
regardless of what host permissions would allow. A target outside the boundary
MUST be rejected before any other check runs. For a skill, the boundary is
applied to what the execution path can see: the targets the skill declares and
the parameters it is invoked with. What an admitted skill's own code does beyond
them is bounded by its admission under (c), not by the path.

**(b) Disjoint from the store.** The workspace and the Entity Store MUST be
disjoint. A target inside the Entity Store MUST be rejected as outside the
boundary however the Operator declared it, so that no host operation can reach
structural, mnemonic, or integrity content by a path other than those OC-003(c)
defines.

**(c) Admitted and valid.** A **skill** — a packaged operation installed into one
specific entity — executes if and only if it is present in the **Skill Index**
and its manifest validation passes at the moment of execution. The Skill Index is
derived state, built at start from verified structural content and living only
for the session. Skill files and manifests are structural content: installing,
removing, or repairing a skill is a commit under OC-002(b). A skill failing
manifest validation is excluded from the index and reported to the Operator.

**(d) Evidenced.** Every rejection MUST carry the check that produced it and MUST
be logged; every result MUST be logged.

---

## OC-009 — Boundaries are crossed only by signal

Every boundary this specification requires — between reasoning and integrity
state (OC-005(b)), between reasoning and the model (OC-006), between cognition
and persisted knowledge (OC-007), between cognition and the host (OC-008) — MUST
be crossable only by a signal that is observable and loggable.

No required boundary may be crossed by shared mutable state, by a direct
reference into another part's internals, or by any path that leaves no record.
Signals are routed through infrastructure that owns no operations and holds no
authority.

Reading store content under the write rules of OC-003(c) is not a boundary
crossing: OC-003(c) disciplines writes, and the store is the shared, verifiable
medium.

---

## OC-010 — Verified start, or no start

Every start MUST be a gated sequence in which every gate is verified before the
session credential is issued. A failed gate aborts the start, except where a
gate's own rule defines a lesser outcome. **No gate is skippable and there is no
degraded start**: an entity either starts verified or does not start. **No
configuration may provide a path that skips a gate, reorders the two constrained
gates below, or issues a credential on a failed gate.**

The sequence MUST include, at minimum: the passive-signal check (OC-002(c)),
detection and recovery of an unclosed previous session, structural verification
against the chain (OC-004(a)), binding verification (OC-002(a)), authorization
state (OC-002(b)), and the Skill Index build (OC-008(c)).

Two ordering constraints are load-bearing and MUST hold: the **passive-signal
check runs first**, and **crash recovery runs before structural verification**,
so that a partial commit is rolled back before the store is verified. The
ordering of the remaining gates is implementation-defined.

---

## The set

The Core Invariants are OC-001 through OC-010. The set is closed and exhaustive:
extensions may not add to it, weaken it, or reinterpret it, and no configuration
or operational condition may relax any member.

**Extension contract.** An extension MAY add operations and artifacts, and MAY
harden an invariant — narrowing a permission, making an optional verification
mandatory. It MUST NOT weaken, remove, or reinterpret any invariant, and no
combination of active extensions may violate one. Every artifact an extension
adds MUST be classed within OC-003(c)'s content classes and follow their write
rules. An extension that hardens key management MUST do so within OC-003(b).

**Revision.** A change to any sentence on this page is a revision of the
specification. Editorial and clarifying revisions preserve continuity; hardening
and addition preserve it by migration under OC-004(c); weakening and removal
break it. A weakening revision requires a new major version and severs every
existing entity's chain — the one revision this specification makes expensive on
purpose.

---

*The conformance test for each invariant, the rationale for the set, and the
operational machinery are in [OBEC-Core](obec-core.md) and the
[Implementation Profile](obec-profile.md). Neither is version-bound; this page
is.*
