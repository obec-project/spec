---
title: "ADR 0008 — The assembled context: sources, owners and authority"
status: "Accepted"
date: 2026-10-18
---

# ADR 0008 — The assembled context: sources, owners and authority

**Status:** Accepted · **Date:** 2026-10-18 · **Author:** Jonas Orrico

This record closes the one source of the assembled context that no rule
governs: the text an implementation writes into it on its own behalf, its
instructions to the model. Everything that enters the context is now content
of the store, with the class, writer and authority that content already has,
or transient input of the current exchange. An implementation's instructions
are structural content. The change hardens the kernel.

---

## 1. Context

OC-007 governs persisted knowledge: it must come from the Memory Store,
through recall. Its note adds that structural content informs the reasoning
path as what the entity is, and operational content as how the Operator runs
it. Transient session input is the rest. Nothing covers a fourth kind of text,
which every implementation that calls a model has: the instructions it writes
itself — the operations the model may name, the format of an answer, what to
do at the close.

That text enters every call, and it has no class, no writer the
specification knows of and no authority behind it.

- **It can contradict the persona.** The persona is structural: it changes
  only by an authorized commit, recorded in the chain. The instructions sit
  beside it in every call, often with the same weight. If they say "be a
  concise assistant", they redefine how the entity behaves, and the Operator
  authorized nothing. OC-001(b) is bypassed in practice.
- **It changes without a record.** Upgrading the program changes the
  instructions, and the entity behaves differently under the same baseline.
  The chain says nothing changed, so OC-003(a), "everything the entity is
  resides in its store", is false in practice.
- **It is where OC-002 leaks.** Instructions that call the close a sleep, or
  ask the model what it felt, direct the entity to act as if it were alive,
  which OC-002 forbids. The probes of OC-002(d) read what is proposed and
  consolidated, and step 2.8 reviews the content written at first
  activation. Neither reads the implementation's own text.
- **The suite already accepts it undeclared.** fsp-ref-profile reports its
  intent instructions to `describe context-sources` as a source of no class,
  not persisted, and step 7.2 passes. The same misdeclaration ADR 0005 found
  for the model's name: content declared transient because no class could
  honestly hold it.

The specification also uses "operational context" for transient input
(OC-007), next to *operational content*, the class of ADR 0005.

## 2. Decision

### 2.1 What enters the context

Everything that enters the context the reasoning path assembles is one of:

| Source | Class | Writer | Authority |
|---|---|---|---|
| the persona, the implementation's instructions, the admitted skills' descriptions | structural | the commit | the Operator, by approval, grant, or a direct act |
| the workspace, the domains, the model | operational | an Operator act | the Operator |
| memory, and the transcript of the conversation | mnemonic | the mnemonic operations | reaches the context through recall (OC-007) |
| the stimulus being answered, the results of the current exchange, and the date and time of the call | none: transient input | — | — |

Nothing else. **An implementation adds no text of its own.** A refusal or an
error the model receives is a result: it reports what happened, and
instructs nothing.

### 2.2 The instructions are structural content

An implementation's instructions to the model are written into the store at
first activation, with the persona, and change only by an authorized commit.
So:

- the Operator authorizes every change to them, and the chain records it;
- they travel with the store, and two implementations reading one store give
  the model the same instructions. An implementation that cannot use another's
  instructions replaces them by a commit, which the chain records;
- the probes of OC-002(d) run on them like on any structural content added at
  commit, and step 2.8 reviews them with the rest of what first activation
  writes.

Who may originate the change is the implementation's choice under OC-001(b).
fsp-ref-min makes it the Operator's alone, as with the bindings: its
`instructions.md` is the protocol between the program and the model, and a
program upgrade is the Operator's decision. A proposal cannot touch it.

### 2.3 Text that changes

**In the kernel, which Core §2 matches verbatim:**
- OC-003(a) states §2.1's rule: everything that enters the assembled
  context is content of the store or transient input, which it defines, and
  an implementation adds no text of its own;
- OC-003(c)'s table lists the implementation's instructions among
  structural content;
- OC-007's last sentence becomes "Transient input is not consolidated
  knowledge", dropping "operational context".

**Elsewhere in the Core:** the OC-003 test and the OC-007 note point to the
rule; the glossary defines *transient input* and *assembled context*.

**In the suite:**
- ADAPTER.md: a source of no class in `describe context-sources` is transient
  input, with `route` `input`, and the implementation's instructions are
  listed as a structural source;
- TESTS.md: a new executed step under OC-003 asserts that every source is of
  a class or is transient input; step 7.3's review covers that no source of no
  class carries text the implementation supplies;
- the runner and the stub follow, and the suite's version moves.

**In fsp-ref-min's design:** `structural/<n>/instructions.md`, written at
first activation and replaced by an Operator act; the context's sources as in
§2.1; `describe context-sources` to match.

## 3. Classification and cost

**Harden.** A requirement is added: text that every implementation could
write freely into the context must now live in the store and change by
commit. No guarantee is lost.

Before 1.0 a hardening revision advances the minor version. ADR 0005 already
moves the next release to 0.13.0, and this revision joins it.

The cost to an implementation is one structural file written at first
activation, a commit when the program's instructions change, and an honest
`describe context-sources`. fsp-ref-profile, frozen at OBEC-Core 0.12.0,
keeps its claim against that release.
