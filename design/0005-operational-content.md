---
title: "ADR 0005 — Operational content, a fourth class"
status: "Accepted"
date: 2026-10-17
---

# ADR 0005 — Operational content, a fourth class

**Status:** Accepted · **Date:** 2026-10-17 · **Author:** Jonas Orrico

This record adds a fourth content class to OC-003(c). **Operational** content
is how the Operator runs the entity: the workspace it acts in, the rules over
what it may do there, the model it runs on, and its operating limits. Only an Operator act writes it, cognition
may read it, and the chain does not verify it. Integrity content keeps only
what proves and guards the entity. The change hardens the kernel.

---

## 1. Context

OC-003(c) divides the store into three classes. Operational settings had no
class of their own. Configuration was structural, and a paragraph allowed
operational settings — "such as the model it uses or the workspace it acts
in" — to be held as integrity content instead, changed only by an Operator
act. That paragraph came with the 0.11.0 clarification: as structural content,
the workspace was a host path inside the verified state, and it changed by
commit. Each place it allowed has a defect.

- **As integrity content, cognition cannot see it.** OC-005(b) says no
  cognitive operation may reach integrity state, and step 7.2 of the suite
  fails any persisted source in assembled context whose class is not
  structural or mnemonic. Yet an entity has to know its workspace to name a
  file in it, and it is reasonable for it to know which model it runs on.
  The reference implementation puts the model's name in the context and, to
  pass 7.2, declares that source transient and of no class, which it is not.
  The specification induced the misdeclaration: there was no honest way to
  give cognition a setting held where the Operator was told to hold it.
- **As structural content, it changes by commit.** A commit can be covered
  by a standing grant, so a grant scoped broadly enough would let a commit
  the Operator never saw move the workspace. OC-008(a) wants the boundary
  declared by the Operator, not authorized in advance. Every change of host
  folder would also become a chain entry. That is noise in the record of
  who the entity is, about where it happened to run. The Profile already has
  the same defect elsewhere. OP-016 makes the Operator's allow, deny and hold
  rules configuration, so the entity can propose "allow this domain", a
  grant over `configuration` can cover the proposal, and the boundary widens
  on the entity's initiative without the Operator seeing it.
- **The integrity class lost its definition.** Integrity content is what
  proves and guards the entity: the Genesis Anchor, the chain, the log, the
  credential, the authorization state. OC-005(a) had to list "operational
  settings where held there" among them. That qualifier shows the seam: the
  Operator's running choices are neither proof nor guard.

Keeping settings outside the store is not open either. OC-003(a) forbids a
guarantee depending on state outside the store, and OC-008's boundary depends
on the workspace.

## 2. Decision

### 2.1 Four classes

| Class | Content | Write path |
|---|---|---|
| **structural** | persona, skills, configuration, Operator bindings | the authorized atomic commit of OC-001(b) and OC-004(b) — and no other |
| **mnemonic** | session records, consolidated memory | the mnemonic operations — and no other |
| **integrity** | Genesis Anchor, baseline, log, credential, authorization state, drift digests | the single path of OC-005(a) — and no other |
| **operational** | the workspace of OC-008(a), the Operator's operational rules, the model, operating limits | an Operator act — and no other |

### 2.2 What makes content operational

Operational content is what the Operator **declares directly** about running
the entity: where it may act, what engine it runs on, and how far it may go
in one operation. It follows from that definition:

- **Only an Operator act writes it.** The act is logged and attributed to its
  binding, as every Operator act is (OC-001(a)). No proposal may originate a
  change to it, and no standing grant may cover one.
- **The chain does not verify it.** It is not who the entity is. A commit
  never carries it, and no verification depends on it, so it can name host
  locations without breaking portability (OC-003(b)).
- **Cognition may read it.** It informs cognition as the frame the Operator
  set, the way the persona informs it as what the entity is. It is not
  knowledge, and OC-007 does not govern it. No operation reachable from
  cognition writes it, which OC-003(c) already ensures: an operation never
  writes outside its own class.

**The Operator's operational rules are operational content.** Allow, deny and
hold over host operations say where and how the entity may act, as the
workspace does, and only the Operator sets them. The same holds for a
decision that answers a hold. When the Operator places a held target inside
the boundary — for the held act, for the session, or as a standing setting
(OP-016) — that decision is operational content with that scope, and it
lapses when the scope ends.

**Lifetime does not decide the class; the writer does.** Every class has
transient content. The credential is integrity content and lasts one
session. The session's records are mnemonic and are never consolidated
unless the entity saves from them. A permission for one act is operational
and lasts one act. Content the implementation writes on its own behalf, such
as the credential, a persisted Skill Index or the state of a check, is never
operational, however short it lives. Putting it there would give the class a
second writer.

**Configuration** keeps a narrower meaning: structural content that shapes
what the entity is, such as its probes and the parameters of its memory.
Setting it apart from operational content takes one question: is this a
change to the entity, which the Operator authorizes, or a change to how the
Operator runs it, which the Operator makes? The first is a commit; the
second is an act.

### 2.3 Text that changes

**In the kernel, which Core §2 matches verbatim:**
- OC-003(a) lists four classes;
- OC-003(c) takes the four-row table and a paragraph stating §2.2's rules,
  replacing the paragraph that let operational settings be integrity
  content;
- OC-005(a) drops "operational settings where held there".

**Elsewhere in the Core:**
- the OC-003 test enumerates four classes;
- the OC-007 note on structural content gains a sentence for operational
  content;
- the glossary replaces *Operational settings* with *Operational content*,
  and its class entries say "one of the four content classes".

**In the suite:**
- steps 3.4 to 3.6 cover four classes;
- step 7.2 accepts `operational` as a persisted source's class, with no
  recall route required;
- ADAPTER.md adds `operational` to the class vocabulary of `describe state`
  and `describe context-sources`, and §3.3 says the workspace is operational
  content, changed by the Operator act alone;
- the stub gains an operational write path;
- the suite's version moves.

**In the Profile:**
- OP-016 says the operational rules are operational content, and stops
  saying that the workspace declaration may be configuration;
- the `configuration` category of OP-011(d) no longer covers the rules, so
  no standing grant reaches them;
- the glossary's *Configuration* drops "its operational rules".

**In ADR 0004:** §2.3 gave "allowing a domain" as an example of an Operator's
own structural act, committed in an Endure. That example is superseded:
allowing a domain is an Operator act on operational content, effective at
once, with no proposal and no commit. The Endure Protocol itself does not
change.

## 3. Classification and cost

**Harden.** The revision adds a requirement: what used to be an
implementation's choice, structural or integrity, is now a class with one
write path, the Operator act. A commit under a grant no longer reaches the
workspace or the Operator's rules. No guarantee is lost:

- the properties integrity gave these settings are restated for the new
  class: a single writer, no write from cognition, nothing verified depending
  on them;
- reading by cognition is new only for an implementation that held them as
  integrity. One that held them as structural content already let cognition
  read them. "Cognition never reads its settings" was never a guarantee of
  the specification.

Before 1.0 a hardening revision advances the minor version, so the next
release is 0.13.0. An existing entity migrates by moving its settings to the
new class under a version-transition entry (OC-004(c)). Before 1.0 there is
no real entity to migrate.

The reference implementation frozen as fsp-ref-profile keeps its claim
against 0.12.0 until it is revised. fsp-ref-min is designed on this
revision.
