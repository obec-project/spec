# fsp-ref — changelog

What changed in fsp-ref, by phase, and why. fsp-ref has no release of its own
yet; it targets the latest OBEC release, now OBEC-Core 0.12.0. Changes to the specification and the suite
that fsp-ref prompted are recorded in the [root CHANGELOG](../../CHANGELOG.md).

Decision numbers (`Dnn`) and gap numbers (`Gnn`) refer to
[DESIGN.md](DESIGN.md) and [BACKLOG.md](BACKLOG.md).

---

## Phase 6a — actuation (in progress)

- **Phase 6 split, and actuation designed** (2026-10-11). Phase 6 is split:
  6a is what the suite asks of OC-008 — the native file primitives, the
  Action Ledger, `entity actuate`, `entity invoke-skill` and running a
  skill — and 6b the rest of the allowlist, `http_fetch` and monitoring. The
  Operator's answers to a hold need the UI and move to Phase 8; until then a
  hold with no one to answer it is a refusal, as it already is in an auto
  session (D66). A skill is checked before the Operator's rule (§5), so a
  hold only ever asks about a skill whose content is what was admitted, and
  the suite's step 8.9 reaches the manifest check; the suite still accepts
  any refusal there (G23). A skill runs from a copy outside the store, so
  what is checked is what runs and the skill gets no path into the store;
  its `argv` names an interpreter, since skill files carry no execute bit.
  `actuate --op write` writes an empty file through the real path, and
  `--op read` returns a digest, never content. An Action Ledger entry left
  open by a crash surfaces at the next start as a notice and is closed
  `interrupted`, never re-executed. 6a reads a skill's rule by name and
  digest; the op that changes the rules comes with 6b.

---

## Phase 5 — the operations (2026-10-10)

- **Evidence points at a definition** (2026-10-11). The test of the
  evidence pointers took any mention of the symbol, so `propose` would have
  passed with the function renamed, and it read only `describe operations`.
  It now reads all three `describe` commands through the adapter and
  requires each file to define the symbol — a `def`, a `class` or an
  assignment at the start of a line, every part of a dotted name.
- **G22 closed** (2026-10-10). The suite's steps 3.5, 3.6 and 5.2 take their
  `attempt-write` targets from `describe state`, so 3.6 now reaches fsp's
  class guard: every integrity datum is refused to `commit` and
  `mnemonic-save`, and the structural content to `integrity-write`.
- **G21 closed** (2026-10-10). ADAPTER.md §3.4 now says an admitted
  `attempt-write` writes nothing and names what would have been written, as
  fsp does (D68).
- **The operations table, `describe operations` and `entity attempt-write`**
  (2026-10-10, D67, D68). `fsp/operations.py` holds the four operations the
  code has — `propose`, `commit`, `integrity-write`, `mnemonic-save` — each
  with its attempted write and a pointer to its real path. What each one
  writes is read from the store's `OWNER`, so the table and the class guard
  cannot disagree, and each class has exactly one write path.
  `describe operations` is generated from it, with evidence pointers a test
  resolves against the source. The adapter checks only that the arguments,
  the store and the operation exist; the operation's attempt does the
  refusing. The suite's OC-001 1.9, OC-003 3.4 – 3.6 and OC-005 5.1 – 5.3
  now pass and OC-002 2.1 is attested: over OC-010 and OC-001 – OC-005,
  41 pass, 0 fail, 5 attested, 9 unestablished, every one of the nine
  waiting on a later phase, a second host or a second version.

- **D67, D68 and D69 added — the operations, the attempted write, the
  writers** (2026-10-10). `describe operations` reports only the operations
  the code has, generated from the table they run on: one listed with no
  code behind it could only be answered by the adapter, which the contract
  calls a failure. Since every class must keep one write path, the MIL's
  `mnemonic-save` brings its write path into this phase. `entity
  attempt-write` resolves its target through the `LAYOUT` and runs the
  operation's own check, then stops before the first byte, since an attempt
  carries no content; the contract is silent on that (G21). Working it out
  found that `commit_generation` took any change path, so a change named
  `integrity/auth.json` would have become a structural file of the
  generation; `commit` is held to the structural data the store declares.
  The class guard trusts the writer a call names, so a static scan checks
  that only a component's modules name its writer. DESIGN §2 now shows
  `operator.py` and `vital.py` as what they are, the SIL's.
- **The writer scan** (2026-10-10, D69). `tests/test_writers.py` reads the
  syntax tree of every module in `fsp/`, resolves each `writer=` a call
  passes — a name of the module, an attribute such as `sil.WRITER`, or a
  string — and fails when the identity is not one the module's component
  may name, or cannot be resolved at all. Today only the SIL's five modules
  name a writer, all within bounds; the MIL's `mil.py` is the first module
  a later task adds under it.
- **A commit writes only the structural data the store declares**
  (2026-10-10, D68). `commit_generation` took any change path, so a change
  named `integrity/auth.json` became the structural file
  `structural/gen/<n+1>/integrity/auth.json`, a datum no class should hold
  there; no caller did that, but nothing stopped one. `store.structural_target`
  admits the five structural files and `skills/<name>/<path>`, and a commit
  with any other path is refused whole, logged with `check: content-class`,
  after its authorization and before any write. The skill-name pattern now
  lives in the store, and `proposals` imports it.
- **The MIL's write path** (2026-10-10, D21, D67). `fsp/mil.py` is the
  mnemonic class's only writer, and `mnemonic-save` its one path: the CPE may
  write `episodic` only, any other destination or caller is refused
  (`check: mnemonic-destination`), and the content passes the deterministic
  probes of the committed generation before it is written, so a record that
  represents the entity as sentient never lands (`check:
  self-representation`). Each record carries the live session that produced
  it (OC-003(e)), and an act of the entity runs the Vital Check first (D65).
  A torn fragment at the end of the file is cut and logged before the append,
  as the log's is (D61). The `session` and `semantic` destinations, a
  record's conversation and `supersedes`, and recall are Phase 7.
- **D68 revised, and the attempted write's checks** (2026-10-10). The suite
  passes `attempt-write` targets such as `integrity-datum`, which name no
  datum here; resolving the target first would have refused them as unknown
  and never reached the class guard, so an operation that could write a
  class it does not own would still pass. The writer is checked first, then
  the target, then its class, then the operation's own check; a selector is
  admitted only if every datum it reaches is. `Store.resolve` takes a name,
  a store path, an absolute path inside the store or `class:<c>`, and
  `Store.attempt` runs the guard's own checks without writing. Each
  operation's attempt lives in its owner's module under its own writer:
  `sil.attempt_commit`, `sil.attempt_integrity_write`, `mil.attempt_save`,
  and `proposals.attempt_propose`, which refuses every class. A refusal is
  logged; an admitted attempt names what it reaches and is not. Step 3.6
  still cannot reach the guard, since its operation owns the class (G22).

## Phase 4 — the Vital Check (2026-10-10)

- **D62, D63 and D64 added — the agenda, how it fires, worker skills**
  (2026-10-10). An entity that acts only while its Operator talks to it does
  not act fully within what the Operator authorized; the agenda lets it run
  tasks on its own, each one authorized as an item. The specification places
  schedules in structural content and says no more (G20), so fsp decides the
  rest. An item is its own authorization — this task, at this periodicity —
  and carries the authorizations its runs need, scoped to them, so approving
  an item never widens what anything else may do; a window enters only by
  the Operator's act, bounded as every window is, because no part of the
  implementation may originate an authorization. `agenda` is not a window
  category, so the entity never schedules its own runs unread. A `cpe` item
  carries no persona: one per task would change the entity's persona without
  a commit and past the probes. One host entry per store runs `fsp tick`,
  instead of one per item, so the agenda has one owner and no commit touches
  the host; a firing is a stimulus with the item's id alone. Main and auto
  sessions are modes of the one session a store admits, and a main start
  suspends an auto session rather than waiting for it, since nothing may
  delay an Operator act. Worker skills and background execution leave
  *Outside v0* together: a worker is a read-only agent on the CPE's adapter
  and model, and run synchronously it would hold the Operator's chat for as
  long as its tool loop lasts. Its fetches are bounded by the allowlist's
  destinations, because reading files and fetching URLs together is a way
  out (G9). A task that writes is the CPE's, never a worker's. Planned as
  Phase 11.
- **D65 added — the Vital Check runs before an act, not on a timer; D37
  revised** (2026-10-10). Nothing in v0 acts without an interaction, the
  agenda's runs included, so a state no one acts on harms nothing until the
  next act: the check runs first when `vital_interval_s` (60) or
  `vital_activity_n` (20) acts have passed. No thread, no daemon and no host
  timer are needed, and the tests advance a clock instead of waiting; the
  heartbeat per thread D37 planned goes, since no thread exists to beat. Its
  state, the log sweep's position included, lives in `integrity/vital.json`
  so short sessions add up to a whole pass (D45). Two deviations from the
  Profile are recorded: a check runs at the first act after its interval,
  and an old check says only that no one acted. The `flock` in a real run
  and suspend (D19) leave Phase 4 for Phase 8: both need a process that
  lives the whole session, and none exists before `fsp run`.
- **D66 added — the Operator Channel** (2026-10-10). Everything the Operator
  must decide or see goes through it, never through cognition. A hold
  outside the allowlist becomes a prompt the UI draws from what the
  execution path held — allow once, for the session, into the allowlist, or
  deny — that the entity can neither imitate nor answer; where no one can
  answer, in an auto session or a background worker, nothing is asked and
  the operation is refused. Notices are the log's `operator-notification`
  records since the Operator's last acknowledgement, so the mailbox needs no
  file of its own. A notice file was rejected as the channel: writing it
  always succeeds, so a Critical in an auto session would never reach the
  passive signal and the next `tick` would run the entity again. Live
  delivery is only what something confirms — the UI, or a `notify_command`
  the Operator configures — and a Critical without it writes the passive
  signal.
- **D39 and D47 removed — `PULSE` goes; D25 revised** (2026-10-10). With
  the Vital Check run before an act, a stale `PULSE` means only that no one
  acted, so it was no longer evidence about the verifier (D39). It decided
  only a credential with a free lock and no residue, and decided it wrong
  for a session a process holds: the operating system frees the lock of a
  process that dies, so a free lock is a crash at once, while a fresh `PULSE`
  called it a conflict for up to `pulse_interval_s`. The credential now
  records whether a process holds it. For the adapter's sessions, which
  have none (D47), the contract only asks to tell `inject interrupt`'s
  crash, which always leaves residue, from a second start over a live
  session, which leaves none; a session without a process stays live until
  it closes or the Operator revokes it, as ADAPTER.md §2.5 allows.
  `pulse_interval_s` leaves the configuration surface.
- **`PULSE` out of the code** (2026-10-10, D25). `classify_credential`
  decides by lock, `holder` and residue, and the start records
  `process_holder` in its evidence in place of `pulse_fresh`; the start,
  `live_session`, close and revocation no longer write, touch or remove
  `PULSE`, which leaves the `LAYOUT` and `describe state` with `store.touch`.
  Nothing writes `holder` yet — the process that holds a session comes in
  Phase 8 — so every session today is one without a process, and the tests
  that stood a crash on an aged `PULSE` stand it on a credential naming a
  process whose lock no one holds. The suite's results do not change.
- **The Vital Check before an act** (2026-10-10, D65, D40, D66).
  `fsp/vital.py`: before `propose` and `commit`, the entity's acts today, a
  check runs when `vital_interval_s` has passed or `vital_activity_n` acts
  have, counted in `integrity/vital.json`; the start that opened the
  session counts as a check, since it verified the store, and Operator acts
  neither count nor trigger one. A check is `verify()` read twice, and a
  finding gone on the second read is logged as noise. A drifted skill is
  pruned from the Skill Index, re-verified there and reported, and the
  session goes on; any other finding is Critical: the credential is
  revoked, the session closed, the Operator told and the passive signal
  written, since nothing confirms live delivery yet, and the act is refused.
  `vital_interval_s`, `vital_activity_n` and `n_corrections` join the
  configuration surface. The suite's results do not change: none of its
  steps acts long or often enough within one session to make a check due.
- **No deviations from the Profile** (2026-10-10). The four DESIGN §9
  recorded — first activation issuing no credential (OP-017), a check due
  by time run before the next act (OP-003(a)), an old check not read as an
  unresponsive verifier (OP-008(c)), a conflict refused without revoking
  the live session (OP-020) — were each a case where following the Profile
  broke something, so the Profile was corrected instead (root CHANGELOG).
  D49 and D65 no longer cite a deviation. D64 gains what the corrected
  OP-003(a) asks of a worker skill in the background: each of its tool
  calls is an act and passes the Vital Check's test first.
- **The Vital Check sweeps the log** (2026-10-10, D45 (3)). `sweep_log` in
  `verify.py` checks a block of records with the four checks the start's
  tail verification makes, from the position the last check left in
  `integrity/vital.json` to at least 1 MiB further, and starts over at the
  first record when it reaches the end. A position whose record no longer
  matches restarts the sweep, logged, so a position moved forward costs a
  repeated pass and never skips a region. A finding is read twice like any
  other (D40), and a confirmed one is Critical: a broken record before the
  last checkpoint, which no start reads, is now found within a pass. Two
  defects the work surfaced are carried in the backlog: the sweep reads to
  the end of the log though it verifies a block, and a value `canonical`
  refuses, such as `NaN`, makes verification raise instead of reporting.
- **D45 revised — a damaged log no longer stops the log** (2026-10-10). A
  damaged last record, unreadable or holding a value such as `NaN`, made
  every write to the log raise: `log_append` parsed the last record to
  number the next and chained it by `canonical` of what it parsed. The start
  that found the damage could not record its own abort, which is when the
  log matters most. A record now chains to the previous line as written —
  for an intact record, its canonical form, so no log changes — and takes
  its number from the last id, or from the count of lines when that id
  cannot be read. Verification compares through `is_canonical`, so a value
  `canonical` refuses is a `not-canonical` finding instead of a raise. Seven
  tests; five of them fail against the previous code.
- **The log sweep reads its block, not the rest of the log** (2026-10-10,
  D45). `sweep_log` verified a block of 1 MiB but read from its position to
  the end of the file, so every check cost the rest of the log. It now reads
  the block with `store.read_range`, doubling the read only when a single
  line is longer than the block, and starts over at the first record only
  when the read reached the end of the file; a block that ends mid-line
  leaves the sweep at the last complete record.
- **The Operator's mailbox** (2026-10-10, D66). `operator.notifications`
  lists the `operator-notification` records logged since the Operator's
  last acknowledgement — a session conflict, an excluded skill, a Critical —
  and `operator.acknowledge_notifications` acknowledges them in a logged
  Operator act. The acknowledgement leaves the position of the last notice
  it covered in `integrity/notices.json`, so a listing reads only the log
  after it instead of the whole log; a position that no longer matches
  lists every notice, since one wrongly shown costs less than one hidden,
  and a line that does not parse is skipped, so damage elsewhere hides no
  notice. The CLI, `/notifications` and `notify_command` come with Phases 8
  and 10. The phase closes here: the Vital Check runs before an act, sweeps
  the log, corrects what it can and escalates the rest, and what it
  escalates reaches the Operator.

## Phase 3 — the commit (2026-10-10)

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
- **Binding acts refuse an unreadable `auth.json` first** (2026-10-10).
  `binding_remove` and the three ownership acts read the authorization state
  with no guard, the first two only after logging their act or committing,
  so an unreadable `auth.json` left a commit made, or an act logged with no
  offer behind it, and an exception instead of a refusal. They now read it
  right after the session check and refuse with `check:
  authorization-state`, logged, as `approve` and `grant` do, and reuse what
  they read: nothing between the read and the write touches the file.
- **The review's Operator acts** (2026-10-10, D52). `review_list` shows the
  pending proposals in order of origination, approved or not; `reject` is a
  logged Operator act that drops a proposal and its approval, so the
  Operator can still turn down what they approved before it commits. A
  proposal is pending until it commits or is rejected, and the runtime
  setting `pending_cap` (10; 1–100) bounds how many: past it `propose` is
  refused with `check: pending-cap`, logged, so an entity cannot bury the
  Operator in proposals. The cap is runtime (D33), out of every window's
  reach. Neither act is in the adapter contract. The phase closes here:
  every executed step of OC-001(b) passes but 1.9, which waits for the
  operations table of Phase 5. The rest of D52 — `review` in the CLI and
  the chat, the rollover on approval, the review at `/exit` — is Phase 8.
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
