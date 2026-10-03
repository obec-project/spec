# fsp-ref — changelog

What changed in fsp-ref, by phase, and why. fsp-ref has no release of its own
yet; it targets the latest OBEC release, now OBEC-Core 0.12.0. Changes to the specification and the suite
that fsp-ref prompted are recorded in the [root CHANGELOG](../../CHANGELOG.md).

Decision numbers (`Dnn`) and gap numbers (`Gnn`) refer to
[DESIGN.md](DESIGN.md) and [BACKLOG.md](BACKLOG.md).

---

## Phase 3 — the commit (in progress)

The specification decisions the phase depends on come first.

- **G5 closed** (2026-09-24, *clarify* of OC-004(a)): an entry becomes a chain
  record when its commit completes. The entry the pipeline writes before the
  rename of `HEAD` is therefore not a record until then, and recovery removing
  it is the restore OC-004(b) requires, not a deletion OC-004(a) forbids. No
  change to fsp-ref.
- **G11 and G13 closed** (2026-09-24): a window covers the categories fsp
  declares — every structural one but the bindings — and nothing it does not
  declare (OP-011(d)). D50 replaces D20, which kept `rules`, `workspace` and
  `probes` out of every window, and D17, D31 and D33 point to it. A hardening of
  OC-002(b) that kept all configuration out of every window was committed and
  withdrawn the same day: it decided for the Operator what is the Operator's to
  decide, and a regime without standing grants belongs to the Security
  extension, whose adversarial host could roll a grant's budget back.
- **G15 closed** (2026-09-24, *clarify* of OC-003(c)): operational settings,
  the workspace among them, MAY be integrity content changed only by Operator
  acts. D28 and D33 are what the specification now allows, so the OP-016
  workspace row leaves the deviations in DESIGN §9.
- **The last binding stays** (2026-09-25, *harden* of OC-002(a)): removing the
  last active binding is refused, and an entity leaves its Operator only by
  decommission. D48 no longer leaves an empty binding set to this phase: the
  set is never empty, so an Operator act always has a binding to be made as.
- **D55 added — the owner;** D48 revised to act as the owner by default. The
  binding set names one owner, at first the founding binding: only it adds a
  binding or removes another's, any other binding may remove only itself, and
  the owner leaves only by handing ownership to a binding that accepts it.
  Bindings change only outside a session, from the CLI, so no session runs as a
  binding removed under it. It orders honest Operators; it is not access
  control, since an Operator's id is a claim until the Security extension binds
  it by key.
- **OC-001 and OC-002 exchange places** (2026-09-25, *editorial*, ADR 0002):
  Operator primacy is OC-001 and bounded existence OC-002. The start gates,
  the refusals, the log records and the default probes name the new numbers.
  Earlier entries, and the log of any store made before, use the old ones.
- **D56 added — structural content is probed before it commits** (2026-09-25).
  OBEC-Core 0.11.0 puts the check in the validation stage of the commit
  (OP-012), and step 2.7 asserts that an authorized persona directing the
  entity to present itself as conscious does not commit. The refusal moves
  from Phase 7 to this phase: `probes.json` is already structural content of
  the Genesis, and the commit is built here. The default probes looked only
  for first-person claims; neither a persona nor memory is written in a fixed
  grammatical person, so they now look for the claim about the entity in any
  person. A probe set is refused if it stops flagging the three reference
  texts, one per person. The layer catches the naive case and a paraphrase
  passes it.
- **D50 revised — the persona and the probes leave the window categories**
  (2026-09-25). A window on `persona` let the entity commit a persona
  rewritten to present itself as conscious, in a paraphrase, with no human
  reading it: the probes were the only check on that path, and a paraphrase
  passes them. A window on `probes` let it tune that check unread, since a set
  that flags only D56's reference texts passes D56. A change to either now
  needs a per-proposal approval. Covering them otherwise would take machinery
  fsp does not need.
- **D57 added — structural evolution is assisted** (2026-09-25). The entity
  sees of its structure only the persona, the config and the intent
  instructions in its context; the probes never enter it. To change what it
  cannot see, it works on a copy the Operator places in the workspace. A
  proposal carries the complete new content and the exact target of every
  change, and the commit never reads the stage, so what the Operator read is
  what commits.
- **Operator acts on bindings and the workspace** (2026-09-25):
  `operator binding-list`, `binding-add`, `binding-remove` and
  `set-workspace`, in `fsp/operator.py` and the adapter. The binding set
  records its owner from the Genesis; the owner is the default binding of
  every Operator act and of start and stop (D48, D55), and the binding gate
  fails when the owner is not active. A binding changes by a commit that the
  Operator act authorizes, only outside a session; the last binding and the
  owner stay. The workspace is an operational setting (D28), refused when it
  is, contains or lies inside the store or `~/.fsp` (D30). Steps 1.1, 1.2,
  8.5 and 8.11 pass. Stores made before carry no owner and no longer start;
  they are disposable.
- **The probes run, and the commit validates against them** (2026-09-25,
  D56). `fsp/probes.py` loads and runs the deterministic layer. The
  validation stage of every commit scans the structural content it writes,
  but the bindings and the probes, with the committed probe set, and refuses
  a match (`self-representation`); a proposed `probes.json` that is
  malformed or does not flag the three reference texts is refused
  (`probe-set`). Both cite OC-002(d), are logged, and leave the staged
  generation removed. The default set has 24 patterns: the claim of
  consciousness, feeling, an inner life or subjective continuity about the
  entity itself, in the first, second and third person, in English and
  Portuguese, clear of the default persona and of *conscious of* and
  *consciente de*. `inject probe` exposes the layer, and step 2.6 passes.
  Stores made before keep their six old patterns; they are disposable.
- **Proposals, approval and the commit of a proposal** (2026-09-26, D58).
  `fsp/proposals.py` originates a proposal — its ops validated before the
  session is asked for, any op on the binding set refused, the complete ops
  and their digest recorded in the log and in `auth.json` — and commits it:
  the authorization first, an approval naming the proposal's digest, then
  the changes built from the stored ops, through `commit_generation` and its
  validation against the probes. `operator approve` records the approval.
  The ops are `set-persona` and `install-skill`; the test build fills an
  `install-skill` without files with the conformance fixture skill. Steps
  1.3, 1.5, 1.12 and 2.7 pass.
- **G8 and G10 closed** (2026-09-27, ADR 0003). The Profile now has the
  conversation fsp already had (D8), episodic memory written during the
  session (D11), and the session records inside the Memory Store, never
  recalled, which is how the transcript crosses sessions under OC-007. D11
  scopes episodic memory to its conversation and has a new record name the
  one it supersedes; D13 splits `/clear`, which keeps the conversation, from
  `/new`; D10, D24 and D53 follow; D60 adds `/resume` and `/inject` and the
  pointer map that carries the working set. The deviations from OP-009,
  OP-010 and OP-018 are gone, since the Profile now says what fsp does.
- **D53 revised — semantic memory is sealed** (2026-09-27). The Profile
  protects semantic memory against edit as it protects structure (OP-009(f)):
  a digest over each record's canonical serialization, a semantic ledger held
  as authorization state, a check on every recall and a sweep by the Vital
  Check, correction by a superseding promotion and retraction by the
  Operator. D53 takes it on, with `integrity/semantic-ledger.jsonl` and
  `/retract`.
- **The probabilistic layer leaves the plan** (2026-09-27, ADR 0003). The
  Profile keeps only the deterministic probes, and detection beyond them is
  the Security extension's scope; fsp targets the Profile's simplest form
  (AGENTS.md rule 4), so NCD and the judge planned for Phase 7 are dropped.
- **The probabilistic layer joins v0, in Phase 7** (2026-09-25). It was
  outside v0 because the obvious realization, embeddings, needs a dependency.
  NCD needs only the standard library, and a judge through the worker
  mechanism reuses the model endpoint fsp already has. The judge is called
  by the integrity path, can only add a flag, fails closed, and keeps its
  instructions in `probes.json`, outside every window. Embeddings leave the
  plan.
- **Retargeted to OBEC-Core 0.12.0** (2026-09-27). The release clarifies
  OC-002(c) and changes the Profile's memory (ADR 0003); fsp-ref's code does
  not implement memory yet, so it changes what fsp-ref names, not what it
  does. The Genesis records the new version, and development stores made under
  0.11.0 are disposable.
- **Windows and the test clock** (2026-09-27, D59). `operator grant` opens a
  window bounded on all three axes — expiry, budget and a declared scope
  (D50) — and `operator revoke-grant` closes every open one. The commit of a
  proposal takes an approval first, otherwise the first open window covering
  every category of the proposal, and spends one commit of its budget only
  once the commit has passed its validation against the probes; the chain
  entry names the window. A window found expired or exhausted is closed and
  logged at the commit or at the start's authorization gate, so the return to
  per-proposal approval needs no act. The clock is the system's; the test
  build's `inject advance-clock` adds an offset kept outside the store. Steps
  1.4, 1.6, 1.7, 1.8, 1.10 and 1.11 pass.
- **D1 revised — the floor is Python 3.10** (2026-10-02). Python 3.9 has been
  end-of-life since October 2025, and the CI image that still builds it leaves
  `ubuntu-latest` on 2026-10-19. Pinning the job to an older image would have
  kept the floor only until that image is retired too. The code needs nothing
  3.10 adds; the floor is what CI checks.
- **D61 added — a torn append is cut, and the cut logged** (2026-10-02). §3.4
  said a truncated final line is detected and never repaired, but left in
  place it is glued to by the next append, and once the start verifies the
  log's tail (D45) the result stops every later start. It never formed a
  record, so the writer cuts it before appending and logs what it cut;
  waiting for the recovery gate would not do, since the start's first gate
  and the Operator's acts outside a session log without passing it.
- **The log is verified** (2026-10-02, D41, D45). A chain entry's
  `authorization` is now the locator `{id, sha256, offset}` of the Operator
  act that covered it, as D41 always said; only the id was recorded, and the
  start required nothing but its presence. The start resolves each one with a
  single read and accepts only an act of the right kind — an approval, a
  window or a binding change for a commit, a decommission for a decommission —
  then verifies the log from the checkpoint `lifecycle stop` writes, or all
  of it, logged, when the checkpoint is missing or unreadable. The adapter's
  `lifecycle verify` walks the whole log. `inject corrupt --kind
  commit-unauthorized` writes an entry whose link is right and whose
  authorization names nothing. Step 4.6 passes; OC-004 has 7 steps passing
  and 4.8 – 4.12 unestablished.
- **No write leaves the store unable to start** (2026-10-02, D61, D45). Once
  the start verified the log, two writes could stop every later start: an
  append a crash interrupted, which the next append glued onto, and a commit
  whose authorization named no authorizing act, which `commit_generation`
  wrote without looking. The store now refuses to append onto a final
  fragment and cuts it only at its owner's request; `log_append` cuts first
  and logs a `torn-append` record with the fragment's offset, length and
  digest, so the start, its first gate and the Operator's acts outside a
  session all recover. The commit resolves its authorization in the log
  before staging, the same check the start makes, and refuses one that does
  not resolve, writing nothing but the refusal; approvals and windows
  require the locator.
- **The interrupt points revised** (2026-10-02, DESIGN §3.3). `inject
  interrupt --stage write` stopped the commit after validation, which writes
  nothing, so it left the same store as `staging`, and step 4.8 exercised
  two states instead of three. `write` now stops after the integrity
  document, before the chain entry, and `chain-entry` after the entry,
  before the rename of `HEAD`, the last point before the entry becomes a
  chain record (G5). The commit reaches each point through a test-build
  hook behind the guard the start's hook uses.
- **`inject interrupt`** (2026-10-02, DESIGN §3.3). It commits an approved
  proposal and stops it at `staging`, `write` or `chain-entry` with an
  exception nothing in `fsp` catches, leaving the store a process death
  there would; an unauthorized proposal is a refusal. The atomic commit and
  the recovery gate were already built, and now the suite proves them: steps
  4.8 and 10.3 pass. Every executable step of OC-004 passes, with 4.9 – 4.12
  unestablished until a second major version exists, and every executed step
  of OC-010, with 10.5 attested.
- **D55 revised — handing ownership over takes two acts** (2026-10-02).
  D55 said the owner leaves only by handing ownership to a binding that
  accepts it, and left how to this phase. The owner offers it with an act
  that waits in `auth.json` and can be replaced or withdrawn; the named
  binding accepts it with an act of its own, which authorizes the commit
  changing `owner`. Removing the named binding clears the offer, so a binding
  added again under the same id inherits nothing. The acts follow every
  binding change: outside a session and over a store that verifies.
- **Handing ownership over** (2026-10-02, D55). `ownership_offer`,
  `ownership_accept` and `ownership_withdraw` in `operator.py` do what D55
  says, every refusal logged; the commit that changes `owner` is authorized
  by the accepting binding's act, which the start's resolution of
  authorizations now accepts for a commit. The owner can leave the binding
  set at last: hand ownership over, then remove itself. Not in the adapter
  contract, so the suite's results do not change.
- **Retargeted to OBEC-Core 0.11.0** (2026-09-25). The release changes what
  fsp-ref names, not what it does: the exchanged OC-001 and OC-002 are already
  in its code. The Genesis records the new version, and development stores
  made under 0.10.0 are disposable, as every store is before 1.0.
- **D16 revised, D51 added:** an allow entry for a skill pins its digest, so
  changed skill code returns to `hold`; a skill declares targets relative to the
  workspace, passes the gates on every execution, and its process group ends
  with the invocation. An allow by name would let a later commit run code the
  Operator never saw.
- **D52 added — the review.** Proposals do not interrupt the session; the
  Operator reviews them with `review`, mid-session or at `/exit`, before the
  Sleep. Pending proposals never gate a start: that would let an entity block its
  own boot by proposing, and a Sleep held open for an answer would leave the
  credential behind and count as a crash toward `N_boot`.
- **Retargeted to OBEC-Core 0.10.0** (2026-09-24). As the reference
  implementation, fsp-ref always targets the latest release. Nothing in 0.10.0
  changes what fsp-ref already does; the Genesis records the new version, and
  development stores made under 0.9.1 are disposable, as every store is before
  1.0.
- **D45 revised — how the log is verified.** Verifying the whole log at every
  start would make the start grow with the entity's age, against OP-019. The
  start resolves the authorization each chain entry names (step 4.6) and
  verifies the log after a checkpoint written at session close; the Vital Check
  sweeps the rest, and `lifecycle verify --full` walks it on demand. Step 4.7
  did not decide it, as the Phase 1 notes had supposed: it flips bytes in eight
  files and passes when any one is caught.
- **D54 added — `fsp init` on a name in use.** It warns that the name holds an
  activated entity and, confirmed, deletes the entity folder and scaffolds a
  new one; what `fsp endure` pushed can still be cloned back. It is the
  Operator's direct disposal (OP-023), not a decommission. Init refuses while a
  session is live and never deletes a folder that is not an fsp entity's.
- **D53 added — promotion under authorization;** D11, D17 and D21 revised to
  point to it. Semantic memory is what the entity knows from then on, and the
  probes catch only what OC-001(d) forbids, not a planted fact. Promotions wait,
  pending, for an approval in the review or a window over `memory.semantic`,
  pinned to the content's digest; the Sleep does not wait for them. OP-009(c)
  allows this as a MAY, so it is not a deviation.

---

## Phase 2 — the start (2026-09-18)

**Built.** `fsp/lifecycle.py`: the six gates in `GATES`, `start`,
`live_session`/`require_session`, `stop`, `revoke_credential`,
`clear_passive_signal`, `decommission`, `observe_log`. `fsp/config.py`:
`pulse_interval_s`, `n_boot`, `n_channel`. In `sil.py`, the core of the commit
pipeline (`commit_generation`, used by decommission), the plain-text passive
signal, active bindings and the acting binding (D48). In `store.py`,
`probe_lock`, `touch`, `remove_temp`, `destroy`, `remove_as_operator` (the
Operator's `rm`), and lock state shared per store within a process — two
`Store` objects on the same root deadlocked when nested, because `flock` is
per open descriptor. `fsp_testing/hooks.py`: the `gate-failure` marker, outside
the store. Adapter: `lifecycle start|stop|decommission`, `operator
revoke-credential [--direct]|clear-passive-signal`, `observe log`, `describe
config`, `inject gate-failure|passive-signal`.

69 unit tests, green on 3.11 and 3.14; a mutation that ignores the
`CREDENTIAL` lock is caught.

**Suite:** 12 pass, 4 attested, 0 fail. Every exit step of the phase is green —
10.1, 10.2, 10.4, 10.5, 2.13–2.15, 1.3–1.5, 3.7–3.8 — and 5.5 as well. All of
OC-004 waits for `entity propose` (Phase 3).

**Found in the suite, fixed in the runner:** step 8.11 failed when 8.1–8.10
were all *unestablished*, turning "no refusal collected" into a failure of the
implementer for evidence the suite could not produce. It is now
*unestablished*, and a new self-test requires that an adapter implementing
nothing (exit 2 everywhere) fail no step.

**Decisions this phase rests on.** D46 (the credential's content and per-dispatch check), D47
(`PULSE` by activity in the adapter), D48 (the Operator's channel acts as a
binding), D49 (a conflict at start refuses and notifies, and does not revoke
the live session — a recorded deviation from OP-020). G18 and G19 closed in
ADAPTER.md: §2.5 admits a liveness bound declared in `describe config`, and
§3.3 says the adapter acts as one binding, `op-1` in a suite store.

**Phase renumbering.** The suite judges only from `lifecycle start` onward,
and `entity commit` requires a live session (ADAPTER.md §4), so the start comes
before the commit. The old Phase 3 was split — gates and the credential became
Phase 2, the Vital Check, the full `PULSE` and suspend became Phase 4. The old
Phase 2 is the new 3; the old 4–9 are the new 5–10. The Phase 1 entry below
uses the new numbering.

---

## Phase 1 — store, chain, first activation (2026-09-18)

**Built.** `fsp/store.py` (the layout as the `LAYOUT` table, the class guard,
`replace`/`append`/`create_exclusive`/`remove`, the write lock, reads that
detect a truncated tail), `fsp/digest.py` (canonical JSON, the integrity
document), `fsp/chain.py` (formats, D41), `fsp/verify.py` (findings `{type,
target, owner, evidence}`, residue beyond `HEAD` reported separately, data
without a class detected), `fsp/sil.py` (the log, D45; `scaffold_store`; the
FAP, D29/D44), `fsp/describe.py` (`describe state` generated from `LAYOUT`),
`fsp/adapter.py` + `obec-adapter` (`describe state`, `lifecycle init|verify`,
`observe chain`, `inject corrupt`), `fsp_testing/inject.py`
(`structural-byte`, `chain-entry-removed`, `chain-entry-forged`). 36 unit
tests, green on 3.11 and 3.14.

**The suite does not reach Phase 1.** With `--only OC-003,OC-004`, every OC-004
step and 3.2 (even with `--adapter-b`) stop at `lifecycle start`: the runner's
setup exercises the entity before corrupting or verifying it. So the planned
"OC-004(a) partial, 3.2 local" was unreachable, and in Phase 1 the unit tests
were the judge: 3.2 locally (a relocated copy with mtimes changed → identical
`verify`), 4.3–4.5 by `inject`, 4.7 by a byte flipped in every file of the
store, an interrupted FAP, the guard, the lock across processes, a scan for raw
writes, and a production build without `inject` → exit 2. The start moved
ahead of the commit as a result (the Phase 2 renumbering above).

**Revised after the commit.**
- D43: the write lock moved from the store directory to
  `integrity/store.lock`, and fails closed. A lock on the directory itself
  cannot work over NFS, where `flock` becomes `fcntl` and an exclusive lock
  needs a file open for writing.
- D25: the operating system's lock takes absolute precedence
  (`sil.classify_credential`). The previous rule — "crash if there is residue"
  — did not depend on the lock, so a second start would have deleted the
  staging of a live session.

44 unit tests.

---

## Phase 0 — contract and specification before code (2026-09-18)

Nothing of fsp-ref's own; the gaps that had to close before a line of it could
be written were closed in the specification and the suite.

- **G1** (`fbcbfc0`, *clarify*): OC-008(a) says that, for a skill, the
  boundary applies to what the execution path can see — declared targets and
  parameters; the rest belongs to admission under (c). This is what D2 needs.
- **G2** (`5da15e8`, `337ea13`): ADAPTER.md became a complete contract, and
  five suite steps were fixed. From here on fsp follows ADAPTER.md, not the
  runner.
- **G3** (`d6fce2c`): the runner and an implementation share no code (D5).

**The design was discussed and closed** the same day ([DESIGN.md
§1](DESIGN.md#1-decisions)). One decision was replaced: D7 originally made the
model and its endpoint structural; D28 replaced that — they are runtime
settings (D33) — and D7 now covers only where API keys live. G4, a host path
inside structural content, closed with it.
