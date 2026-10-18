---
title: "ADR 0007 — The entity is cognitive; the part is the reasoning path"
status: "Accepted"
date: 2026-10-18
---

# ADR 0007 — The entity is cognitive; the part is the reasoning path

**Status:** Accepted · **Date:** 2026-10-18 · **Author:** Jonas Orrico

This record ends the use of *cognition* at two scales. *Cognitive* describes
the entity as a whole. The part that turns a context into an intent, which
the specification called *cognition*, becomes the **reasoning path**, and the
model is its engine. The kernel changes editorially, and the adapter
contract changes with it, so the suite's version moves.

---

## 1. Context

### 1.1 Two scales

**The narrow sense is the one the invariants rely on.** *Cognition* is the
part that turns a context into an intent, with the model as its engine:

- "the model is cognition's stateless engine" (OC-006);
- "no cognitive operation may reach integrity state" (OC-005(b));
- the four boundaries of OC-009, each between cognition and something else;
- the Cognitive Processing Engine of Core §3, "cognition: turns stimuli into
  intents";
- the README: "**Cognition** is the part that reasons".

**The broad sense appears where the entity is described whole.** Core §1
specifies "an **auditable cognitive entity**", and the planned extension is the
*Cognitive Mesh Interface*, a mesh of entities, not of parts.

The two senses produce a misreading. OC-005 and the suite depend on cognition
being one **part**: the untrusted one, whose output is routed and checked
before anything is done. A reader who takes §1's broad sense reads "no
operation reachable from cognition writes integrity content" as "no operation
reachable from the entity", and the sentence loses its meaning.

### 1.2 What the word means outside OBEC

In cognitive psychology, cognition is the umbrella for every process of
knowing: perception, attention, memory, language and learning, and also
reasoning, problem solving and decision making. The narrow sense names only
the last three. The others are spread across the entity:

| Function | Where it is in OBEC |
|---|---|
| perception | the stimulus and the assembly of the context |
| memory, learning | the memory path: recall and consolidation |
| attention | the context budget and recall |
| language | the model |
| **reasoning, decision** | **the part called cognition**: the model turns a context into one intent |
| action | the host: native operations and skills |

The specification named the whole by one of its parts. "The model reasons,
and the entity is cognitive" describes the architecture as the field would.

## 2. Decision

### 2.1 Two words, two scales

- **Cognitive** describes the entity as a whole. Core §1's "auditable
  cognitive entity" and the *Cognitive Mesh Interface* keep the word, now in
  its only sense.
- **The reasoning path** is the part that turns an assembled context into one
  intent. The model is its stateless engine.

*Reasoning* alone reads as a process, while the kernel's sentences treat the
part as an actor: "Cognition MAY read it", "Cognition MUST reach the model".
The part is therefore a **path**, beside the memory path and the integrity
path the Profile already names. Where a sentence speaks of the process rather
than the part, *reasoning* is enough.

The word *cognition* is no longer used for a part. *Cognitive cycle* becomes
*cycle*.

### 2.2 Names that follow

| Was | Becomes |
|---|---|
| *cognition*, the part | *the reasoning path* |
| *cognitive operation*, an operation reachable from cognition | in OC-005(b), "nothing the reasoning path does"; elsewhere, an operation reachable from the reasoning path |
| *Cognitive Processing Engine (CPE)*, Core §3 | **Reasoning Interface Layer (RIL)**, beside the Memory Interface Layer |
| *cognitive cycle* | *cycle* |
| OC-006's category, *cognition* | *reasoning* |
| `reachable_from_cognition`, in `describe operations` | `reachable_from_reasoning` |
| boundaries `cognition-integrity`, `cognition-model`, `cognition-knowledge`, `cognition-host` | `reasoning-integrity`, `reasoning-model`, `reasoning-knowledge`, `reasoning-host` |

OC-006's title becomes "The model is the reasoning path's stateless engine,
and it only answers".

### 2.3 Text that changes

- **The kernel**, and Core §2 verbatim in the same commit: OC-001(c),
  OC-003(c), OC-005, OC-006, OC-007 and OC-009, and the table of the ten.
- **The rest of the Core:** §1, §3 with its table of parts, §4, §5, §6, the
  Appendix and the glossary, where *Cognition* gives way to *Reasoning path*
  and *Cognitive cycle* to *Cycle*.
- **The Profile**, the **Primer** and the **README**.
- **The suite:** ADAPTER.md, TESTS.md, the runner and the stub take the new
  field and boundary names, and the suite's version moves.
- **fsp-ref-min's design:** the CPE becomes the RIL.

Unchanged: fsp-ref-profile, frozen at OBEC-Core 0.12.0, whose adapter keeps
the old names and whose claim stands against the suite of that release; and
the entries already in the CHANGELOG.

## 3. Classification and cost

The kernel's sentences rename a term without changing what any of them
requires: an **editorial** revision, which advances the patch version. The
adapter contract changes what the suite reads, a change to what conformance
means, so the suite's version moves in the same release.

The cost is about fourteen occurrences in the kernel, fifty in the Core,
thirty-eight in the Profile, five in the Primer and seven in the README, and
the adapter's field and four boundary names across the contract, the runner
and the stub. Paying it before 1.0 renames the part before the identifiers
freeze, and before fsp-ref-min's adapter reports the old field names: its
first phase answers `describe operations`.
