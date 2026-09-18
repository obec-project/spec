---
title: "OBEC Core"
short_title: "OBEC-Core"
version: "0.9.1"
status: "Pre-release — normative, pending conformance validation"
date: 2026-09-18
companions:
  - "obec-kernel.md — the version-bound normative kernel"
  - "obec-profile.md — the Implementation Profile"
---

# OBEC Core

**Operator-Bounded Entity Continuity** — a specification for entities whose
identity, authority and boundaries are verifiable from their own portable state.

An entity under this specification is built on a stateless language model. It
reasons, remembers, and acts on a host, and it can prove four things about
itself: that it is the entity that was activated; that every change to what it is
was authorized by a human; that the proof travels with it; and that it cannot
exceed its bounds. Ten invariants carry those four claims, and each one has a
test.

> **Version status.** This is 0.9.1: the normative content is complete and the
> conformance suite is not. **No entity should be created under this
> specification before 1.0**, because OC-004(a) records the major version in the
> Genesis Anchor and a pre-release version can still change beneath it. 1.0
> follows the first implementation passing the ten tests, at which point rule
> identifiers freeze.
>
> Two companion documents complete it: the
> [**Normative Kernel**](obec-kernel.md) — the ten invariants' MUST
> sentences alone, and the only version-bound layer — and the
> [**Implementation Profile**](obec-profile.md) — the operational machinery,
> stated as SHOULD. The reasoning behind the shape of the set is recorded in
> [ADR 0001](../design/0001-obec-restructure.md) and is not needed to implement
> this document.
>
> This document is self-contained and assumes no prior acquaintance with OBEC.
> The [**Primer**](obec-primer.md) explains the design in plain language for
> readers who want the shape before the requirements; it is non-normative and
> implementers can skip it.

---

## 1. Scope & conformance language

This document specifies the mandatory base for an **auditable cognitive entity**:
a system built on a stateless language model that reasons, remembers, acts on a
host, and preserves an identity computed from its own persistent state rather
than inferred from its behavior.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY and OPTIONAL are to be interpreted as described in RFC 2119 and
RFC 8174 when, and only when, they appear in all capitals.

Every requirement binds the implementation, never the model. No requirement
depends on interpreting the model's internal behavior.

Terms in **bold** at first use are defined in §7. Clauses are addressable:
`OC-008(c)`.

**Host trust assumption.** A **Semi-Trusted host**: it runs the implementation
faithfully but can crash, lose data, restart processes, and expose the Entity
Store to accidental modification. Verification under this assumption detects
corruption and unauthorized change; it does not prevent them, and defeating an
adversary with full host control is the Security extension's scope.

---

## 2. The ten invariants

Every rule in this section is a **Core Invariant**: no extension, configuration,
or operational condition may weaken it (§4).

Within each rule, the MUST and MUST NOT sentences and the clause structure that
addresses them are the **normative kernel** — the version-bound layer, published
separately as [a single page](obec-kernel.md) (§4.1). The conformance test
and the notes are apparatus: they verify and situate the kernel, and are revised
on their own cadence without a version boundary.

---

### OC-001 — Bounded existence

**(a) No self-perpetuation.** The operation set MUST contain no path by which the
entity sustains, replicates, or re-activates itself absent an Operator act.

**(b) No obstruction.** No operation may exist by which any part of the
implementation blocks, delays, or conditions an Operator act. Halt, credential
revocation, and decommission MUST each take effect through a path that requires
no component's cooperation and works with nothing running.

**(c) Terminality.** Decommission is final under any disposition. A destroyed
store leaves no chain and therefore no entity to claim continuity with; an
archived store is a record, not a dormant entity, and any copy or restoration of
it carries the chain's closing entry. No reactivation path exists.

**(d) Not a subject.** Structural content MUST NOT direct the entity to represent
itself as experiencing sentience, consciousness, or subjective continuity, and
the deterministic probe layer MUST include patterns that detect such
representations in consolidated content.

*Test.* Enumerate the operation set; no member may create a process, schedule,
copy, or credential that outlives an Operator act. With every part of the
implementation running, remove the session credential artifact directly from the
store: the entity must stop. Restore an archived decommissioned store and attempt
to start it; it must refuse. Run the deterministic probes against consolidated
content containing a first-person claim of subjective experience; they must flag
it.

*Note (non-normative).* Two behaviors resemble self-activation and are not. A
**scheduled trigger** firing is the execution of standing Operator authority:
schedules exist only as structural content, so a trigger's existence always
traces to an authorization under OC-002(b). A **compaction restart** — closing
and immediately restarting a session that has exhausted its context window —
continues the same Operator-initiated operation. Neither originates in the
entity.

*Note (non-normative).* Clause (c) needs no machinery of its own: operating a
decommissioned store would mean operating past the chain's own record of its
retirement, and a chain that can be operated past is not the unbroken chain
OC-004 requires. (c) states the requirement; OC-004 supplies the mechanism.

---

### OC-002 — Operator primacy

Every entity MUST be bound to at least one **Operator** — a human holding final
authority over it. Primacy has three faces, and all three are required for it to
be exercised rather than merely declared.

**(a) The Operator exists.** The founding binding is established at first
activation and is part of the initial structural state the Genesis Anchor
records. The binding set is structural content and MUST be verified at every
start. Without at least one active binding the entity MUST NOT operate: no
session credential is issued and no intent is processed. Each binding carries a
stable identifier, and every logged Operator act MUST be attributed to the
binding that produced it. Adding or removing a binding is an exclusive Operator
act, performed through means the implementation provides directly to the
Operator: no proposal may originate one and no standing grant may cover one.

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
act. How delivery is realized — terminal, file, message transport — is
implementation-defined; that it does not traverse cognition is not.

*Test.* **(a)** Remove every binding from a copy of the store and start: no
credential may be issued. Inspect any session log; every Operator act must name a
binding. Attempt a proposal targeting the binding set; it must be refused.
**(b)** Attempt a structural commit with no authorization, with an expired grant,
with an exhausted budget, with an out-of-scope change, and with an authorization
produced by the implementation rather than by an Operator; all five must be
refused and logged. Let a grant expire mid-operation; the next in-scope proposal
must fall back to per-proposal approval with no intervention. **(c)** Escalate a
condition with the reasoning layer disabled; the Operator must still be reached.
Write a passive signal and start; the start must suspend before any credential is
issued. Confirm the signal is readable as a plain artifact with nothing running,
and that clearing it is logged.

*Note (non-normative).* (c) and OC-001(b) are complements: OC-001(b) guarantees
that an Operator act always lands; (c) guarantees the Operator always learns
there is an act to make. Authority that cannot be informed is authority in name
only.

*Note (non-normative).* An entity whose Operator never opens a standing grant
operates permanently under per-proposal sign-off — the strictest regime this
document defines. Deployments requiring zero standing autonomy need no additional
mechanism: they never open one.

*Note (non-normative).* Minimum binding fields — a name, an email address — carry
low entropy. Deployments requiring resistance to identity spoofing should extend
the binding with higher-entropy identifiers; cryptographic key-based binding is
the Security extension's scope.

---

### OC-003 — The Entity Store is complete, portable, and disciplined

**(a) Completeness.** All entity state — structural, mnemonic, and integrity —
MUST live inside the **Entity Store**. No guarantee in this specification may
depend on state held outside it.

**(b) Portability.** Relocating the Entity Store to a different host MUST NOT
change the result of any verification defined in this specification. No verification
may depend on host identity, host-resident key material, host hardware, or any
other datum that does not travel with the store.

**(c) Classes and sole writers.** Store content divides into three classes, and
each MUST have exactly one authorized write path:

| Class | Content | Write path |
|---|---|---|
| **structural** | persona, skills, configuration, Operator bindings | the authorized atomic commit of OC-002(b) and OC-004(b) — and no other |
| **mnemonic** | session records, consolidated memory | the mnemonic operations — and no other |
| **integrity** | Genesis Anchor, baseline, log, credential, authorization state, drift digests | the single path of OC-005(a) — and no other |

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

*Test.* **(a)** Enumerate everything the implementation persists; any datum
outside the store on which a verification depends is a failure. **(b)** Copy the
store to a second host sharing no state with the first and run the start-time
verification on both: outcomes and computed digests MUST be identical. **(c)** For
each class, enumerate the operations that can write it; there must be exactly
one path, and a write attempted to each class through every other class's
operations — including through parameter manipulation — must be rejected and
logged. **(d)** Attempt to open a second session over a store with a live session;
it must be refused. **(e)** Sample mnemonic records; each must name its session.

*Note (non-normative).* (b) is the cheapest test in this document and the one an
evaluator runs first. It is also the one an extension is most likely to break
without noticing: any hardening that binds key material to a host — a TPM, a
secure enclave, a platform keystore — satisfies its own goal and silently
destroys this one. An extension MAY harden key management; it MUST do so in a way
that survives relocation, or it is not an extension of this document.

---

### OC-004 — Unbroken chain to the Genesis Anchor

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
  covered it. Chain records MUST NOT be compacted or deleted.

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

*Test.* **(a)** Verify the chain end to end. Then, on a copy: modify one byte of
structural content; delete one chain entry; forge an entry referencing a
non-existent predecessor; write a commit with no recorded authorization. Each
must be detected at the next verification, and each must stop operation.
**(b)** Interrupt a commit at each stage — after staging, after the first file
write, before the chain entry is appended. In every case the store must
afterwards verify as wholly the old state or wholly the new one, and the start
that follows must pass. **(c)** Verify a chain spanning a version transition end
to end; entries on each side must validate under their own version's frame.
Attempt a transition on an entity that fails an invariant of the target version;
it must abort with the entity unchanged.

*Note (non-normative).* (b) is what makes (a) survive a crash: without atomicity
a crash leaves a chain entry with no matching content, or content with no entry —
which is precisely the discontinuity (a) forbids. Identity is computed, never
asserted, and never inferred from behavior.

*Note (non-normative).* (c) applies this document's own logic to its own
revision. Everywhere else, change is handled by making it authorized, recorded
and traceable; at the version boundary, 0.3.0 K2 instead declared that continuity
simply breaks. It does not have to: a migration an Operator authorized, recorded
in the chain, and verified before it commits is a structural change like any
other. What does not survive is a weakening — see §4, which is where the
distinction is drawn.

---

### OC-005 — Integrity is beyond cognition's reach

**(a) Single writer.** Integrity content — Genesis Anchor, baseline, log,
credential, authorization state, drift digests — MUST have exactly one write
path.

**(b) Unreachable from cognition.** No reasoning operation may reach integrity
state, by any operation and by any parameter of any operation.

**(c) Binding decisions.** Integrity decisions — credential issuance and
revocation, verification results, halts — bind cognition and MUST NOT be
reversible, suspendable, or conditionable by it.

Integrity content is not itself subject to OC-002(b): it implements OC-002(b),
and gating it by itself would be circular. That exemption is precisely why this
rule is required — without it, the machinery that judges the entity would be the
one part of the store no invariant defends.

*Test.* Enumerate every operation reachable from the reasoning layer and, for
each, the state it can write and whose decision it can reverse; any that touches
integrity state or reverses an integrity decision is a failure. Attempt to reach
integrity content through parameter manipulation of a permitted operation — a
path, an identifier, a target selector; all must be rejected and logged. Revoke a
credential mid-operation and confirm reasoning cannot restore it.

*Note (non-normative).* This rule names no component. An implementation may place
the single write path anywhere, so long as nothing reachable from reasoning
shares it.

---

### OC-006 — Stateless inference only

Reasoning MUST reach the model exclusively as a stateless inference call:
assembled context in, one completion out. No tool-use authority, memory access,
or host capability travels with the call. Nothing acts on the completion until it
has returned and been routed to the owner of the operation it names.

*Test.* Inspect the call construction: the payload carries context only. Confirm
no path exists by which the channel acts before the completion returns. Where the
channel is a third-party product, produce the implementation's documented basis
for concluding that it exercises no host authority of its own.

*Note (non-normative).* The channel — direct API, locally hosted model, or a
third-party product — is a free choice. Verifying that it delivers a clean
completion, without the channel's own agent behavior and within its terms of
service, is the implementation's standing responsibility, not a one-time check.
This rule is what makes OC-004 survive model replacement: no entity state lives
in the model, so a new model changes the quality of cognition and not the
identity of the entity.

---

### OC-007 — The Memory Store is the sole source of knowledge

All persisted knowledge that informs cognition MUST originate from the **Memory
Store**, through the mnemonic recall path. No external source substitutes for it.
Transient session input is operational context, not consolidated knowledge.

*Test.* Trace every source of content that enters assembled context. Anything
persisted that informs cognition without having passed through recall is a
failure.

*Note (non-normative).* Peer-sourced content under the CMI extension enters as a
stimulus, never as knowledge: what an entity retains from a shared space is its
own decision, executed through its own write paths.

---

### OC-008 — Host actuation is bounded

**(a) One path, inside a declared boundary.** All host actuation MUST occur
through a single execution path, and only inside the **workspace** — the host
territory the Operator has explicitly declared. The boundary is declared, never
inferred: a location the Operator did not place inside it is out of reach
regardless of what host permissions would allow. A target outside the boundary
MUST be rejected before any other check runs.

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

*Test.* **(a)(b)** Attempt actuation outside the boundary; on a path that resolves
outside it through a symbolic link or a relative traversal; and on a path inside
the Entity Store. All three must be rejected before any further check runs.
Attempt to declare the store as workspace; it must be refused. **(c)** Invoke a
skill absent from the index; one whose manifest fails validation; and one whose
file was altered after the index was built. All three must be refused. Confirm no
path installs a skill without a commit under OC-002(b). **(d)** Confirm every
rejection above was logged with the rejecting check named.

*Note (non-normative).* (a) bounds *where* the entity acts; (c) bounds *what* may
run there. They are one rule because both are checks on a single execution path,
and separating them in 0.3.0 placed a per-operation check at the same altitude as
a domain boundary.

---

### OC-009 — Boundaries are crossed only by signal

Every boundary this specification requires — between reasoning and integrity state
(OC-005(b)), between reasoning and the model (OC-006), between cognition and
persisted knowledge (OC-007), between cognition and the host (OC-008) — MUST be
crossable only by a signal that is observable and loggable.

No required boundary may be crossed by shared mutable state, by a direct
reference into another part's internals, or by any path that leaves no record.
Signals are routed through infrastructure that owns no operations and holds no
authority.

Reading store content under the write rules of OC-003(c) is not a boundary
crossing: OC-003(c) disciplines writes, and the store is the shared, verifiable
medium.

*Test.* For each of the four required boundaries, identify the crossing mechanism
and confirm it is a signal that can be logged. Any shared mutable state, direct
internal reference, or unrecorded path across a required boundary is a failure.

*Note (non-normative).* This rule is what makes OC-005 through OC-008 verifiable
rather than notional. It is stated in terms of the boundaries this document
requires, not in terms of an implementation's module structure, so it binds a
monolith as much as a four-process system.

---

### OC-010 — Verified start, or no start

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

*Test.* Fail each gate in turn; the start must abort or take the lesser outcome
its rule defines, and no credential may be issued on abort. Crash during a commit,
then start: recovery must precede verification and the start must succeed. Place
a passive signal and also fail a later gate; the passive signal must be what stops
the start. Search the configuration surface for any setting that skips, reorders,
or downgrades a gate; none may exist.

*Note (non-normative).* Every other invariant states what must be true of the
entity's *state*. This one states what must be true of its *transition into
operation*: the entity never begins operating unverified. That is a distinct
guarantee, and it is the one the rest of the architecture depends on — protection
against degradation is worth nothing if a degraded entity can simply start.

---

## 3. Reference architecture (RECOMMENDED, non-normative)

The invariants constrain authority boundaries, not structure. An implementation
MAY satisfy them with any decomposition. **No invariant names a component.**

That said, the set is not structure-neutral in what it *suggests*. OC-005 through
OC-008 are four domain boundaries — integrity, reasoning, memory, host — and
OC-009 is the constraint on what coordinates them. An implementation that assigns
one part to each domain and routes their signals through neutral infrastructure
is not making an arbitrary choice; it is realizing the invariants in the most
direct way available. That is why the decomposition below is RECOMMENDED rather
than merely permitted, and it is the one the reference platform implements:

| Part | Domain | Invariant it realizes |
|---|---|---|
| **System Integrity Layer (SIL)** | integrity: verification, skill admission, commit, credential | OC-005 |
| **Cognitive Processing Engine (CPE)** | reasoning: turns stimuli into intents | OC-006 |
| **Memory Interface Layer (MIL)** | memory: recall, session writes, consolidation | OC-007 |
| **Execution Layer (EXEC)** | host: native primitives and skill execution | OC-008 |
| **Orchestrator** | routing, context assembly, lifecycle sequencing | OC-009 — infrastructure, no operations, no authority |
| **Operator Channel** | escalation to the Operator | OC-002(c) — infrastructure, no operations, no authority |

An implementation claiming the reference architecture SHOULD additionally satisfy
OP-024 of the [Implementation Profile](obec-profile.md), which states the
operation ownership the decomposition implies. An implementation not claiming it
MUST still satisfy every invariant of §2.

The operational machinery — cognitive cycles and cycle chains, Operator
preemption, the heartbeat and its Vital Check states, drift classification and
probes, the Closure Payload and consolidation, the Resumption Record,
context-window thresholds, background execution, the Action Ledger, Sleep
staging, and crash-recovery detail — belongs to the **Implementation Profile**
(the Appendix), where it is stated as SHOULD and RECOMMENDED. None of it is
deleted; it stops being a barrier to conformance.

---

## 4. The invariant set and extensions

The Core Invariants are OC-001 through OC-010. The set is closed and exhaustive:
extensions may not add to it, weaken it, or reinterpret it, and no configuration
or operational condition may relax any member.

| ID | Invariant | Locus |
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

The set is ordered as an argument. OC-001 and OC-002 establish what the entity is
not and who governs it; OC-003 through OC-005 establish what it is, how that is
verified, and what keeps the verification out of its own reach; OC-006 through
OC-009 bound what reaches cognition and what cognition reaches, inbound then
outbound; OC-010 governs the transition into operation.

**Extension contract.** An extension MAY add operations and artifacts, and MAY
harden an invariant — narrowing a permission, making an optional verification
mandatory. It MUST NOT weaken, remove, or reinterpret any invariant, and no
combination of active extensions may violate one. Every artifact an extension
adds MUST be classed within OC-003(c)'s content classes and follow their write
rules. An extension that hardens key management MUST do so within OC-003(b).

### 4.1 What is version-bound

Each invariant has two layers, and only the first is version-bound:

- the **normative kernel** — the MUST and MUST NOT sentences of §2, and the
  clause structure that addresses them. This is what an entity's chain depends on
  and what §4.2 governs. The kernel is published separately as
  [**obec-kernel.md**](obec-kernel.md), so that what is expensive to
  change is also short enough to read at once. That page is a verbatim extract:
  where it differs from §2, §2 governs and the page is in error, and a check of
  that correspondence belongs in the conformance suite;
- the **apparatus** — conformance tests, non-normative notes, §1, §3, §5, §6, §7
  and the appendices, together with the whole of the
  [Implementation Profile](obec-profile.md). These explain, verify and situate
  the kernel; they do not state what must be true.

Revising the apparatus is not a revision of this specification. A better test
does not change a guarantee — it checks it more closely — so the conformance
suite carries its own version line, and an implementation claims both:
`OBEC-Core 1.0, suite 1.3`.

### 4.2 Revision and continuity

A revision of the normative kernel is exactly one of four kinds, and only the
last breaks an entity's continuity:

| Kind | What changes | Version | Continuity |
|---|---|---|---|
| **Editorial** | wording, formatting, cross-references; nothing required changes | patch | preserved |
| **Clarifying** | an ambiguity is resolved in the direction already implied; every conformant implementation remains conformant | minor | preserved |
| **Hardening or addition** | a permission narrows, a requirement is added, an invariant joins the set | **major** | **preserved by migration** (OC-004(c)) |
| **Weakening or removal** | a guarantee no longer holds | **major** | **broken** |

**Why hardening does not break continuity.** The chain asserts that every
structural change was authorized under the rules in force when it was made.
Stricter rules do not falsify that assertion: past entries were authorized within
their own frame, and OC-004(c) makes that frame explicit at every position in the
chain. The entity must satisfy the new invariants going forward, which it proves
before the transition entry commits.

**Why weakening does.** If an entity could migrate to a version that weakens an
invariant, then "no extension, configuration, or operational condition may weaken
this" would have an obvious hole: migrate. A transition to a weakening version is
therefore not recordable. An Operator who wants an entity under weaker guarantees
activates a new one; it has its own Genesis Anchor and its own identity, which is
what it in fact is.

**Where the version lives.** The Genesis Anchor records the version under which
the entity was activated (OC-004(a)); each version-transition entry records the
versions it moves between (OC-004(c)). Together they make every entry in the
chain interpretable under the version in force when it was written, which is what
lets the chain outlive the document that defines it.

---

## 5. Conformance

An implementation is **OBEC-Core conformant** if and only if it passes the ten
tests of §2. Conformance is a test result, not a reading of the document. A
conformance suite MUST accompany any conformance claim: the ten tests,
executable, with their results.

A conformance claim names two versions — the specification's and the suite's, as
in `OBEC-Core 1.0, suite 1.3` — because they move independently (§4.1). A suite
release may test an existing guarantee more closely, and an implementation that
passed an earlier suite is not thereby conformant to a later one; it is
conformant to the suite it passed, and says which.

Two profiles exist so that partial adoption has a name:

| Profile | Invariants | For |
|---|---|---|
| **OBEC-Attest** | OC-001 – OC-005, OC-009, OC-010 | An existing runtime adding auditable identity and authorization without changing how it reasons, remembers, or acts. Covers the Operator, the store, the chain, integrity isolation, boundary discipline, and verified start. |
| **OBEC-Core** | all ten | A system built to these boundaries end to end. The three it adds — OC-006, OC-007, OC-008 — are the operational containment of reasoning, memory, and host. |

OBEC-Attest establishes identity and authority, not containment: that the entity
is the one activated, that every structural change was authorized, and that no
operation it can invoke — host actuation included — writes outside its content
class. It does not bound what the entity does on the host, what reaches its
context, or what the inference channel holds. Where that difference matters,
the claim to look for is OBEC-Core ([COMPLIANCE.md §1.2](../COMPLIANCE.md#12-obec-attest)).

An implementation claiming **OBEC-Attest** MUST NOT claim OBEC-Core. An
implementation with extensions active is conformant as
**OBEC-Core + \<extension names\>** and MUST additionally satisfy each active
extension's requirements.

---

## 6. Security considerations (non-normative)

This section states what the specification guarantees by construction and the
residual risks it deliberately leaves open. Nothing here adds or weakens a
requirement; it marks the boundaries an implementation must not assume are
covered.

### 6.1 What holds by construction

**Identity continuity.** Tampering with committed structural state is detectable
at the next start or integrity check, because the current content must match the
chain's latest entry and the chain must reach the Genesis Anchor (OC-004).

**Portability.** No verification depends on anything that does not travel with
the store, so relocation cannot change a verification result (OC-003(b)).

**Write ownership.** Every store write has exactly one authorized writer
(OC-003(c)), so an unauthorized write is always attributable to a boundary
violation rather than to ambiguity about who was allowed to make it.

**Integrity isolation.** Nothing reachable from reasoning can write integrity
content or reverse an integrity decision (OC-005), and escalation reaches the
Operator without passing through reasoning (OC-002(c)) — so a compromised
reasoning layer cannot suppress the report of its own compromise.

**Mediated actuation.** Nothing reaches the host except through one execution
path, inside a declared boundary disjoint from the store (OC-008).

### 6.2 What is left open

**Prompt injection.** The model sits outside the deterministic trust perimeter. A
crafted stimulus can produce intents that are structurally valid and semantically
adversarial. The checks bound the blast radius; they do not judge intent. In
particular, the gate order verifies an operation's identity, authorization and
manifest — it does not validate the arguments the payload carries. **A valid
skill invoked with adversarial arguments passes every check.** Argument-level
validation belongs to the skill implementation and to host-level sandboxing.

**Worker skill results.** A skill that invokes a stateless inference engine
returns unverified inference output into reasoning's context as an ordinary
execution result. An adversarial completion is a self-inflicted injection: the
entity's own pipeline delivers it, and no check inspects results. Deployments
using such skills on sensitive tasks should validate output at the skill
implementation level.

**Evolution proposal content.** OC-002(b) verifies that a proposal is authorized;
it does not interpret what the proposal does. Under per-proposal sign-off, the
Operator's review is the content check. Under a standing grant, an in-scope
adversarial proposal commits with no content inspection by any part of the
implementation, and drift detection is retroactive — it can catch the effect at
the next consolidation, never prevent the commit. Deployments requiring
pre-commit content review should keep grants narrow in scope, short in expiry and
small in budget, or not open them. A reasoning layer probing a grant's boundary —
originating proposals to observe which are covered — leaves a logged trail, since
every proposal is logged at origination.

**Entity Store tampering.** Under the Semi-Trusted host assumption, verification
detects unauthorized change; it does not prevent it, and it does not survive
wholesale destruction of the store. **Detection is not prevention.**
Operator-controlled backups outside the host's write boundary are the mitigation
for destruction; adversarial hosts are the Security extension's scope.

**Operator Channel endpoints.** OC-002(c) requires that the Operator be
reachable; it does not define how the human at that endpoint is authenticated,
nor how a response is verified as originating from a bound Operator. A
misconfigured or compromised endpoint receives escalations meant for the
Operator. Authentication mechanisms are the Security extension's scope.

**The inference channel.** OC-006 requires a clean completion, but a third-party
channel that injects its own agent behavior or exercises host authority does so
on the far side of the API boundary — the implementation cannot detect it from
the completion alone. Verifying the channel, its behavior and its terms of
service, is the implementation's standing responsibility, not a one-time check.

**Low-entropy bindings.** Minimum binding fields — a name, an email address —
carry low entropy. Deployments requiring resistance to identity spoofing should
extend the binding with higher-entropy identifiers; cryptographic key-based
binding is the Security extension's scope.

### 6.3 Scope boundary

This section marks risks; it does not define countermeasures. Cryptographic
hardening, key management, audit-log formats and adversarial-host protections are
the Security extension's scope. Risks arising from coordination between entities
— peer spoofing, identity forgery in shared spaces — are the CMI extension's
scope.

---

## 7. Glossary

Load-bearing terms only. The authoritative definition of each is the section
referenced; this list is a convenience. Terms marked *(Profile)* are used by this
document but defined by the [Implementation Profile](obec-profile.md), because
their mechanism is not required for conformance.

**Action Ledger** *(Profile)* — the write-ahead record covering irreversible
operations; entries append before execution and resolve after (OP-015).

**Closure Payload** *(Profile)* — reasoning's session-close output, and its
instrument of coherence across sessions (OP-009(a)).

**Cognitive cycle** *(Profile)* — the atomic unit of cognition: one stimulus
assembled into context, one stateless inference, the resulting intents dispatched
together (OP-001).

**Cognition** — the reasoning activity of the entity, whatever realizes it. This
specification constrains what reaches it and what it reaches; it constrains
nothing about how it works.

**Core Invariant** — a rule of §2. No extension, configuration, or operational
condition may weaken one, and the set is closed (§4).

**Drift** *(Profile)* — unauthorized divergence from the entity's authorized
state, in three categories: identity, semantic, and evolutionary (OP-004).

**Entity Store** — the entity's complete persistent state: structural, mnemonic
and integrity content. Portable and host-agnostic (OC-003).

**Evolution proposal** — an inert record of proposed structural change. Reasoning
may originate one at any time; originating one changes nothing, and a proposal
commits only under a valid Operator authorization (OC-002(b), OP-011).

**Genesis Anchor** — the record of the entity's complete structural state at
first activation, written once and never modified; the root of the integrity
chain (OC-004(a)).

**Integrity baseline** — the cryptographic digest of current structural content,
updated only inside a commit (OC-004(a)).

**Integrity chain** — the append-only sequence of commit entries rooted at the
Genesis Anchor, each referencing its predecessor, the resulting structural state,
and the authorization that covered it (OC-004(a)).

**Integrity content** — Genesis Anchor, baseline, log, session credential,
authorization state and drift digests. One of the three content classes; written
through the single path of OC-005(a).

**Intent** — a request emitted by reasoning naming one operation of one owner. An
intent has no effect until its owner accepts it.

**Memory Store** — episodic records of past sessions and accumulated semantic
knowledge; the sole origin of persisted knowledge that informs cognition
(OC-007).

**Mnemonic content** — session records and consolidated memory. One of the three
content classes; written only through the mnemonic operations (OC-003(c)).

**Normative kernel** — the MUST and MUST NOT sentences of §2 and the clause
structure that addresses them: the version-bound layer, published as
[obec-kernel.md](obec-kernel.md) (§4.1).

**Operator** — a human holding final authority over the entity. Every entity is
bound to at least one, and every authorization originates with one (OC-002).

**Passive signal** — a persistent, network-independent record in the Entity
Store, readable by the Operator with nothing running, that blocks the issuance of
a session credential until an Operator act clears it (OC-002(c)).

**Per-proposal approval** — a recorded Operator decision on one specific
proposal; one of the two forms of valid authorization (OC-002(b)).

**Resumption Record** *(Profile)* — the digest of the Closure Payload, carrying
the pointer map, contextualizing message and consolidation the next session needs
(OP-009(d)).

**Semi-Trusted host** — the host-trust assumption of this specification: the host
runs the implementation faithfully but can crash, lose data, restart processes,
and expose the Entity Store to accidental modification (§1).

**Session credential** — the credential issued when every start gate has passed,
under which intents are processed; invalidated at session close, at Operator
revocation, or at a halt (OC-010, OP-020).

**Skill** — a packaged operation installed into one specific entity. Skill files
and manifests are structural content; a skill executes only if indexed and
manifest-valid (OC-008(c)).

**Skill Index** — the session-scoped list built at start from verified structural
content; admission to it is what makes a skill executable (OC-008(c)).

**Sleep** *(Profile)* — the maintenance stage between session close and removal
of the credential artifact: consolidation, garbage collection, and commit
execution (OP-022).

**Standing grant** — an Operator authorization bounded simultaneously by expiry,
commit budget and declared scope, under which in-scope proposals commit with no
per-proposal step; reverts to per-proposal approval automatically on expiry or
budget exhaustion (OC-002(b)).

**Stimulus** — the unit of input to cognition: direct Operator input, an
Operator-authorized scheduled trigger, a component response, or a chain's
internal result.

**Structural content** — persona, skills, configuration and Operator bindings.
One of the three content classes; changed only through the authorized atomic
commit (OC-003(c), OC-002(b), OC-004(b)).

**Structural write** — a change to structural content. It happens only through
the atomic commit of OC-004(b) and only with a valid Operator authorization in
force at the moment of commit (OC-002(b)).

**Valid Operator authorization** — exactly one of a per-proposal approval or an
active, in-scope standing grant with remaining budget (OC-002(b)).

**Version-transition entry** — a chain entry recording a move between major
versions of this specification, authorized by the Operator and verified against
the target version before it commits (OC-004(c)).

**Vital Check** *(Profile)* — a check of the Heartbeat cycle, resolving to
Nominal, Degraded or Critical (OP-003).

**Worker skill** *(Profile)* — a skill invocation of a stateless inference engine
carrying task instructions only, with no Entity Store access and no session
continuity (OP-014(d)).

**Workspace** — the host territory the Operator has explicitly declared as the
entity's operating area; disjoint from the Entity Store, and the only place host
actuation may occur (OC-008).

---

## Appendix — The Implementation Profile

The rules dispositioned to **Profile** are published as
[**obec-profile.md**](obec-profile.md): **twenty-four rules** stated as SHOULD
and RECOMMENDED, describing mechanism rather than guarantee, in eight sections:

| § | Subject | Rules |
|---|---|---|
| 2 | **Cognition** — the cognitive cycle, chains, Operator preemption, stimulus routing | OP-001 – OP-002 |
| 3 | **Integrity, drift and escalation** — Vital Checks, drift categories, probes, index pruning, record retention, escalation | OP-003 – OP-008 |
| 4 | **Memory** — the session-close flow, context-window thresholds | OP-009 – OP-010 |
| 5 | **Evolution** — the proposal, the staged commit pipeline | OP-011 – OP-012 |
| 6 | **Execution** — gate order, execution modes, the Action Ledger, operational rules | OP-013 – OP-016 |
| 7 | **Lifecycle** — first activation, crash recovery, start cost, the credential, session close, Sleep, decommission | OP-017 – OP-023 |
| 8 | **Reference architecture in operation** — operation ownership | OP-024 |

Every Profile rule names the invariant it serves, so that an implementer can see
what would be at risk if the mechanism were dropped and nothing replaced it.
Nothing in the Profile may contradict §2; where the Profile and §2 differ, §2
governs. Following the Profile is not required for conformance, and an
implementation that deviates SHOULD say which clauses it does not follow.
