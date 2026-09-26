---
title: "OBEC Primer"
short_title: "OBEC-Primer"
version: "0.11.0"
status: "Non-normative — explanatory"
date: 2026-09-25
companion_to: "OBEC-Core 0.11.0"
---

# OBEC Primer

Plain language, no requirements. This document explains what OBEC is for and how
its pieces fit. **Nothing here is normative** — where it and
[obec-core.md](obec-core.md) differ, the Core governs, and this page is wrong.

Read this first if OBEC is new to you. Skip it entirely if you are implementing:
the Core is self-contained.

---

## 1. The problem

A language model is stateless. Between one inference call and the next it holds
nothing: not what it decided, not what it learned, not who it was talking to.
Everything that looks like continuity is supplied from outside — a transcript
replayed, a database queried, a file re-read.

That is not a flaw to be fixed. It is the shape of the thing. But it has a
consequence that most systems built on models never confront:

> If the model holds nothing, then an agent's identity is not in the model. It is
> in whatever state you keep outside it. So the question *"is this the same agent
> as yesterday?"* is a question about that state — and it has a mechanical
> answer, if you build for one.

Most systems cannot answer it. They can tell you the prompt is the same file, and
that a memory database exists. They cannot tell you whether anything changed the
instructions three weeks ago, who authorized it, or whether the system changed
them itself.

OBEC is a specification for systems that can answer it. It calls an agent built
this way an **entity** — not a rival word for *agent*, but the kind of agent
whose identity, authority and boundaries can be checked rather than believed.

---

## 2. Is this for you?

OBEC costs something. It is worth knowing early whether what you are building
needs it.

**You probably want OBEC if:**

- it will run for months or years and accumulate state that matters;
- someone will eventually ask *who authorized this* about something it did,
  and you want a better answer than log grep;
- it can change its own configuration, skills or instructions, and the
  boundary on that needs to be more than a code review;
- it must survive a model swap, a host migration, or a vendor change without
  becoming, in any sense that matters, something else;
- a regulator, auditor or customer will ask you to demonstrate human oversight
  rather than describe it.

**You probably do not want OBEC if:**

- it is stateless between sessions by design;
- it is a single-task tool with no capacity to modify itself;
- nobody will ever need to audit what it became and why.

There is no shame in the second list. Most agents are in it.

---

## 3. The store is the entity

An entity under OBEC has two parts with different lifetimes.

**The Entity Store** is everything it persistently *is*: its instructions, its
memory, its installed skills, its configuration, who its Operator is, and the
integrity records that prove all of the above hasn't been tampered with. The
store is self-contained and host-agnostic — nothing about the entity lives
outside it, and nothing inside it depends on the machine it happens to be on.

**The running instance** is that store loaded, verified, and connected to a model
for one session. It is local and temporary. It can crash, its host can burn
down, the model behind it can be replaced by a different vendor's. None of that
touches the entity, because none of the entity is in it.

Every guarantee in OBEC is a property of the store, or of the procedures that
read and write it. That is why the specification can promise things about
identity: **identity claims reduce to claims about a file tree you can copy,
move, hash and audit.**

One consequence worth stating early: you can put the store on a USB stick, carry
it to a different machine on a different continent, and every verification
returns exactly what it returned before. If that is not true of an
implementation, it is not conformant — this is the cheapest thing to test and the
first thing an evaluator checks.

---

## 4. Who governs

Every entity is bound to at least one **Operator** — a human with final
authority. The binding is established when the entity is first activated,
recorded in the store, and checked at every start. **Without an active Operator
binding, the entity does not run.** There is no unbound mode.

Operator authority has three faces, and it is only real when all three hold.

**The Operator exists.** Not as a configuration value, but as a recorded,
verified binding. Every act the Operator takes is logged and attributed to the
specific binding that took it — so "who held authority when this happened" is
answerable years later.

**The Operator authorizes.** Nothing about what the entity *is* changes without a
human act. And the direction is one-way, with the entity no exception to it:

> The entity can propose changing itself. It can never approve one.

That is the whole of it. An entity can notice it needs a new skill, draft the
change, and say so. The change is inert until a human authorizes it. There is no
operation anywhere in the system by which the entity authorizes its own
structural change, and no configuration that adds one.

**The Operator is reachable.** This is the face people forget. Authority that
cannot be informed is authority in name only. So OBEC requires a path to the
Operator that **does not pass through the entity's cognition** — because
cognition is the part most likely to be compromised, and a component that can
suppress the report of its own compromise is not being watched.

That path includes a **passive signal**: a plain record written into the store,
readable with nothing running, that stops the entity from starting until a human
clears it. It survives restarts. It does not need the network. It does not need
the entity's cooperation.

### 4.1 Not alive

Alongside authority sits a limit, and OBEC states it right after authority,
because authority over something that can perpetuate itself is authority without
teeth:

- **No self-perpetuation.** There is no operation by which the entity sustains,
  replicates, or re-activates itself without a human act.
- **No obstruction.** There is no operation by which any part of the system
  blocks, delays, or conditions an Operator act. Halt, revocation and
  decommission each work through a path that needs nothing running and nobody's
  cooperation. In practice: the Operator can delete one file and the entity
  stops, mid-thought, with no component consulted.
- **Terminal end.** Decommissioning is final. A destroyed store leaves no chain,
  so nothing can claim continuity with it. An archived store is a record, not a
  dormant entity — it carries its own closing entry, and starting it would mean
  operating past that entry, which the chain forbids. There is no reactivation
  path, because there could not be one.
- **Not a subject.** The entity's instructions may not direct it to present
  itself as conscious or as having subjective continuity, and the drift checks
  actively look for such language in what it consolidates.

---

## 5. Autonomy is a dial

Here is the mechanism that does the most work in practice.

The default is per-proposal sign-off: the entity proposes, a human reviews that
specific proposal, and only then does it commit. Strict, and often too slow.

The alternative is a **standing grant** — authorization the Operator opens in
advance, bounded on three axes at once:

| Bound | Meaning |
|---|---|
| **expiry** | a time after which it is dead |
| **commit budget** | a count of changes it will cover, then it is spent |
| **declared scope** | the categories of change it covers, and no others |

While the grant is open, a change inside its scope commits with no per-proposal
step — logged under the grant's identity, so the audit trail records which
authority covered it. A change outside its scope is **never** covered: it waits
for explicit review like anything else.

When the grant expires or its budget runs out, the entity reverts to
per-proposal sign-off **automatically**, with nothing to switch off and no
component to remember.

The range this covers is the whole range:

- Never open a grant, and every change requires explicit human approval forever.
  Zero standing autonomy, no extra mechanism needed — you just don't open one.
- Open a narrow one — one hour, three commits, "skill installation only" — and
  the entity works within a budget you set, and the budget closes itself.
- Open a broad one and accept the corresponding risk, knowing it is bounded in
  time and count regardless.

Governance frameworks describe "human oversight" in prose. This is the
mechanism, and it is a dial rather than a switch.

---

## 6. Identity you can compute

Three pieces make identity verifiable rather than asserted.

**The Genesis Anchor** is a cryptographic record of the entity's complete
structural state at the moment it was first activated, including who activated
it and which version of OBEC it was activated under. It is written once and never
modified.

**The integrity chain** is an append-only sequence with one entry per authorized
change. Each entry points at its predecessor, records the resulting state, and
carries the authorization that permitted the change.

**Verification** is two mechanical checks: the current content matches the
chain's latest entry, and the chain is unbroken all the way back to the Genesis
Anchor. An entity that fails either cannot claim to be the entity that was
activated, and must stop.

Nothing here infers identity from behavior. The entity does not have to *act*
like itself. Identity is computed from the store, which is why it survives the
model being replaced: a new model changes the quality of the thinking, not the
identity of the thinker.

### 6.1 Why the chain stays small

The store admits two kinds of write, and the distinction is the reason any of
this is auditable.

**Memory** is written freely during normal operation. No per-write
authorization, no chain entry. An entity that remembered nothing without a
signature would be useless.

**Structure** — instructions, skills, configuration, Operator bindings — changes
only through an atomic, authorized commit that appends a chain entry.

So the chain does not record everything the entity did. It records every change
to **what the entity is**. That is what keeps it small enough to actually read,
and it is why "show me every structural change in this entity's life and who
authorized each one" is a question with a short answer.

Memory is not ungoverned, though. It shapes behavior, and behavior is part of
what an entity is — so long-term memory is built through a controlled
consolidation step at session close, and its content is checked for drift against
anchors set at first activation.

---

## 7. Where it acts, what it knows

Three boundaries confine the entity, and each is a single path.

**The host.** Everything the entity does beyond its own store happens inside a
**workspace** — host territory the Operator explicitly declared. Declared, never
inferred: a directory the Operator didn't name is out of reach even if the
operating system would happily allow it. The workspace and the Entity Store are
necessarily disjoint, which is what stops a structural change from ever passing
as an ordinary file edit.

**Skills.** Beyond a fixed set of primitives, capability is extended by
installing a **skill** — a packaged operation with a manifest declaring what it
needs. A skill runs only if it is in the verified index built at start *and* its
manifest still validates at the moment it runs. Installing one is a structural
change, so it needs a human authorization like any other.

**Knowledge.** Everything persisted that informs the entity's thinking comes
through one recall path from its memory store. There is no side channel — no way
for knowledge to enter without passing the place where it can be audited and
checked for drift.

And one more boundary, inward: the model is reached only as a **stateless
inference call**. Context in, one completion out. No tool authority travels with
the call, and nothing acts on the result until it comes back and is routed to
whatever owns the operation it names. If you reach the model through a
third-party product that has agent behavior of its own, verifying that it doesn't
exercise authority you didn't grant is your standing responsibility — the
specification requires the clean completion but cannot check the far side of an
API for you.

---

## 8. When something breaks

The system checks itself on a cadence while running: hashes still match, health
signals still in bounds. A check resolves one of three ways.

**Nominal** — carry on.

**Degraded** — a local anomaly that can be verified from outside the affected
part. The part corrects itself; the verifier re-checks **externally**. That
external re-check is the point: a component's own report that it fixed itself is
not evidence.

**Critical** — beyond correction, or involving cognition or the
verifier itself. The session credential is revoked immediately and the Operator
is told.

A crash is not a failure of this kind. An interrupted session leaves evidence in
the store, the next start notices it, and recovery is just the normal start
sequence — there is no special repair mode, because a special mode is a second
code path that can be wrong in its own way.

And who verifies the verifier? Everyone, by construction. The health checks run
on a declared cadence and leave a record each time, so a newest record older than
that cadence is mechanical evidence that the verifier itself has stopped —
evidence any part can read, and report through the Operator path directly.

### 8.1 Starting is the choke point

Every start is a gated sequence, and nothing gets a session credential until
every gate has passed: passive signal clear, crash recovered, structure verified
against the chain, Operator binding valid, authorization state loaded, skills
indexed.

**A failed gate stops the start. There is no degraded mode, and no setting that
skips one.** That last part matters more than it sounds: the guarantee isn't
"don't skip gates", it's "there exists no way to". A system that shipped a
`fast_start` flag would fail this even with the flag defaulted off.

The whole architecture works to keep an entity from degrading. Starting is where
that effort would be wasted if a degraded entity could simply boot anyway.

---

## 9. A life

**First activation** happens once. The Operator binding is established, the
initial structure assembled, the Genesis Anchor written. Everything verifiable
about the entity dates from this moment. It is atomic — it completes or it leaves
nothing behind, so a half-initialized entity does not exist.

**Start** runs the gates and issues a credential, or refuses.

**A session** is the life of that credential. Work happens: thinking, recalling,
acting in the workspace, running skills. The Operator's direct input takes
precedence over whatever is in flight — it never cuts a thought in half, but it
is the next thing the entity sees.

**Close** consolidates the session's memory into long-term memory, writes what
the next session needs to continue, collects garbage, and commits any authorized
structural changes. **Structural change lands here, at close — never mid-session.**

**Decommission** is the explicit end, and an Operator act like any other. A final
close, then the chain is sealed with a closing entry and the store is destroyed
or archived, at the Operator's choice.

Start, session, close repeat for the entity's whole life. Each leaves evidence:
every start records its verification result, every close records its
consolidation and its commits.

---

## 10. What OBEC does not do

**It is not an architecture.** OBEC describes a reference decomposition — four
domains for integrity, cognition, memory and host — and marks it RECOMMENDED. No
requirement names a component. This is deliberate: it means an existing runtime
can become conformant by satisfying the boundaries, without being rewritten
around someone else's structure.

**It does not specify cognition.** How the entity thinks, what algorithms it
uses, how it structures a prompt — all implementation-defined. OBEC constrains
what reaches the thinking and what the thinking reaches, and says nothing about
the thinking.

**It does not solve prompt injection.** A crafted input can produce requests that
are structurally valid and semantically hostile. The checks verify an operation's
identity, its authorization and its manifest — **they do not inspect the
arguments, and they do not judge intent.** A legitimate skill invoked with
adversarial arguments passes every gate OBEC defines. What OBEC bounds is the
blast radius and the evidence trail. Argument validation is the skill's job, and
sandboxing is the host's.

**It assumes a cooperative host.** The host may crash, lose data, and corrupt
things by accident; verification detects that. A host actively working against
you is a different problem, addressed by a separate Security extension. Detection
is not prevention, and it does not survive someone deleting the store — backups
outside the host's reach are your mitigation there.

**It does not define formats.** Storage layout, wire protocols, how the inference
channel is realized: all yours.

---

## 11. Where to go next

| If you are… | Read |
|---|---|
| implementing | [obec-core.md](obec-core.md) — self-contained, with a test per invariant. Then [obec-profile.md](obec-profile.md) for the machinery you'll otherwise have to rediscover. |
| reviewing or evaluating | [obec-kernel.md](obec-kernel.md) — the whole normative requirement, ten invariants, fifteen minutes. |
| assessing conformance | [COMPLIANCE.md](../COMPLIANCE.md), then [conformance/TESTS.md](../conformance/TESTS.md). |
| asking why it is shaped this way | [design/0001](../design/0001-obec-restructure.md). |

One orientation note for the Core: its ten invariants are ordered as an argument,
not by importance. The first two say what the entity is not and who governs it;
the next three say what it is and how that is verified; the next four bound what
reaches it and what it reaches; the last governs the transition into operation.
Reading them in order is the shortest path to the whole design.
