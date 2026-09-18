# Contributing to OBEC

OBEC is a vendor-neutral specification. Contributions are welcome, and must
follow the processes here so that architectural coherence and specification
integrity survive them.

Read [GOVERNANCE.md](GOVERNANCE.md) before proposing a normative change.

---

## 1. Guiding principles

- **Specification first.** The normative text is authoritative. Reference
  implementations do not define the standard, and behavior is never defined by
  pointing at code.
- **The invariant set is closed.** Ten invariants, no more, and nothing may
  weaken one. Adding to the set, removing from it, or rewording it is a major
  version (Core §4).
- **Minimalism.** Every rule that survived the restructure survived two filters:
  *can it be given a mechanical test?* and *could a configuration plausibly relax
  it?* A proposed rule that fails either belongs in the Profile or nowhere.
- **Self-containment.** A normative requirement is stated in the specification
  text, not imported from another document.
- **Vendor neutrality.**

---

## 2. Which document are you changing

The three specification documents have different revision costs. Know which one
you are touching before you open a pull request.

| Document | Contains | Revision cost |
|---|---|---|
| [`spec/obec-kernel.md`](spec/obec-kernel.md) | the MUST and MUST NOT sentences | **version-bound** — changing a sentence here is a revision of the specification |
| [`spec/obec-core.md`](spec/obec-core.md) | the same rules with tests, rationale, notes, glossary | apparatus — revised freely, except where the change alters a kernel sentence |
| [`spec/obec-profile.md`](spec/obec-profile.md) | operational machinery, as SHOULD | apparatus — revised freely |

The kernel is a **verbatim extract** of the Core's §2. A change to a normative
sentence must land in both, identically, in the same commit. Where they differ,
§2 governs and the kernel is in error.

---

## 3. Classifying a change

Every change to the normative kernel is exactly one of four kinds, defined in
[Core §4.2](spec/obec-core.md#42-revision-and-continuity). **The classification
is not a formality — it determines whether existing entities survive the
change.**

| Kind | What changes | Version | Continuity |
|---|---|---|---|
| **editorial** | wording, formatting, cross-references; nothing required changes | patch | preserved |
| **clarify** | an ambiguity resolved in the direction already implied; every conformant implementation stays conformant | minor | preserved |
| **harden** | a permission narrows, a requirement is added, an invariant joins the set | **major** | preserved by migration (HC-004(c)) |
| **weaken** | a guarantee no longer holds | **major** | **broken** |

A **weaken** pull request severs the chain of every existing entity. It requires
explicit approval by the Specification Owner, a migration note, and a statement
of what is lost. It is the one change this project makes expensive on purpose.

Changes outside the kernel — tests, notes, the Profile, the conformance suite,
tooling — carry none of these consequences and use the non-normative types below.

---

## 4. Commit convention

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 4.1 Type

Normative types are the four revision kinds of §3, so that the commit log is the
record the version rule is enforced against:

| Type | Use |
|---|---|
| `editorial` | kernel wording; nothing required changes |
| `clarify` | a kernel ambiguity resolved in the direction already implied |
| `harden` | a kernel permission narrows or a requirement is added |
| `weaken` | a kernel guarantee is removed or relaxed |

Non-normative types:

| Type | Use |
|---|---|
| `init` | the repository's first commit. Used once, and it describes what the initial state contains rather than what preceded it — provenance belongs in `design/`, not in the log |
| `test` | conformance tests, the adapter contract, the runner |
| `profile` | the Implementation Profile |
| `design` | architecture decision records |
| `docs` | README, governance, contributing, changelog |
| `impl` | reference implementation code |
| `ietf` | Internet-Draft generation |
| `chore` | repository plumbing, tooling, CI |

### 4.2 Scope

The narrowest thing the change touches — a rule identifier when there is one:

```
HC-004   OP-012   kernel   core   profile   suite   adapter   readme
```

### 4.3 Subject

Imperative mood, no trailing period, lower case after the colon, ≤ 72
characters. Say what the change does, not what it is about.

### 4.4 Body

Wrapped at 72 characters. Required for every normative type, and it must state:

1. **Rationale** — why the change is correct, not merely what it does.
2. **Continuity impact** — one of `preserved`, `preserved by migration`, or
   `broken`, matching the type.
3. **Affected rules** — every identifier touched, including clauses.

Optional for non-normative types, but write one when the subject line does not
carry the reasoning.

### 4.5 Footer

`Refs:` / `Closes:` for issues, `RFC:` for an accepted RFC.

**No attribution trailers.** Commits carry no `Co-Authored-By`, no
"generated with" lines, and no tool or assistant footers of any kind. The commit
log records who authored normative change and is read as a governance artifact;
machine trailers pollute it.

### 4.6 Examples

```
harden(HC-003): require key material to survive relocation

An extension hardening key management could bind it to a TPM or a
platform keystore, satisfying its own goal while silently destroying
portability. Nothing in the previous text prevented it. HC-003(b) now
names host-resident key material explicitly, and the extension contract
in §4 requires hardening to stay within it.

Continuity impact: preserved by migration. An entity whose key material
already travels with the store passes the new test unchanged; one whose
does not must be migrated before its version-transition entry commits.

Affected rules: HC-003(b), §4 extension contract.
```

```
editorial(kernel): say "specification" where the text meant the whole spec

"this document" became ambiguous once the specification was split across
three files. Three normative sentences in §2 said "document" where the
guarantee belongs to the specification as a whole.

Continuity impact: preserved. No requirement changes.

Affected rules: HC-003(a), HC-003(b), HC-009.
```

```
test(adapter): define the command contract for driving an implementation

Storage formats and operation sets are implementation-defined, so the
suite cannot inspect internals. It drives an adapter that speaks OBEC
vocabulary and runs with Operator authority, outside the entity's
operation set.
```

```
docs(readme): lead with the four claims instead of the architecture
```

---

## 5. Pull requests

Every pull request MUST:

- state which of the four kinds it is, or that it is non-normative;
- describe the purpose of the change;
- update the kernel and the Core together when a normative sentence moves;
- update [CHANGELOG.md](CHANGELOG.md) under the correct kind.

A normative pull request MUST additionally include rationale, a continuity impact
statement, and security considerations where they apply.

A pull request that changes an invariant's requirement MUST update that
invariant's conformance test in the same change. A guarantee whose test did not
move is a guarantee nobody can check.

---

## 6. Proposing a new invariant

The set is closed at ten. Adding to it is a **harden** change requiring a major
version, and the proposal must show:

1. **A failure the existing ten permit.** Concretely: inputs, state, and the
   outcome no current invariant forbids.
2. **A mechanical test.** Executable against an adapter, or attestable with
   evidence. A property that cannot be tested is not an invariant here.
3. **That configuration could plausibly relax it.** This is the filter that
   separates an invariant from a Profile rule. A rule nobody would ever think to
   switch off does not need invariant status.
4. **That it names no component.** Invariants constrain authority boundaries,
   never structure — that is what lets an existing runtime claim conformance
   without being rewritten.

Most proposals that pass 1 and 2 fail 3, and belong in the Profile.

---

## 7. RFC process

Significant architectural changes SHOULD begin as an RFC in `ietf/` or as an ADR
in `design/`, depending on whether the audience is external or the project
itself. An RFC must include problem statement, proposed specification text,
continuity analysis, and security considerations.

Acceptance requires explicit approval by the Specification Owner.

---

## 8. Extensions

An extension MUST declare the OBEC-Core version it targets, add capability or
harden a rule but never weaken one, class every artifact it adds within
HC-003(c), and define its own conformance requirements on top of the ten.

An extension that hardens key management MUST do so within HC-003(b).

---

## 9. Conformance changes

A change affecting what conformance means MUST update the affected test and the
suite version. The suite versions independently of the specification
([Core §4.1](spec/obec-core.md#41-what-is-version-bound)); a claim names both.

A system must be able to determine objectively whether it conforms. Any change
that makes conformance a matter of interpretation is out of scope for this
project.

---

## 10. Licensing

By contributing you agree your contributions may be redistributed under the
licenses in [LICENSE](LICENSE). Disclose any known patent or licensing
restriction affecting a contribution.

---

## 11. Final authority

The normative specification text is the final authority. Where contributors
disagree, the Specification Owner decides, subject to
[GOVERNANCE.md](GOVERNANCE.md).
