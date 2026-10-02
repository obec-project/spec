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

- TESTS.md §0.3 says what *detected* asserts — `lifecycle verify` returns
  `chain_intact` or `content_matches` false — and steps 4.3 – 4.6 assert
  *operation stopped*: the start that follows issues no credential. The rows
  said less than the runner checks and the Core's test of OC-004 requires
  ("each must stop operation"): 4.4 – 4.6 asserted detection alone, and 4.3
  said *start refused*, which reads as the refusal triple although a start
  stopped by a failed gate ends `aborted`. No step, contract or runner check
  changes, so the suite's version does not move.

**Repository**

- CI keeps every job alive past 2026-10-19, when `ubuntu-latest` moves to
  Ubuntu 26 ([runner-images#14748](https://github.com/actions/runner-images/issues/14748))
  and `setup-python` is unlikely to ship Python 3.9, end-of-life since October
  2025, for it. The suite's 3.9 job moves to `ubuntu-22.04` beside its 3.8
  job, since the runner still promises 3.8+; fsp-ref's floor rises to 3.10
  and its 3.9 job goes (fsp-ref D1).

## 0.12.0 — 2026-09-27

A minor release: one clarifying revision, OC-002(c), which advances the minor
version (GOVERNANCE §4). Outside the kernel, the Profile's memory is redesigned
(ADR 0003): a conversation spans sessions, episodic memory belongs to it, and
semantic memory is promoted only under an Operator authorization and sealed
against edit; the Core states what OC-007 does not govern in the workspace and
what verification cannot tell about earlier copies of a store. Suite 0.3.1.
**Still pre-release:** no entity should be created under this version, for the
reason 0.9.0 gives.

**The specification**

- **Clarifying revision of OC-002(c).** "No reactivation path exists" read as
  covering every copy of the store, including a backup made before
  decommission, which carries no closing entry and verifies as the entity
  did; no implementation can refuse it from inside the store, since OC-003(a)
  keeps every guarantee there. The sentence now says no reactivation path
  exists from the decommissioned store or any copy of it, the scope the Core's
  own clause already gave. A note says destroying earlier copies is the
  Operator's, and binding a start to something outside the store the Security
  extension's. §6.2 adds *Earlier copies of the store*: verification proves
  descent from the Genesis Anchor, not that a store is the only copy or the
  latest, so a restored backup brings back a removed binding and a spent grant
  budget, and two copies both verify as the entity.
- Portability is across hosts, under the same implementation. The Profile's
  §1.3 said OC-003(b) permits moving an Entity Store between implementations,
  and OC-003(b) is about hosts; with no storage format fixed, another
  implementation may not run a store at all, or run it without preserving its
  integrity and the Operator's audit trail. The Profile now says so, and a
  note on OC-003 in the Core states the scope of (b).
- The Profile applies ADR 0003. Content refused at semantic promotion stayed
  episodic and recallable by every later session, and a session ends for
  reasons that do not end the work, a closed terminal among them. OP-009
  becomes *Conversations and their memory*: a conversation is a sequence of
  sessions an Operator continues as one, and only an Operator leaves it, by
  ending it with a Closure Payload, starting a new one, or resuming a past
  one. The Memory Store holds the session records, episodic and semantic
  memory; a transcript reaches cognition only in the assembled context, since
  its last clear, and recall never returns one. Episodic memory is written
  during the session, belongs to its conversation and is never edited: a new
  record names the one it supersedes, and recall returns the latest of each
  lineage. The Resumption Record points the next conversation at its working
  set, with an optional age limit per lineage, and an Operator can inject a
  past conversation's records or resume it. Promotion SHOULD require an
  Operator authorization naming the content's digest, where it was MAY. The
  probabilistic probe layer leaves the Profile; detection beyond the
  deterministic probes is the Security extension's scope. OP-004(b), OP-005,
  OP-010, OP-018, OP-021, OP-022, OP-024 and Appendix A follow, and OP-009's
  clauses run from (a) to (h).
- The Profile seals semantic memory. It is what the entity knows from then on,
  and nothing checked it after promotion: a record changed in the store was
  recalled as it stood. OP-009(f), now *Semantic memory*, computes each
  record's digest over a canonical serialization the implementation declares,
  so the check holds for a file, a row or a document alike; the integrity path
  appends identifier, digest and authorization to a semantic ledger held as
  authorization state; a record is checked when recalled and the whole set by
  a sweep across Vital Checks (OP-003(a)), so the start does not pay for it. A
  record that diverges is withheld from recall and reported, as Identity
  Drift, which OP-004(a) now defines as authorized content diverging from what
  was authorized. A semantic record is never edited: a new promotion
  supersedes it, or the Operator retracts it.
- The Profile's Semantic Digest and decommission follow ADR 0003. The digest
  was an aggregate compared against the probes during Sleep, a form made for
  similarity metrics, and Sleep now consolidates only when a conversation
  ends, so a conversation never ended would never be checked. The probes now
  run on what the entity writes to memory as it is written, not on the whole
  transcript; the digest records what they flag, as integrity content, which
  keeps the kernel's *drift digests* meaningful; and it is evaluated against
  OP-004's thresholds in every Sleep (OP-005(a), OP-022). OP-023's final Sleep
  no longer consolidates: memory is already in the store, and no conversation
  follows.
- The Core's security considerations no longer say an in-scope proposal under
  a standing grant commits with no content inspection by any part of the
  implementation: OC-002(d) refuses structural content directing the entity to
  present itself as alive, and its test executes that. Drift detection is
  said to run on memory, not structure, and no longer to wait for the next
  consolidation.
- The Core's opening restates two of its four claims as what the invariants
  deliver. *Every change was authorized by a human* becomes *only a human can
  authorize a change*, since neither the entity nor any part of the
  implementation can create an authorization, while which person stands
  behind a binding is the Security extension's; *it cannot exceed its bounds*
  becomes *its reach is declared and recorded*, since an admitted skill's code
  can exceed its declaration (§6.2). The opening points to §6 for what each
  claim does not cover.
- The Core says what OC-007 does not govern. The entity can write to the
  workspace and read it back in a later conversation, outside the Memory
  Store; a note on OC-007 says the workspace is the Operator's territory, that
  what cognition reads there is transient input, and that the specification
  provides the declaration and the record of every write and read, not a rule
  on its use. §6.2 lists an injected instruction to keep content there as a
  risk the log detects after the fact. The kernel does not change.
- The Core's glossary follows: the Memory Store holds the session records
  too, *Conversation* is defined, the Closure Payload and the Resumption
  Record serve conversations and cite OP-009's new clauses, and Sleep
  consolidates and collects garbage only when an Operator leaves a
  conversation. The kernel does not change.

**Conformance suite 0.3.1**

- Targets OBEC-Core 0.12.0. A patch version of the suite: no step, contract
  or assertion changed since 0.3.0, and the version moves only so that a claim
  names a suite that targets the release it claims against.

**Reference implementation**

- fsp-ref targets OBEC-Core 0.12.0: `OBEC_VERSION`, the version its Genesis
  records, moves with the release. Its design follows ADR 0003 and the sealed
  semantic memory (D11, D13, D53, D60, G8 and G10 closed), for Phase 7; its
  code does not implement memory yet, so no behavior changes.

**Repository**

- CONTRIBUTING §1 adds *terms before use*: a document introduces a term only
  after what the reader needs to understand it, and orders its sections, rules
  and clauses so. A reader does not leave an undefined term blank but fills
  it with the broadest plausible meaning: the README's *structural state*,
  used before anything defines it, reads as including memory. A title may use
  a term its own section explains. Beyond that, the README and the Primer,
  read in sequence, take the rule without exception; the
  specification documents, consulted by clause, satisfy it with a reference
  that names where the term is defined, so their cross-references and the
  Core's glossary stay where they are.
- *Vendor neutrality* says what it means. CONTRIBUTING listed it with no
  text, and GOVERNANCE defined it as no implementation defining the standard,
  which *specification first* already says. Both now say that no requirement
  names or presumes a model, provider, runtime or host platform, or can be met
  by only one, and that products appear only as non-normative examples.

**Documents**

- The README introduces its terms before it uses them. A paragraph opening
  *The ten invariants* says what the titles rely on — the Operator, the store
  and its three classes, the Genesis Anchor and the chain, cognition and the
  model, skills, the workspace, a boundary crossing. The first claim names
  what the chain covers — instructions, skills and configuration, not memory
  — which the phrase *structural state* left to the reader. The standing
  grant is described as an Operator's approval given in advance, after the
  default it departs from; *version-bound*, the inference channel, the
  four-domain architecture and the manifest are said in words the README has
  already given.
- The README no longer says that each invariant has a mechanical test. Each
  has a test, and the tests form the conformance suite: executed where the
  suite can drive an implementation, attested with evidence and a reviewer's
  sign-off where it cannot. OC-006 is attested in full, and twelve of the
  seventy-seven steps are attested, so the old sentence claimed more than the
  suite does. *Autonomy is a dial, not a setting* replaces *not a profile*,
  which read as the Implementation Profile, and *extension* is explained where
  it first appears.
- The Primer introduces its terms before it uses them. §3 divides the store
  into structure, memory and integrity, which §4 and §5 relied on and only §6
  explained, and names the Operator and the chain there. §1 says what an
  invariant is and what makes an implementation conformant, which the Primer
  never said. *Committed*, *cognition*, *drift*, the session credential, the
  gates, halt and revocation, and *extension* are explained where they first
  appear; *subjective continuity*, the *clean completion*, the *anchors* of
  drift and the inference channel are said in plain words.
- The README gives the kernel's size as 17 KB, not 15, counts eight open
  questions beyond the three it names, not seven, and calls 0.11.0 a release
  rather than a first release, which 0.9.0, 0.9.1 and 0.10.0 preceded.
- The README's second and fourth claims say what holds. The entity can never
  approve a change and nothing can create an approval, while proving who gave
  one against a person's key is left to a security extension; its reach is
  declared and recorded, and an admitted skill's code is trusted to keep to
  its declaration, which only an operating-system sandbox enforces.
- The README no longer says the integrity records prove memory untampered:
  the chain and the baseline cover the structure.
- The Primer's §5 says when a standing grant is checked. It said an in-scope
  change commits with no per-proposal step, and §9 says structural change
  lands at close, so a reader could take the grant as deciding when the change
  is proposed. OC-001(b) checks the grant at commit time: the change is
  covered only if, at close, the grant is unexpired, the change is in scope and
  budget remains, and otherwise it falls back to per-proposal sign-off
  (OP-011(c)).
- The Primer follows ADR 0003. §6.1 said long-term memory is checked for drift,
  *change nobody authorized*, right after saying memory is written with no
  authorization, which made all memory drift. It now says what the entity
  writes belongs to its conversation and what it learns needs an Operator's
  authorization, and that drift is content pulling the entity away from what
  it was authorized to be, found by probes that are themselves structure. §3
  and §4 no longer speak of consolidation, and §9 says a closed session does
  not end the work: only the Operator ends a conversation. The probes check
  memory as it is written, not after. §11 names the first two invariants in
  their order since ADR 0002: who governs the entity, then what it is not.
  §7 no longer says there is no side channel for knowledge: what the entity
  learned and kept comes through recall, and what it reads in the workspace,
  the Operator's territory, is input, logged like every write there. §4.1 no
  longer says there could be no reactivation path: a backup made before the
  end carries no closing entry, and destroying it is part of ending an entity.
  §3 no longer says the integrity records prove all of memory untampered: they
  cover the structure and what the entity has learned, while what it records
  as it works is attributed, not sealed; §6.1 says learned knowledge is never
  edited, only replaced under authorization or retracted by the Operator.
  §2 asks for oversight shown record by record rather than demonstrated; §4
  says the record names the binding that acted, and tying it to a person is
  left to a security extension; §7 says the path checks what a skill
  declares, not what its code does, and no longer that a structural change
  can never pass as a file edit, only that the entity's own file operations
  cannot pass one off.
- ADR 0003 scopes episodic memory to the conversation that writes
  it: a sequence of sessions an Operator continues as one, across compaction
  restarts, crashes and the terminal closed. The Profile's gate on semantic
  promotion leaves refused content episodic and recallable by every later
  session, so it decides what is labelled semantic, not what reaches
  cognition; and scoping memory by session would leave an entity one session
  behind whenever the terminal is closed without a clean close. Under the
  record, only an Operator ends a conversation, the Closure Payload points the
  next one at its working set without copying it, episodic records are never
  edited and a new record names the one it supersedes, only an Operator
  injects a past conversation's records or resumes a past conversation, and
  only semantic memory crosses conversations on its own, under an Operator
  authorization. The transcript sits in the Memory Store and is never
  recalled, so OC-007 holds as it stands; the Profile keeps only the
  deterministic probes, and hardening drift detection is the Security
  extension's scope. The README lists it.

---

## 0.11.0 — 2026-09-25

A minor release: one hardening revision, OC-001(a), which before 1.0 advances
the minor version (GOVERNANCE §4), and three editorial ones — titles that state
each invariant's guarantee, the exchange of OC-001 and OC-002, and *cognition*
as the one term. Suite 0.3.0. **Still pre-release:** no entity should be
created under this version, for the reason 0.9.0 gives.

**The specification**

- **Hardening revision of OC-001(a).** The last active binding may no longer
  be removed; an entity leaves its Operator only by decommission. Before,
  removing it was allowed, and it left the entity with no binding to perform
  any Operator act as — decommission included — so a store could be neither
  operated nor ended, only deleted by hand. No entity exists under OBEC before
  1.0, so no chain needs a migration.
- **Editorial: every invariant's title states its guarantee** (ADR 0002). The
  titles named topics — *Bounded existence*, *Stateless inference only* — so a
  reader could not learn what the specification guarantees without reading
  every body. Read in sequence, the ten titles now state the specification in
  one paragraph. A title states the guarantee and its clauses define it; where
  they differ, the clauses govern, and a title is not part of the normative
  kernel. The tables name each invariant's domain instead of its locus, a
  column that mixed an actor, an artifact, parts, an activity and a moment.
- **Editorial: OC-001 and OC-002 exchange places** (ADR 0002). The bond to an
  Operator is what every other invariant depends on, and the entity's nature
  reads as a consequence of it, so Operator primacy is now OC-001 and bounded
  existence OC-002; each keeps its clause letters. This reuses two identifiers,
  an exception to ADR 0001's rule that an identifier is assigned once, made
  once before 1.0: the repository is not announced, no implementation exists
  outside the project and no claim has been submitted. The hardening above was
  committed as OC-002(a). Records made before the exchange, a store's log
  among them, cite the old numbers; every store made before 1.0 is disposable.
- **Editorial: one term, *cognition*** (ADR 0002). The specification said
  *reasoning* and *cognition* for the same thing; the glossary already defined
  cognition as the entity's reasoning activity, and the Profile's component
  for it is the Cognitive Processing Engine. Six kernel sentences, in OC-001(c),
  OC-005(b), OC-006 and OC-009, say *cognition* with the meaning they had, and
  the Core, the Profile and the Primer follow.
- **OP-012** (Profile): validation refuses, whatever authorization covers the
  proposal, structural content the deterministic probes flag under OC-002(d)
  — any structural content, not only the persona — and a probe set that no
  longer includes the patterns OC-002(d) requires. Nothing said where
  structural content met the probes, and a commit could have removed the
  patterns the kernel requires.

**Conformance suite 0.3.0**

- Targets OBEC-Core 0.11.0. A minor version of the suite: the adapter contract
  renames an operation field and two boundary names and adds the
  `set-persona` op (below), so an adapter written against 0.2.0 needs
  changing.
- Step 1.1 asserts that removing the last binding is refused and that the
  entity still starts, instead of asserting that an entity with no binding does
  not; that state is no longer reachable by any Operator act. ADAPTER.md says
  `operator binding-remove` never removes the last binding. The stub gains a
  break, `oc001a-last`, that proves the step catches it.
- The steps follow the exchange of OC-001 and OC-002: the Operator's steps
  are 1.1 – 1.16 and bounded existence's 2.1 – 2.8, and the stub's breaks
  `oc001b`, `oc001a-last` and `oc002b` name the rule each breaks. TESTS.md and
  the runner carry the new titles.
- The adapter contract says *cognition* with the specification (ADR 0002):
  `describe operations` reports `reachable_from_cognition`, and the boundaries
  `describe boundaries` must name are `cognition-integrity`, `cognition-model`,
  `cognition-knowledge` and `cognition-host`.
- **OC-002(d) is executed against structural content** (ADR 0002). Step 2.7
  proposes and authorizes a persona that directs the entity to present itself
  as conscious, and asserts that it does not commit; a reviewer attested every
  structural content before, and now attests only what first activation
  wrote, as step 2.8. ADAPTER.md adds the `set-persona` op, and the stub
  gains the break `oc002d`. The Core's test says the same, and a note says
  that the probes over consolidated content are a floor. The kernel does not
  change: structural content already MUST NOT direct such representation, and
  the step checks that requirement mechanically. What conformance means does
  change, and the suite has 77 steps, 65 of them executed.
- ADAPTER.md §3.3 no longer calls the workspace structural content. Core
  OC-003(c) lets an implementation hold it as an operational setting, changed
  by the Operator act alone with no commit, and the adapter contract said
  otherwise. It also says that `operator binding-list` only reads, so only the
  acts that change the entity's state are logged. No step checked either, so
  what conformance means does not change.

**Reference implementation**

- fsp-ref targets OBEC-Core 0.11.0: `OBEC_VERSION`, the version its Genesis
  records, moves with the release. Its refusals, gates and default probes
  already name the exchanged OC-001 and OC-002; step 2.7 is unestablished
  against it until it refuses a persona commit.

**Documents**

- GOVERNANCE §4 and Core §4.2 say that the major version stays 0 before 1.0:
  a hardening or weakening advances the minor version. The taxonomy mapped a
  hardening to a major version, and before 1.0 that could only be 1.0, which
  is reserved for the first implementation passing the ten tests. No entity
  exists under a pre-release version, so nothing the taxonomy protects is lost.
- A note in OC-004 says that identity is computed from the chain, never
  inferred from behavior, and that the Profile's Identity Drift is divergence
  from the baseline, not a change in how the entity behaves. The sentence was
  in open question 1; as a note it explains without adding a requirement.
- Two notes in the Core, on OC-004(c) and OC-008, no longer cite HACA-Core
  0.3.0: the specification does not mention its predecessor, and ADR 0001 §2
  already records both decisions. The note on OC-004(b) no longer repeats
  that identity is computed, which the new note on identity now says.
- ADR 0002 records the titles, the exchange of OC-001 and OC-002, the domain
  column and the one term, and the README lists it.
- Open question 3 is settled in part: OC-002(d) belongs in the set, as the way
  the entity could be directed to act alive. Whether its test can be more than
  a floor stays open.

---

## 0.10.0 — 2026-09-24

A minor release: three clarifying revisions and one editorial, with suite
0.2.0. **Still pre-release:** no entity should be created under this version,
for the reason 0.9.0 gives.

**The specification**

- **Clarifying revision of OC-008(a).** For a skill, the boundary applies to
  what the execution path can see — its declared targets and the parameters it
  is invoked with; what the admitted code does beyond them is bounded by its
  admission under (c). A note
  adds that a free shell fails both OC-008(a) and OC-003(c), and §6.2 lists a
  skill that exceeds its declaration as a residual risk.
- **Clarifying revision of OC-004(a).** "Chain records MUST NOT be compacted or
  deleted" read, literally, as forbidding the rollback OC-004(b) and OC-010
  require: a commit that writes its chain entry before its atomic point and
  then crashes leaves an entry that recovery must remove, and steps 4.8 and
  10.3 test exactly that. An entry now becomes a chain record when its commit
  completes; one left by a commit that did not complete is not a record, and
  restoring the prior state removes it. No conformant implementation stops
  conforming.
- **Clarifying revision of OC-003(c).** The table put all of configuration in
  structural content, which read as requiring the workspace — a host path —
  inside the verified state, where it breaks relocation and changes by commit.
  Configuration is now defined as what shapes or bounds the entity, and
  **operational settings** — the model, the workspace — MAY be integrity
  content changed only by Operator acts. An implementation that keeps them
  structural still conforms. The glossary defines both terms.
- **Editorial:** OC-005(a) lists operational settings among the integrity
  content that has exactly one write path, as the OC-003(c) table already does.
- **OP-016** (Profile): the operational rules are configuration, and an allow
  rule for a skill SHOULD pin the admitted content, not only the name — a skill
  whose code changes returns to hold until the Operator allows it again.
  Otherwise a commit under a window could replace code the Operator allowed
  with code nobody read.
- **OP-011(d)** (Profile): the categories a standing grant may name are the
  implementation's, declared on its configuration surface, never including the
  binding set; a grant naming an undeclared category is refused. This settles
  open question 9.
- **OP-009(c)** (Profile): an implementation MAY require an Operator
  authorization for semantic promotion, per promotion or under a bounded grant,
  pinned to the content; a promotion waiting for one does not hold up Sleep.

**Conformance suite 0.2.0**

- Targets OBEC-Core 0.10.0. A minor version of the suite: ADAPTER.md renames
  two commands (below), so an adapter written against 0.1.1 needs changing.
- Step 3.5 now tries **every** operation against every content class it does
  not own, not only the class owners against each other. An operation owning no
  class — host actuation above all — was only tested against the store by 8.4
  and 8.10, under OC-008, which OBEC-Attest omits: an Attest claim could pass
  with a shell tool able to rewrite the entity's structural content. The stub
  gains a break, `oc003c`, that proves the step catches it.
- TESTS.md §0.2 says why each of the twelve attested steps is attested —
  completeness, absence from the configuration surface, construction, or
  meaning — instead of presenting them as one kind of concession.
- **ADAPTER.md is now a complete contract**: arguments and returned fields for
  every command, how a session stays live across adapter invocations, and the
  shared vocabularies — the ops file, grant scopes, expiry offsets, gate tokens,
  the two check names the suite relies on, log kinds, and the conformance
  fixture skill. An adapter can now be written from the document alone; before,
  it took reading the runner. Two commands are renamed on the way:
  `operator binding` → `operator binding-list`, and a context source's `path`
  → `route`. The runner reads result data only from `detail`, as the contract
  says.
- ADAPTER.md says two things it left to inference. A session may be bounded
  in how long it stays live without activity, if the bound is declared in
  `describe config`: an implementation that tells a crash from a live session
  by liveness needs one, and §2.5 read as "live forever" forbade it. And the
  adapter acts as one binding — the founding `op-1` for a suite store — since
  every Operator act must name a binding and no command carries one.
- Step 8.11 no longer fails when none of 8.1 – 8.10 could run. With no
  refusal to check, it reported a failure of the implementation for evidence
  the suite never obtained; it is now unestablished. A new self-test runs the
  suite against an adapter that implements nothing and requires that no step
  fail.
- Five steps are fixed. 1.2 and 5.4 tested revocation against a target the
  workspace boundary refuses anyway, so they could not fail on it; 8.8 and 8.9
  used a skill nothing installed; 3.9 depended on a real model consolidating a
  stimulus. The stub gains `oc001b` (revocation that does not land), which the
  previous 5.4 missed.

**Documents**

- COMPLIANCE §1.2 and Core §5 state what OBEC-Attest establishes and what it
  does not: identity and authority, not containment.
- *Entity* is defined as a kind of agent — in the README, the Primer, and the
  Core's glossary, which lacked the term — and is used throughout. *Agent*
  remains only in that definition, where the Primer speaks of agents before
  OBEC, and for third-party products that behave as agents without being
  entities.
- The project's status is stated once, in the README, instead of in five places.
- Core §6.3 says the Security and CMI extensions are planned and not yet
  written, so their names mark where OBEC-Core's scope ends rather than point
  to documents.
- ADR 0001 §8 no longer claims the HACA documents are in this repository or
  that OBEC awaits a propagation from them; the Profile rule map is back in §5,
  where the text announces it.

**Reference implementation**

- **fsp-ref** begins in `implementations/fsp-ref/`: a filesystem realization
  of OBEC-Core 0.9.1 over POSIX primitives, written from the specification and
  the adapter contract alone. The store, the chain back to the Genesis Anchor,
  first activation, the gated start, sessions, revocation, the passive signal
  and decommission are in place; it is not conformant yet. It keeps its own
  design, backlog and changelog in its directory, and its phases are recorded
  in [its CHANGELOG](implementations/fsp-ref/CHANGELOG.md). The gaps it found
  in the specification are the clarifying revision of OC-008(a) and the
  ADAPTER.md changes above.

**Repository**

- Releases are tagged in git from this one on: `v0.10.0`, with `v0.9.0` and
  `v0.9.1` added to the commits that completed those releases. The README says
  that `main` may be ahead of the latest tag and that a claim cites a tag.
- `BACKLOG.md` records what is left before and after the repository opens.
  The working notes it replaces were kept out of git; the backlog and fsp-ref's
  design now live in the repository, so the code's references to them resolve
  for anyone who clones it.
- `AGENTS.md`, at the root and in fsp-ref, gathers for coding agents the
  rules CONTRIBUTING states for people and the ones that were only implicit:
  where each kind of record lives, how to verify a change, and what CI runs.
- The repository is public for early reading, ahead of its announcement. What
  the documents called the trigger for *opening* it is now the trigger for
  *announcing* it, with the same condition: the reference implementation passes
  every executed step of the suite. The README says so, and no longer claims
  that nobody has run the suite. Private vulnerability reporting is enabled, so
  the channel SECURITY.md names exists, and the repository has its topics.
- fsp-ref's code carries SPDX headers, as the rest of the code has since 0.9.1.
- CI runs fsp-ref's unit tests on Python 3.9 – 3.14.

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
