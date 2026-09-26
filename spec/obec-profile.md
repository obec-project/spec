---
title: "OBEC Implementation Profile"
short_title: "OBEC-Profile"
version: "0.11.0"
status: "Proposal — companion to OBEC-Core, non-normative for conformance"
date: 2026-09-25
companion_to: "OBEC-Core 0.11.0"
---

# OBEC Implementation Profile

> **Companion document.** [OBEC-Core](obec-core.md) states ten invariants —
> what must be true of an entity, and how to test it. This document states the
> machinery through which implementations have realized them: the operational
> procedures, cadences, records and state transitions that the core deliberately
> does not require.
>
> **Nothing here is required for conformance.** An implementation that passes the
> ten tests of OBEC-Core §2 is conformant whether or not it follows a single rule
> of this document. Where this document and OBEC-Core differ, **OBEC-Core
> governs**.

---

## 1. Scope and status

### 1.1 What this document is

[OBEC-Core](obec-core.md) carries ten invariants: what must be true of an entity,
and how to test it. This document carries the machinery — **twenty-four rules**
describing *how* implementations have realized those guarantees, rather than
*what* must be true of them.

They are stated because they are good. Each was written against a failure an
implementation actually hits — an interrupted Sleep, a context window exhausted
mid-task, an irreversible operation whose result never returned — and an
implementer who ignores them will meet those failures again. But meeting them
differently is not non-conformance, and the core should not have said otherwise.

### 1.2 Conformance language

Rules here use **SHOULD** and **RECOMMENDED** as defined in RFC 2119 and RFC
8174. A **MUST** appears only where it is internal to a mechanism this document
defines — where following the mechanism at all requires that step. Such a MUST
binds an implementation that adopts the mechanism, never one that does not.

Rules are `OP-nnn` with addressable clauses — `OP-014(b)` — so that a deviation
report names the clause rather than the rule it belonged to. Each rule carries a
**Serves:** line naming the invariant it supports, so that an implementer can see
what would be at risk if the mechanism were dropped and nothing replaced it.

> **Numbering.** **Identifiers freeze at 1.0** and are never reused thereafter. A
> withdrawn rule keeps its number and is marked `withdrawn`. Before 1.0 the
> numbering is not yet a commitment.

### 1.3 What deviation costs

Deviating costs nothing in conformance and something in expectation. Two
implementations that both pass the ten tests but realize Sleep differently are
both conformant, and neither can predict the other's behavior at session close.
This matters for tooling and for the Cognitive Mesh Interface (CMI) extension.
It does not make a store portable between implementations: OBEC-Core OC-003(b)
guarantees portability across hosts under the same implementation, and another
implementation may not run a store at all, or run it without preserving its
integrity and the Operator's audit trail.

Where an implementation deviates, it SHOULD say so, naming the clauses it does
not follow. A store that carries such a declaration tells whoever reads it what
the implementation that wrote it did differently.

---

## 2. Cognition

The core constrains what reaches cognition and what cognition reaches. It says
nothing about how cognition advances. This section describes the cycle model
these rules assume.

---

#### OP-001 — The cognitive cycle

**(a) The cycle.** Cognition SHOULD advance in **cognitive cycles**, each the
atomic unit: one stimulus assembled into context, one stateless inference, and
the resulting intents dispatched together.

A single inference may produce more than one intent; each names exactly one
operation of one owner and is independently accepted or rejected. The cycle
completes at dispatch of the full set. What follows for each intent is the
consequence of that intent, and **one intent's outcome is never visible to
another dispatched in the same cycle** — the inference that produced them could
not have seen it either.

An aborted cycle emits nothing: no partial output is observable, and nothing
persists except through a dispatched intent.

**(b) Chains.** A sequence of cycles continuing one cognitive operation with no
new external stimulus between them — each cycle's resolved results serving as the
next cycle's internal stimulus — is a **cycle chain**. Every cycle in a chain
remains individually atomic under (a).

*Serves:* OC-006 (the inference is the atomic step), OC-009 (intents cross
boundaries as signals).

---

#### OP-002 — Stimulus handling

**(a) Operator preemption.** Direct Operator input SHOULD preempt at the cycle
boundary, never mid-cycle: the in-flight inference completes and its intents
dispatch; the input becomes the stimulus of the next cycle to run.

Arriving during a cycle chain, it suspends the chain at that boundary — the
dispatched intents still resolve, their results held as the chain's pending
stimulus — and the chain resumes or is discarded at the Operator's decision.
Suspension or discard never reverses a cycle that has already resolved. A chain
still suspended at session close does not survive it: the close discards the
chain.

**(b) Queueing.** Only direct Operator input preempts. Every other stimulus
queues behind an active chain, logged on arrival and injected after the chain
completes or is discarded.

**(c) No silent drop.** **No stimulus is dropped without a logged record.** Held
results of a discarded chain are logged, never silently dropped.

**(d) Pre-session buffer.** A stimulus received while no valid session credential
exists SHOULD be held in a buffer preserving arrival order, and processed among
the session's first stimuli after the credential is issued.

*Serves:* OC-001 (primacy is exercised, not merely declared), OC-010.

---

## 3. Integrity, drift and escalation

The core requires that integrity be verifiable, beyond cognition's reach, and
that the Operator be reachable. It does not say how often to look, what to do
about a partial failure, or how the report travels. This section does.

---

#### OP-003 — The Vital Check

**(a) Cadence.** A **Vital Check** SHOULD run when an activity threshold is
reached or a time interval has elapsed since the last check, whichever comes
first, both declared in configuration. The recurring cycle of these checks is the
**Heartbeat**.

**(b) States.** A Vital Check SHOULD resolve to one of three states:

- **Nominal** — hashes match, health signals in bounds; operation continues.
- **Degraded** — a localized anomaly verifiable from outside the affected part.
  The verifier signals; the affected part corrects within its own authority; the
  verifier re-verifies **externally**. Verified resolution returns to Nominal;
  failed re-verification, or an anomaly that cannot be externally verified,
  escalates to Critical.
- **Critical** — beyond correction, or involving cognition or the verifier
  itself. The session credential is revoked immediately and the condition
  escalates through OP-008.

An anomaly in cognition itself classifies as **Critical, never Degraded**. The
Degraded corrections that resemble cognitive self-repair in fact target the
transient state around it — assembled context discarded and rebuilt, or an active
cycle aborted without committing. Neither leaves a trace that cognition could
attest to, and external re-verification is what confirms the correction, never
the correcting side's own report.

Transient isolated faults are noise. A condition becomes an anomaly only when it
persists after a corrective attempt, cannot be externally verified, or has no
valid correction path.

*Serves:* OC-004, OC-005 (integrity decisions bind cognition and are not
self-attested).

---

#### OP-004 — Drift classification

Drift is unauthorized divergence from the entity's authorized state. It SHOULD be
classified in three categories, with thresholds and responses declared in
configuration:

**(a) Identity Drift** — active structural content diverging from the integrity
baseline; detected per Vital Check by hash comparison.

**(b) Semantic Drift** — consolidated memory diverging from the probes (OP-005).

**(c) Evolutionary Drift** — a chain discontinuity or authorization gap: a commit
not referencing its predecessor, a state hash not matching its commit, a commit
with no recorded authorization. **Always Critical; no threshold applies** — it is
a direct violation of OC-004.

*Serves:* OC-004.

---

#### OP-005 — Semantic probes

**(a) Probes and digest.** **Semantic Probes** are structural anchors assembled
with the initial structural state at first activation and updated only through
authorized commits. A **Semantic Digest** — an incrementally updated aggregate
over consolidated content, held as integrity content — SHOULD be compared against
the probes during Sleep. The same comparison SHOULD gate semantic promotion
(OP-009(c)): content failing it is not promoted, and the failure is logged.

**(b) Layers and isolation.** Probes SHOULD be defined in two layers. The
**deterministic** layer — required keywords, forbidden patterns, content hashes —
runs first and confirms drift without inference. The **probabilistic** layer —
similarity metrics — runs only when the deterministic layer is inconclusive.

Probabilistic comparison **MUST** run isolated from cognition: a comparison
mechanism must not inherit the drift it detects.

The deterministic layer MUST include the patterns OC-002(d) requires.

*Serves:* OC-002(d), OC-005(b), OC-007.

---

#### OP-006 — Skill index re-verification and pruning

**(a) On demand.** The execution path MAY request re-verification of the skill
index, or of a specific skill, before any execution.

**(b) Pruning.** A skill MAY be pruned from the index mid-session as the
corrective action for a localized anomaly — a manifest or file mismatch found by
a Vital Check or by (a). A pruned skill is immediately non-executable; the prune
is logged and reported to the Operator.

Pruning resolves the skill's availability, not the divergence: the underlying
mismatch remains Identity Drift and follows OP-003(b). Structural repair happens
only through an authorized commit, and the next start rebuilds the index from the
repaired state.

*Serves:* OC-008(c).

---

#### OP-007 — Integrity record retention

**(a) The chain is permanent.** The integrity log is append-only, and **chain
records are never compacted or deleted**.

**(b) Operational records are not.** Routine operational records — Vital Checks,
execution results — MAY follow a compaction policy declared in configuration.

**(c) Checkpoints.** Every `N_ckpt` commits — `N_ckpt` declared in configuration
— a **checkpoint** MAY be recorded: a verified digest of the chain so far, stored
in the integrity baseline within the same commit. Start-time validation then
covers the chain since the last verified checkpoint rather than the whole chain.

A checkpoint is an optimization of verification cost, never a truncation of the
chain: (a) holds regardless.

*Serves:* OC-004, OC-010 (start cost).

---

#### OP-008 — Escalation

**(a) Active mode.** Live delivery SHOULD carry the condition, its severity, the
originating part, and references into the integrity log. Escalations (OP-003(b))
and holds awaiting approval (OP-016) travel this way.

**(b) Passive fallback.** Where live delivery fails `N_channel` consecutive
attempts — `N_channel` declared in configuration — the passive signal of
OC-001(c) is written instead.

**(c) Corroborated escalation of a failed verifier.** Failure of the integrity
path is escalatable like any other condition, and its detection needs no
dedicated mechanism: the Heartbeat cadence is declared in configuration and every
Vital Check leaves a record, so **a newest check older than the declared cadence
is mechanical evidence of an unresponsive verifier**.

Any part MAY act on that evidence — or on the verifier's failure to answer a
signal — and report directly. A peer escalation of this kind SHOULD fire on the
**second reporter**: the first report is recorded and held by the channel
infrastructure, and a second, distinct reporter of the same evidence corroborates
it; the escalation then goes to the Operator.

A cheap realization of the evidence is a liveness record refreshed at each Vital
Check — a timestamp any part compares against the declared cadence with a single
read. Reading store content is not a boundary crossing under OC-009.

*Serves:* OC-001(c), OC-005.

---

## 4. Memory

The core requires that persisted knowledge come from the Memory Store and that
every mnemonic record name its session. It does not say how a session's memory
becomes long-term memory.

---

#### OP-009 — The session-close memory flow

**(a) The Closure Payload.** Consolidation SHOULD be a cognitive act. At session
close, cognition — the only part able to structure memory coherently for its own
later use — consolidates the session's episodic memory and emits the **Closure
Payload**, carrying: the session's consolidation; a declaration of the working
context the next session needs; the message that contextualizes that context and
sets the next steps; and, when the session produced learnings worth persisting,
the requested promotion of episodic memories into semantic memory.

The payload SHOULD be written to the session store **on emission**, which is what
makes Sleep re-executable from it after a crash (OP-018).

**(b) Consolidation and collection.** During Sleep, the memory path SHOULD
process the payload: the Memory Store is written through this path and no other.
In the same Sleep, garbage collection SHOULD remove expired session-store content
under retention rules declared in configuration.

**(c) Semantic promotion.** Semantic memory is refined knowledge. Promotion of
episodic content into the semantic store is requested through the payload and
**SHOULD be gated by the drift comparison of OP-005(a)**. Content that fails the
comparison is not promoted, and the failure is logged.

An implementation MAY also require an Operator authorization for promotion, in
the shape of OC-001(b): a per-promotion approval, or a standing grant bounded by
expiry, budget and scope. The authorization then names the content it covers,
and a promotion waiting for one does not hold up the rest of Sleep — the
content stays episodic, and recallable, until it is authorized or rejected.

**(d) The Resumption Record.** A **Resumption Record** SHOULD be produced during
Sleep as the digest of the payload, carrying three things: a pointer map to the
working memories the next session needs, resolved to Memory Store addresses after
consolidation, within a limit declared in configuration; the message that
contextualizes them and sets the next steps; and the session's consolidation.

Retrieval against it at the next session start follows the normal recall path —
it is a pointer map, not a second source of knowledge. The record SHOULD be
loaded at start only if the integrity log holds the completion record of the
Sleep that produced it; otherwise it is discarded and logged, and the session
starts without resumption context.

*Serves:* OC-007 (recall remains the only path), OC-003(c), OC-010.

---

#### OP-010 — Context-window thresholds

Cognition SHOULD report its context-window utilization as a health signal,
evaluated against two thresholds declared in configuration:

- past the **soft** threshold, cognition SHOULD close the session itself;
- past the **hard** threshold, it is signaled to stop current processing, persist
  the working context worth keeping through normal mnemonic writes, and emit the
  Closure Payload.

The headroom above the hard threshold is the reserve that guarantees this
sequence still fits the window; it SHOULD be sized together with the Vital Check
cadence, so that a breach is detected while the guarantee still holds.

A threshold breach is a **capacity condition, not an anomaly**: OP-003(b)'s state
is unaffected. Either way the session closes normally, Sleep follows, and the
start sequence runs immediately after, delivering the Resumption Record so
cognition continues from where it stopped.

This restart continues the same Operator-initiated operation and is not
self-activation (OC-002(a)).

*Serves:* OC-002(a), OC-007.

---

## 5. Evolution

The core requires that structural change be authorized, atomic and chained. It
does not say what a proposal looks like or how a commit is staged.

---

#### OP-011 — The proposal

**(a) The record.** An **evolution proposal** SHOULD be an inert record carrying
the proposed operations plus a human-readable description. Cognition may
originate one at any time, or one may be recorded on the Operator's direct
instruction. Every proposal is logged when originated. A proposal targeting the
Operator binding set is invalid regardless of origin (OC-001(a)).

**(b) Classification.** Whether a recorded approval exists, or whether the
proposal falls within a standing grant's scope, SHOULD be determined by the
integrity path alone, without input from cognition.

**(c) Held proposals.** A proposal outside a standing grant's scope SHOULD be
held for explicit Operator review, logged, and the session continues. A held
proposal commits only after a recorded approval. A proposal originated under a
grant but not committed before the grant closes falls back to per-proposal
approval: closure withdraws the standing authority, not the proposal's validity.

**(d) Scope categories.** The categories a standing grant's scope may name
SHOULD be declared by the implementation, on its configuration surface; the
binding set is never among them. A category covers the categories beneath it
and nothing else. A grant naming an undeclared category SHOULD be refused, so
that a mistyped scope is not a grant that silently covers nothing.

*Serves:* OC-001(b).

---

#### OP-012 — The staged commit pipeline

Authorized proposals SHOULD be executed during Sleep as a staged pipeline:
**staging → validation → snapshot → atomic commit → resumption**.

The atomic commit writes all structural files, the updated integrity baseline and
the chain entry as one indivisible operation, under a write lock covering
structural content only. A failed commit restores the snapshot and the entity
resumes from its last verified structural state.

Validation runs on the integrity path and SHOULD refuse, whatever authorization
covers the proposal:

- structural content the commit would write — persona, skill manifests,
  configuration, any text the entity is given — that the deterministic probe
  layer flags as directing the entity to represent itself as experiencing
  sentience, consciousness, or subjective continuity;
- a probe set the commit would write that no longer includes the patterns
  OC-002(d) requires. Running the candidate set against a first-person claim of
  subjective experience, and refusing it when nothing is flagged, is one way to
  check.

*Serves:* OC-004(b), OC-002(d).

---

## 6. Execution

---

#### OP-013 — Gate order

The order of checks on the execution path SHOULD be fixed:

1. workspace boundary
2. the Operator's operational rules, including holds for approval (OP-016)
3. index presence, for skills
4. manifest validation

Every rejection carries the gate that produced it and is logged; every result is
returned to cognition and logged.

The boundary check first is not arbitrary: it is what OC-008(a) requires, so that
a target outside the workspace is rejected before any other check runs.

*Serves:* OC-008.

---

#### OP-014 — Execution modes

**(a) Synchronous, under a watchdog.** Execution SHOULD default to synchronous:
it blocks until it returns. A watchdog timer SHOULD run per active execution, and
a deadline expiring before the operation returns is Critical (OP-003(b)).

**(b) Background.** An execution MAY be background: the execution is spawned, a
running record is logged immediately and returned as the intent's resolution, and
the next cycle proceeds without blocking. A terminal record is appended when the
execution completes within its session, and surfaces to cognition as a stimulus
queued under OP-002(b).

A background execution with no terminal record when the session ends is
incomplete: the next start SHOULD surface it to cognition as a reprocessing
stimulus. Background manifests SHOULD declare a handle — a process or job
identifier — and a time-to-live, so that the start can probe or expire the
execution instead of blindly reprocessing it.

**(c) No state between executions.** The execution path SHOULD retain no state
between executions.

**(d) Worker skills.** A **worker skill** invokes a stateless inference engine as
part of its execution: a clean invocation carrying task instructions only, with
no Entity Store access and no session continuity. The invoked model is not an
entity — it has no identity, holds no state, and carries no integrity
obligations. Its result is a normal execution result under OP-013, and no gate
inspects results; deployments using worker skills on sensitive tasks should
validate output at the skill implementation level.

*Serves:* OC-006, OC-008, OC-010.

---

#### OP-015 — The Action Ledger

An operation declared irreversible — by its manifest, or for a native operation
by the implementation's fixed declaration — SHOULD be covered by a write-ahead
**Action Ledger** entry before execution, and closed by a resolution entry after
it. The ledger is integrity content and follows OC-003(c).

Entries without a resolution SHOULD surface to the Operator at the next start,
before the session credential is issued. **They are never silently dropped and
never re-executed automatically.**

*Serves:* OC-008, OC-010.

---

#### OP-016 — Operational rules: allow, deny, hold

The Operator's operational rules over host operations — **allow**, **deny**, or
**hold for approval** — are configuration, and so structural content. The
workspace boundary declaration is either configuration or an operational
setting (OC-003(c)). A held operation waits for an explicit Operator decision;
the decision and its outcome are logged, and the hold travels under OP-008(a).

An allow rule for a skill SHOULD name the admitted content it allows — the
skill's digest — and not only its name. A skill whose content changes, by any
commit, then returns to **hold** until the Operator allows it again: an
authorization to run code is an authorization to run that code.

*Serves:* OC-001(b), OC-008.

---

## 7. Lifecycle

---

#### OP-017 — First activation

First activation runs exactly once, on an empty store: it establishes the
Operator binding, assembles the initial structural state, generates the integrity
baseline, writes the Genesis Anchor, and issues the first session credential.

It SHOULD be atomic with respect to its own outputs — it either completes fully
or reverts every write it made, leaving the store uninitialized. A failed first
activation re-executes at the next start; **a partially-initialized store does not
exist.**

It is irreversible: re-initializing a store creates a new, unrelated entity, with
no chain connecting it to the old one.

*Serves:* OC-004(a).

---

#### OP-018 — Crash recovery

**(a) Detection and re-execution.** A normal close SHOULD remove the session
credential artifact at Sleep completion, so that its presence at start signals a
crash. **The start sequence is itself the recovery procedure; no special mode
exists.**

If the integrity log holds a Sleep completion record, the entity resumes from
that boundary. If not, the pre-commit snapshot is restored, discarding any
partial commit, and Sleep re-executes from the start, from the Closure Payload
held in the session store (OP-009(a)).

A crash before the payload was emitted leaves nothing to consolidate: that
session's progress never reaches the Memory Store, is invisible to recall, and
its session-store residue is removed by garbage collection.

**(b) Attempt threshold.** Consecutive recovery attempts SHOULD be counted in the
integrity log. At a threshold `N_boot` declared in configuration, the passive
signal is written and the entity halts — no further attempts until the Operator
clears the condition.

*Serves:* OC-004(b), OC-001(c), OC-010.

---

#### OP-019 — Start load set and cost

The start SHOULD load a fixed set — integrity artifacts, binding, configuration,
index, validated Resumption Record, unresolved Action Ledger entries, pending
reprocessing stimuli — **and nothing else**. The Memory Store and log history are
read on demand during the session.

**Start cost SHOULD NOT scale with entity age.** This is the property that makes
a long-lived entity practical; it is the first thing to measure in an
implementation that intends entities to live for years, and it is a worthwhile
addition to a conformance suite even though it is not an invariant.

*Serves:* OC-010.

---

#### OP-020 — The session credential

The credential SHOULD be issued when every start gate has passed, and invalidated
at session close, at Operator revocation, or at a halt. Every intent is processed
under a valid credential; invalidation stops intent processing immediately.

The credential artifact **MUST be directly accessible to the Operator with no
active component** — this is what makes OC-002(b) realizable.

A credential artifact found at start that does not match a crash scenario is a
concurrent-session conflict: Critical, the conflicting credential revoked and the
Operator notified before any new one is issued.

*Serves:* OC-002(b), OC-001(a), OC-003(d).

---

#### OP-021 — Session close

**(a) Close modes.** A session ends one of three ways:

- **Normal close** — an Operator signal, a close intent from cognition, or a
  condition declared in configuration (OP-010's thresholds are one such). The
  Closure Payload is emitted and Sleep follows.
- **Critical** — escalation happens before any Sleep may run.
- **Direct intervention** — the Operator removes the credential artifact from the
  store, with no component involved. The entity halts immediately, with no
  Closure Payload and no automatic Sleep.

**(b) Revocation mid-cycle.** On revocation mid-cycle, the active cycle aborts
without commit. Executions in progress are discarded with no result logged or
returned; executions left without a terminal record follow OP-014(b) at the next
start.

*Serves:* OC-002(b), OC-001.

---

#### OP-022 — Sleep

**(a) Stages.** Sleep SHOULD run after every normal close, in three stages, never
concurrently:

1. **consolidation** — the Closure Payload is processed (OP-009);
2. **garbage collection** (OP-009(b));
3. **commit execution** — queued authorized proposals commit through OP-012, or
   the stage is skipped if none are queued.

Semantic drift detection (OP-005) runs in this window. The credential is revoked
before Sleep begins; the artifact is removed only at Sleep completion, serving as
the crash indicator throughout (OP-018(a)).

**(b) Maintenance authority.** During Sleep no intent is generated and no
stimulus is processed: cognition is inactive. Maintenance operations run under
integrity authority, independent of the credential — including maintenance
executions performed under direct integrity instruction.

*Serves:* OC-004(b), OC-005(c), OC-007.

---

#### OP-023 — Decommission

Decommission requires explicit Operator authorization. A final Sleep SHOULD
execute first — consolidating pending mnemonic content and committing queued
authorized proposals — then the credential artifact is removed, the chain is
closed by a final entry recording the decommission, and the store is destroyed or
archived at the Operator's choice.

The orderly path is not the only one: the Operator can always halt the entity
directly (OP-021(a)) and dispose of the store with no component's cooperation.
Under either disposition, OC-002(c) applies — the entity does not operate again.

*Serves:* OC-002(c).

---

## 8. The reference architecture in operation

OBEC-Core §3 describes the four-domain decomposition as RECOMMENDED. This section
records the operation ownership that decomposition implies. It applies only to an
implementation that adopts it.

---

#### OP-024 — Operation ownership

Every operation SHOULD be owned by exactly one part, and a part SHOULD NOT
implement an operation it does not own. The operation set is fixed by the
implementation; skills are the only per-entity extension of capability.

| Part | Owns |
|---|---|
| **CPE** | cognition: turns stimuli into intents. Owns no operation on the store or the host |
| **MIL** | the mnemonic operations — recall, session writes, consolidation, garbage collection — over the Session Store and the Memory Store |
| **EXEC** | the host operations: native primitives and skill execution |
| **SIL** | the integrity operations: store verification, skill admission, the Heartbeat, the commit pipeline, the standing-grant lifecycle, credential issuance and revocation |

The **Orchestrator** and the **Operator Channel** are implementation
infrastructure: they own no operations, hold no authority, and are reachable by
every part.

Two limits are load-bearing and restate core requirements in the decomposition's
vocabulary: the integrity path **records and enforces** Operator authorizations
and never creates, modifies or revokes one (OC-001(b)); and the mnemonic
operations have no write path to structural or integrity content, which binds
their parameters — a request whose target would touch either is rejected whatever
operation carries it (OC-003(c)).

*Serves:* OC-003(c), OC-005, OC-009.

---

## Appendix A — Configuration surface

Every value this document leaves to configuration, in one place. An
implementation SHOULD document its default and its permitted range for each.

| Value | Governs | Clause |
|---|---|---|
| Vital Check interval | time-based heartbeat cadence | OP-003(a) |
| Vital Check activity threshold | activity-based heartbeat cadence | OP-003(a) |
| drift thresholds, per category | detection sensitivity and response | OP-004 |
| `N_ckpt` | commits between chain checkpoints | OP-007(c) |
| log compaction policy | retention of routine operational records | OP-007(b) |
| `N_channel` | live delivery attempts before the passive signal | OP-008(b) |
| retention rules | session-store garbage collection | OP-009(b) |
| pointer-map limit | size of the Resumption Record's working set | OP-009(d) |
| soft / hard context thresholds | session self-close and forced close | OP-010 |
| watchdog deadlines | per-execution timeout | OP-014(a) |
| `N_boot` | consecutive recovery attempts before halt | OP-018(b) |

**No configuration value may relax an invariant** (OBEC-Core §4). In particular,
no setting may skip a start gate, reorder the two constrained gates, or issue a
credential on a failed gate (OC-010).
