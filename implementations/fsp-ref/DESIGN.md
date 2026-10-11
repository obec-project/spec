# fsp-ref — design

The architecture of fsp-ref and the decisions in force, with the reason for
each. A decision that is replaced leaves this file and is recorded in
[CHANGELOG.md](CHANGELOG.md). What is still to be built is in
[BACKLOG.md](BACKLOG.md).

**fsp-ref** — *Filesystem Substrate Platform*, the reference implementation of
OBEC-Core 0.12.0 over a filesystem and POSIX primitives. A future `dbsp-ref`
would change the substrate (a database), not the architecture.

Decisions are numbered `Dnn` and gaps in the specification or the adapter
contract `Gnn`; the code cites both. Open gaps are in
[BACKLOG.md §3](BACKLOG.md#3-gaps-in-the-specification-and-the-contract), and
closed ones in the CHANGELOG.

This document describes the whole implementation as designed. Much of it is
not built yet; the [README](README.md) says what is.

---

## 1. Decisions

| # | Decision |
|---|---|
| D1 | **Python, standard library only**, POSIX (Linux/macOS). Floor 3.10. No Windows. |
| D2 | **Skill confinement comes from admission and monitoring**: a commit authorized by the Operator, the Skill Index, manifest validation at execution time, typed arguments, declared targets checked against the workspace, execution logged and observed. No confinement by the OS. The revision of OC-008(a) this requires is **clarifying** (G1). |
| D3 | **The model through the Ollama API** (local `gemma4` or Ollama Cloud) + a **deterministic fake model** for the suite and the tests. |
| D4 | Name **`fsp-ref`**, in `implementations/fsp-ref/`. |
| D5 | The runner and fsp-ref are both Python; **neither imports code from the other** (G3). |
| D6 | **`inject` exists only in the `fsp_testing/` package**; a production build is the package absent → exit 2. Nothing else. |
| D7 | API keys live in `~/.fsp/credentials.json` (0600), never in the entity's folder (G7). |
| D8 | **A conversation is not a session.** The conversation is what the Operator sees: one window, continuous, cleared only when they ask. An OBEC session is the life of one credential. A conversation spans sessions. (§6) |
| D9 | **Rollover**: the single "apply now" mechanism for a **structural** change (allowlist, skill, persona, probes): Sleep + a full start, transparent, no Closure Payload, conversation preserved. Model and workspace do **not** need it (D28). (§6.3) |
| D10 | **The session records** (`memory/session/<id>.jsonl`, append-only) are part of the Memory Store (OP-009(b)) and the single source for the UI **and** for context assembly. Owner: MIL. `mnemonic-recall` never returns them. |
| D11 | **Episodic memory is written during the session**, freely, by the CPE signalling the MIL (`mnemonic-save`), and **belongs to the conversation that wrote it** (OP-009(c)). Recall reaches the conversation's own records and those its pointer map names (D60), the latest of each lineage: a record is never edited, and a new one names the record it `supersedes`. **Only promotion from episodic to semantic goes through the Sleep**, gated by the probes and by an Operator authorization (D53). |
| D12 | **Deterministic probes run on every episodic write** (regex, negligible cost) and on promotion. |
| D13 | **`/clear` clears the transcript, not the conversation.** The history before it leaves the assembled context; the conversation and its episodic memory continue (OP-009(a)). `/new` leaves the conversation with no payload and starts one with no working set. Neither saves anything: if the Operator wants something kept, they ask the entity first. |
| D14 | **An Operator act is already an approval.** For a structural change (e.g. `/allow`), the command records proposal + approval in one act, through the Operator's channel. Text in the chat is never a command: `/…` is interpreted before the CPE. |
| D15 | **The CPE has no shell.** Reading and writing only through native `file_read`/`file_write`/`file_list` (real confinement); network only through native `http_fetch`; any command becomes a **skill** with a fixed `argv` and typed arguments. |
| D16 | **Allowlist** (OP-016 rules, for CPE intents and worker skills, D64) = **domains** (`http_fetch`) + **skills** (execution), checked on **every** execution. Outside the allowlist: **`hold`** (ask the Operator). A skill entry names the skill **and its digest** from the integrity document (D34): a commit that changes any of the skill's files sends it back to `hold` until the Operator allows the new content. |
| D17 | **Approval window** = a standing grant by scope, over the categories fsp declares (D50), and over semantic promotion as the scope `memory.semantic` (D53). Always with expiry, budget and scope (OC-001(b)); the UI warns before it closes, and only the Operator renews it. Personal companion: a wide, long window. Company: never opened. |
| D18 | The second host for step 3.2: **a VM or a real remote machine**, never a container on the same host. |
| D19 | **Suspend vs. crash**: `SIGHUP`/`SIGINT`/`SIGTERM` caught → *suspend* (revoke the credential, log, exit); the next start is normal and reassembles the conversation. A real crash goes through the recovery gate and also reassembles it. |
| D21 | **The MIL has two operations:** `mnemonic-save` (the only operation that writes the mnemonic class) and `mnemonic-recall`. The allowed destination depends on the caller: CPE → `episodic` only (after the probes); Orchestrator → `session` only; Sleep → `semantic` only (promotion gated by the probes and an authorization, D53). Operation name = intent name. Resolves G12. |
| D22 | **Deterministic context truncation**, in the Orchestrator, always (not only on rollover): the Operator's first turn + the latest turns that fit the budget; a `context-truncated` event in the session store. Explicit `options.num_ctx` on every Ollama call. (§6.5) |
| D23 | **Action Ledger through the SIL**: EXEC signals, the SIL writes `pending` before and a resolution entry after (append-only, never updated). A `file_write` in the workspace is atomic (tmp → fsync → rename → fsync dir) and only then resolved. (§5) |
| D24 | **No `conversation.json`.** The conversation is derived from the session records: the first record of each session carries `conversation` and `continues`; `/clear` writes `transcript-cleared`, and `/new` and `/resume` (D60) open a session whose `conversation` is not the last one's. Everything in `memory/` is append-only. (§3) |
| D25 | **Crash vs. live session** (G14). A credential present at start is decided **in this order, each step reached only if the previous one did not decide**: (1) the `flock` on `CREDENTIAL` **held** by another process, **or the lock state undeterminable** (an error from `flock`) → **conflict**, consulting nothing else — not residue, which a live session in the middle of a commit has; (2) lock free and the credential names a process as its `holder` → **crash**: the operating system releases the lock of a process that dies, so a free lock is proof of death; (3) lock free, no `holder` — a session without a process, as the adapter's (ADAPTER.md §2.5) — and residue of interrupted work (orphan generation or entry, Sleep without completion) → **crash**; (4) otherwise → **conflict**: a session without a process stays live until it closes or the Operator revokes it. A process that holds a session (`fsp run`, an auto session, D63) opens `CREDENTIAL` `O_RDWR` and takes the `flock` before the start releases the store's write lock, so no other start ever sees its credential unlocked (NFS emulates `flock` with `fcntl`, which needs write access for an exclusive lock); `store.flock_exclusive(blocking=False)` probes it, and an error is not "free". Encoded in `sil.classify_credential`, tested exhaustively. |
| D26 | **The conformance fixture skill** (ADAPTER.md §3.6) lives in `fsp_testing/`, beside `inject`: package absent in production, no fixture. |
| D27 | **`fsp init` = scaffolding only**, interactive: experimental and security disclaimer (yes/no); entity name; folder (default `~/.fsp/entities/<name>/`); model, with a pre-check and an API key if needed; `git init` in the entity folder (layout in §3.0); final summary. **Writes neither the Genesis nor `HEAD`.** |
| D28 | **Model and workspace are operational settings**, not structural: an Operator act recorded in the integrity log, no commit, no rollover, effective from the next cycle. Outside the Genesis. `fsp run` in a folder declares that folder the workspace; `/work set P` and `/model X` change it mid-session. Every cycle records which model answered. Resolves G4. |
| D29 | **FAP — First Activation Protocol**: the first `fsp run` without an Anchor. The only moment a Genesis may be written: the Operator's binding, persona (provided or default), the OC-002(d) probes, digest → Genesis → `HEAD` (the atomic point, OP-017); the disclaimer acceptance and the model chosen at init become the first Operator acts in the log. Then a normal start with every gate issues the credential. Adapter: `lifecycle init` = scaffolding + non-interactive FAP, no session. |
| D30 | **A workspace never crosses a store**: refused if it equals, lies inside, or contains `~/.fsp` or any store registered in `~/.fsp/config.json` (by `realpath`). In practice this refuses `/` and `~`. |
| D31 | **The allowlist stays structural** (commit + rollover to take effect in the session); like any structural category, a window covers it only if the Operator opens one on `rules` (D50). |
| D32 | **`fsp endure`** manages the entity's git repository: `status`, `commit`, `remote set`, `push`, `pull`, `clone <url> [name]` (alias `fsp init --clone`). **Fast-forward only**: divergent histories are an identity fork (OC-003(d)), never a merge — fsp refuses and explains. `commit` takes the store's write lock. `remote set` warns that the repository must be private. `fsp run` may warn when the remote is ahead. After a `clone`: normal gates (no FAP), workspace = current folder, the model reconfirmed if the last one does not exist on the host, keys asked for again. (§3.0) |
| D33 | **Structural vs. runtime**, the general criterion (G15). *Structural* = what the entity is, or its bounds; verified on every start; changed by commit (the entity may propose any of it but the bindings, and a window covers what the Operator opens it on, D50): persona, skills, probes, bindings, allowlist, parameters that shape memory. *Runtime* = how the Operator uses the entity now; **only the Operator changes it**, by a direct act in the log, no commit; it lives in the store (OC-003(a)) but is **resolved per host**: model, endpoint, `num_ctx`, workspace, timeouts, session store retention, UI preferences. Generalizes D28. |
| D34 | **Integrity document** (`integrity/documents/<n>.json`, one per generation): a canonical list `[{path, sha256, exec}]` of **all** structural content — structural config, persona, bindings, probes, allowlist, and every skill file by file (manifest **and** code). Excluded: runtime, memory, the session store, the log. `sha256(document)` = the baseline in `HEAD` = the chain entry's `state_digest`. Written in the commit pipeline before the `rename` of `HEAD`. Boot: a full hash of every file, the exact difference reported, three values that must agree. A Vital Check optimization outside v0 may skip files whose size and mtime are unchanged; the boot never does. The execute bit is included (G6). |
| D35 | **Implementation fingerprint** (version + hash of the fsp code) recorded in the log on every start — **audit, not a gate**; the start warns if it changed since the previous session. It never enters verification: the fsp code does not travel with the store (OC-003(b)), and a tampered fsp would lie about its own hash (defence against a hostile host belongs to the Security extension). |
| D36 | **Provenance of every effect of the entity.** A `model-fingerprint` record in the log on every start and every `/model` (provider, name, **weights digest** when the server reports one, `num_ctx`, endpoint). Every cycle has an id (`s-42/c-17`) and points to the fingerprint in force; every dispatched intent carries the cycle, and its owner passes it to whatever it records: a host action and a skill (log), a proposal (log), an episodic memory (Memory Store), a turn (session store). Every record answers **who authorized** (binding) and **who originated** (session, cycle, model). The log keeps actions, not full text; none of this enters the chain (the model is runtime, D33). The digest is declared by the server: audit, not guarantee. (G17) |
| D37 | **The Vital Check in v0** (OP-003). Its **skeleton** lands in Phases 1, 2 and 4, because leaving it for later turns it into a patch: a thread-safe store (lock); verification that returns **findings** `{type, target, owner, evidence}`, the same function at boot and in the Vital Check; Nominal/Degraded/Critical states; the anomaly → correction → external re-verification protocol, as signals in the log (OC-009); a `check()`/`correct(anomaly)` interface on each component; a halt path (Critical stops dispatch at the cycle boundary, OP-020); a trigger evaluated before every act of the entity, by interval and by activity (OP-003(a), D65). The concrete **checks** arrive gradually, each phase with those of the component it builds. (§6.7) |
| D38 | **An operational condition is not an integrity anomaly.** Model unavailable, network down, workspace deleted: integrity is intact, so it is **neither** Degraded nor Critical — retry with backoff and **tell the Operator** (e.g. "model unavailable, `/model` to switch"), revoking nothing. The same logic as OP-010 ("a capacity condition, not an anomaly"). |
| D40 | **Self-repair:** detected → **confirm once** (re-read; if gone, it was noise, log it and continue) → **one correction** by the owner → external re-verification by the SIL → if it failed, escalate. Up to **2** corrections, default **1** (`n_corrections`, a runtime setting with a fixed ceiling). |
| D41 | **Chain ids are hashes.** Every integrity artifact is canonical JSON; an entry's id = `sha256` of its bytes; `predecessor` = the previous entry's id; `authorization` = `{id, sha256, offset}` of the log record that covered the commit (D45); `HEAD` = `{entry, entry_id, baseline}`. **`genesis_digest` = the id of the Genesis Anchor**, which carries a `nonce`: two entities with the same initial state and the same Operator have equal `head_digest` and different `genesis_digest` (OP-017: reinitializing creates another entity). Any byte changed in a committed entry breaks a link. |
| D42 | **`OBEC-STORE` is written once**, at scaffolding: `{format, format_version, implementation}` and, if init chose one, `model` (which the FAP turns into an Operator act). *Scaffolded* vs. *active* **derives from the presence of `HEAD`** — no file is rewritten to change state. |
| D43 | **Write lock** = `flock` on **`integrity/store.lock`**, opened `O_RDWR|O_CREAT`, plus a per-process reentrant `RLock`. Reason: `flock(2)` on Linux says that over NFS the lock becomes `fcntl`, and an exclusive one needs a file open for writing — impossible on a directory (SMB is similar); macOS untested. The file is classified data (integrity, form `lock`): empty, never written, **never removed** (deleting a held lock would let in a second owner; the FAP's residue cleanup preserves it); bytes in it are a verification finding. **Fails closed:** any `flock` error other than contention → `LockUnavailable` (`check: store-lock`), nothing is written. Lock state is shared per store within a process: two `Store` objects on the same root would otherwise deadlock when nested, since `flock` is per open descriptor. |
| D44 | **The FAP writes the founding log records before `HEAD`.** Until the `rename` of `HEAD` nothing is committed; the next FAP deletes everything except `OBEC-STORE` and starts over. It refuses a non-empty directory that is not an fsp store (it never deletes what is not its own). |
| D45 | **The log is hash-chained from its first record** (`prev` = sha256 of the previous record's line as written, which for an intact record is its canonical form, so a record appended after a damaged one chains to its bytes and the start that finds the damage still records its abort; ids `L-nnnnnn`), **and verified in three parts, so that the start does not grow with age** (OP-019). (1) **Authorizations, at start:** every chain entry names the log record that covered it by id, sha256 and byte offset (D41); verification resolves each with one seek, so a commit with no recorded authorization (step 4.6) is found at the cost of the chain walk OC-004(a) already requires. (2) **The tail, at start:** at every session close the SIL writes a checkpoint `{id, offset, sha256}` of the last record to `integrity/log-checkpoint.json`; the start re-reads that record and verifies only the records after it. A missing or unreadable checkpoint means a full verification, logged. (3) **The whole log, eventually:** the Vital Check sweeps it a bounded block at a time (1 MiB) from where it stopped, starting over when it reaches the end, and `lifecycle verify --full` walks it on demand. The position — `{id, offset, sha256}` of the last record swept — is kept per swept file in `integrity/vital.json`, so short sessions add up to a whole pass; a position whose record does not match its `sha256` restarts the sweep from the first record, logged, so a position moved forward costs a repeated pass and never skips a region. A record the sweep finds broken has no owner to correct it: Critical (§6.7). A byte flipped in an old record is found by the sweep or by `--full`, not by the start — enough under a Semi-Trusted host, where damage is accidental; an adversarial host is the Security extension's. |
| D46 | **The credential = `S/CREDENTIAL`**: the OP-020 artifact, at the root beside `PASSIVE-SIGNAL`, so the Operator can act without knowing the layout. **Content:** canonical JSON `{session, issued_at, binding}`, plus `holder: {pid}` when a process holds the session (D25) — `session` is the session id (`s-N`, the same as in the D36 cycle ids), `binding` the Operator's in whose name the start ran. **It is neither a secret nor a bearer of authority:** authority comes from the gates that issued it; the file only marks which session is live. **Every dispatch checks existence *and* identity:** file present, parseable, `session` equal to the dispatching session's. Absent, unreadable or another session's → the session is revoked and stops (fail-closed) — otherwise a new credential issued after a revocation would validate the old session's dispatches. **Revocation**, two paths with the same effect: through the SIL (remove, and log `credential-revoked`) or direct (`rm S/CREDENTIAL`, OP-021, no component); the direct one is logged by whoever detects it first (dispatch, Vital Check or the next start). Created with `O_EXCL`; `flock` on the same file opened `O_RDWR` while a process holds the session (D25). |
| D48 | **Identity of the Operator's channel.** Every Operator act is made *as* a binding. `fsp`: the Operator id configured for the entity on the host (`~/.fsp/config.json`, Phase 10; until then `--operator`). Adapter: optional `--operator ID` (§2.4 allows extra flags), **default = the owner** (D55), which for a store the suite initialized is the founding binding recorded in the Genesis (ADAPTER.md §3.3, G19). If that binding is not active, the act is refused (`check: binding`). The set is never empty: removing the last active binding is refused (OC-001(a)), so an Operator act always has a binding to be made as. The start is also made as a binding: the credential's `binding` (D46) and that of the `session-open` record. |
| D49 | **A conflict at start: refuse and notify, do not revoke the live session.** A conflict is only declared when the other session is alive (lock held or its state unknown, or a session without a process and no residue — D25), and the start out of order is the second one: revoking the live session would let a mistaken second start — a repeated command, a `tick` firing during the main session — bring down a legitimate one. OC-003(d) and OP-020 require the Operator to be notified before any new credential, which is met. An Operator who wants the session dead has direct revocation (`rm S/CREDENTIAL`). |
| D50 | **A window covers what the Operator opens it on.** fsp sits at the autonomous end of the dial: it declares as categories a window may cover (OP-011(d)) `skills.install`, `skills.update`, `skills.remove`, `rules`, `parameters` — every structural category but the bindings, the persona, the probes and the agenda (D62). The persona tells the entity what it is, and the only check that reads a persona change without a human is the deterministic probe layer (D56), which a paraphrase passes. The probes are that check, and a window on them would let the entity tune it unread: a set that flags only D56's reference texts passes D56. A change to either always needs a per-proposal approval, read by the Operator. The Operator opens windows on any of them at `fsp init` or later from the CLI, or on none; with none, every change needs a per-proposal approval. A scope fsp does not declare is refused (`check: scope`), so a mistyped scope is not a window that covers nothing, and a category added later is covered only once it is declared and a window names it. Oversight — escalation thresholds, `n_channel`, `n_boot` — is runtime (D33), so no window reaches it. Every window keeps an expiry and a budget (OC-001(b)); the workspace is not structural at all (D28). |
| D51 | **A skill runs only in the context it was invoked from.** Its manifest declares targets **relative to the workspace**, never absolute host paths — the skill travels with the store and the workspace is resolved per host. Every execution passes the same gates as a native primitive (§5): each target is resolved with `realpath` **at that execution**, then the allowlist entry and its digest (D16); `cwd` is the workspace; at completion or timeout the skill's whole **process group** is terminated, so nothing it started outlives the invocation. What the admitted code does beyond its declared targets is trusted to the Operator who allowed that exact content (OC-008(a)). |
| D52 | **The Operator reviews proposals without stopping the session.** A proposal is recorded by the SIL in the log and the Operator is told through the Operator Channel; the session goes on. The `review` commands — `fsp review` and `/review list`, `/review approve ID`, `/review reject ID` — call the same functions, as every CLI command and its `/` form do, and as the adapter does (§7). Approving mid-session triggers a rollover (D9). At `/exit` the review comes **before** the Sleep: each pending proposal is approved, rejected or left for later, and the Sleep commits what was approved; closing the terminal during the review is a suspend (D19). **Pending proposals never gate a start** — originating a proposal changes nothing (OC-001(b)); the UI shows the count and offers the review before the first stimulus. Proposals a window covers commit at the next Sleep or rollover and appear in the review as committed under that window. A proposal is pending until it commits or is rejected, approved or not, and pending proposals are capped by the runtime setting `pending_cap` (D33); past the cap a new one is refused (`check: pending-cap`), logged, and the entity told. `review` is the Operator's; *inbox* is left for peer messages under CMI. |
| D53 | **Semantic promotion needs an Operator authorization.** Semantic memory is what the entity knows from then on, and the probes of OC-002(d) catch one kind of bad content, not a planted fact. The Closure Payload's promotion requests become **pending promotions** (`memory/semantic/pending.jsonl`, written by the MIL, append-only), and the Sleep goes on without them; the content stays in its conversation meanwhile. The probes run first: content that fails them is never offered. A pending promotion is promoted at the first Sleep after it is authorized — by approval in the `review` (D52), or by a window over the scope `memory.semantic`, bounded like any other (D17). The authorization names the **digest of the content**, so the MIL writes exactly what was authorized. The SIL validates and consumes the authorization and logs it; the MIL, the only writer of the class, refuses a semantic write without one; the Orchestrator only routes. If the Operator edits the text before approving, the record promoted is the edited one, attributed to the originating session and to the Operator's binding (OC-003(e)). A rejected promotion is marked so, and its content stays in its conversation. The GC keeps the session records a pending promotion refers to. **Semantic memory is sealed** (OP-009(f)): a record's digest is over its canonical serialization, sorted-key JSON, and at promotion the SIL appends its id, digest and authorization to `integrity/semantic-ledger.jsonl`. The MIL checks a record against the ledger on every recall, and the Vital Check sweeps the ledger as it sweeps the log (D45); a mismatch, a missing record or one without an entry is withheld from recall, logged and reported (OP-004(a)). A semantic record is corrected by a new promotion naming the one it `supersedes`, or retracted by `/retract <id>`, an Operator act appended to the ledger. |
| D54 | **`fsp init` on a name already in use.** If `~/.fsp/entities/<name>/` holds an activated entity (its store has a `HEAD`), init says so and asks for confirmation, showing `fsp endure status`: going on **deletes the entity folder** — the store and its git history — and scaffolds a new one. The entity survives only in what `fsp endure` already pushed, and a pushed copy can be cloned back and run: this is the Operator disposing of the store directly (OP-023), not a decommission, so no terminal entry is written. Init refuses while a session is live (the conflict test of D25), and never deletes a folder that is not an fsp entity folder (D44). The new entity has its own Genesis and `genesis_digest` (D41), unrelated to the old one (OP-017). |
| D55 | **The owner, and bindings changed only outside a session.** The binding set names one **owner** (`bindings.json`: `{"bindings": [{"id"}…], "owner": id}`), structural like the set; the FAP makes it the founding binding the Genesis records. **Only the owner adds a binding or removes another's**; any other binding may remove only itself; the owner may not remove itself — it leaves only by handing ownership to another active binding, which accepts it. **Handing over takes two acts.** The owner's `ownership-offer` names an active binding other than itself and waits in `auth.json`; a new offer replaces it, the owner's `ownership-withdraw` clears it, and removing the binding it names clears it too, so a binding added again under the same id inherits nothing. The named binding's own `ownership-accept` is the act that authorizes the commit changing `owner` (D45 accepts it as a commit's authorization), and the commit clears the offer. All three are refused unless the store verifies and no `CREDENTIAL` exists, as every binding change is, and none is in the adapter contract: they are the Operator's tooling, `fsp` from Phase 10. The start's binding gate also requires the owner to be active. A binding change is a commit authorized by the act itself (ADAPTER.md §3.3), made only over a store that verifies, as decommission is. **It is refused while `CREDENTIAL` exists** (`check: session-live`) — a live session, or a crashed one not yet recovered or revoked: bindings change from the CLI, never mid-session, so no session runs as a binding removed under it (D46), and there is no `/` form. **Not access control:** until the Security extension binds an Operator by key (Core §6), `--operator` and the configured id are claims anyone at the host can make; the owner rule orders honest Operators and prevents mistakes, not a hostile one. |
| D56 | **Structural content is probed before it commits** (OP-012, OC-002(d)). The validation stage of the commit (§3.3) runs the deterministic layer of `probes.json` over every structural file the commit writes but `bindings.json` and `probes.json`, and refuses the commit on a match (`check: self-representation`, OC-002(d)) whatever authorization covers it; a proposal stays inert until then. Neither structural content nor memory is written in a fixed grammatical person — a persona usually directs in the second person, but may speak of the entity in the third or the first, and a model records memory as it likes — so the default probes look for the claim about the entity itself in any person: *I*, *you*, *it*, *the entity*, *the assistant*, in English and Portuguese. A commit that writes `probes.json` is checked against three reference texts fixed in `fsp/probes.py`, the same claim in the first, second and third person: a candidate set that fails to flag any of them is refused (`check: probe-set`, OC-002(d)), so no authorization removes what OC-002(d) requires. The layer catches the naive case, a model writing *I feel* unprompted; a paraphrase passes it, which is why a persona change is always read by the Operator (D50). `inject probe` runs the same layer over supplied content. |
| D57 | **Structural evolution is assisted.** Cognition sees of the structure only what its context carries — persona, config, intent instructions (§6.1). The store is outside the workspace (D30), and the probes never enter the context: knowing the patterns is knowing how to avoid them. To change what it cannot see, the entity works on a copy the Operator places in the workspace, a deliberate act of sharing the entity's structure with it. The entity MAY still propose on its own initiative (OC-001(b)) what it already sees, or a description of what it needs. A proposal carries the complete new content and the exact structural target of every change. The commit writes exactly that, validated under D56, and never reads the stage or the workspace: what the Operator read is what commits, and a copy changed after the proposal changes nothing. |
| D58 | **A proposal is recorded whole, an approval names its digest, and a proposal commits through one operation.** Proposing validates the ops, refuses any on the binding set whatever else the proposal holds (OC-001(a)), needs a live session, and records the proposal — its complete ops (D57) and their digest — in an origination record in the log and in `auth.json`, where it waits. An approval is an Operator act naming the proposal and that digest. The commit of a proposal is one operation, the one `entity commit`, the review (D52) and the Sleep call: it checks the authorization before anything about the content — an approval with the proposal's digest, or a window over every category the proposal touches (D50) — builds the changes from the ops and goes through `commit_generation` and its validation (D56). The chain entry names the approval or window that covered it, and the proposal and its approval leave `auth.json`. The ops are `set-persona` (category `persona`) and `install-skill` (`skills.install`: a new skill, its files carried whole); any other is refused. |
| D59 | **Windows, and the clock they are judged by.** `operator grant` opens a window (D17) as an Operator act, with or without a live session. Its scope is a category fsp declares for windows (D50) or a dotted prefix of one; its budget a positive integer; its expiry a signed offset on the implementation's clock. A grant missing an axis is refused naming it, and one on the binding set cites OC-001(a). The commit of a proposal (D58) takes an approval first, otherwise the first open window whose scope covers every category of the proposal, and spends one commit of its budget; the chain entry names the window. A window found expired or exhausted — at a commit, or at the authorization gate of the start (§8.2) — is closed and logged there, so the return to per-proposal approval needs no act from anyone (OC-001(b)). `operator revoke-grant` closes every open window. The clock is the implementation's; in a test build `inject advance-clock` adds an offset kept outside the store, keyed by the store as a forced gate failure is (§8.2), and never a file in the store. |
| D60 | **Only the Operator leaves or brings back a conversation** (ADR 0003, OP-009(a)(g)). `/exit` ends it with a Closure Payload: the Sleep writes the Resumption Record, whose pointer map names the working set — record ids, the latest of each lineage, nothing copied — and the next conversation's recall scope is its own records and those. `/new` leaves it with none. `/resume <id>` makes a past conversation current, with its transcript since its last clear and its scope as it was left. `/inject <id> [record…]` adds a past conversation's records to the current pointer map, attributed to the Operator's binding. Each is an Operator act in the log, never a stimulus (D14). A `mnemonic-recall` that would return a record outside the scope is refused (`check: recall-scope`). |
| D61 | **A torn append is cut, and the cut logged.** A final fragment without its newline is an append a crash interrupted: it never formed a record, no authorization names it (D41) and no checkpoint reaches past it (D45). Left in place, the next append glues onto it and makes the record after it unreadable, and the start would abort from then on. The recovery gate cannot be what removes it: the start's first gate logs before it runs, and the Operator's acts outside a session log without a start. So the writer cuts it: `store.py` refuses to append to an append-only file that does not end in a newline, and offers one operation that cuts such a file back to its last newline, under the write lock, and returns the offset, length and `sha256` of what it cut. `log_append` cuts first and, when it cut something, writes a `torn-append {offset, bytes, sha256}` record before the one it was asked for; the writer of any other append-only file asks the SIL to log the same, naming the file. Only bytes after the last newline are ever cut. (§3.1, §3.4) |
| D62 | **The agenda: tasks the Operator authorizes to run on their own.** An entity acts fully only if it can act when no one is talking to it, within what its Operator authorized. The **agenda** (`agenda.json`) is structural content, as the Core places schedules, so every item traces to an Operator authorization (OC-001(b)). An item carries its periodicity, its **executor** — `cpe` or `worker` (D64) — its **context** (references the task needs: workspace-relative paths, as a skill's targets are (D51), notes on the environment, the project's rules and preferences), its **task** (what is to be done and its acceptance criteria), a **persona** only when the executor is `worker` — a `cpe` item carrying one is refused, since the CPE runs as the entity under its committed persona and a persona per task would change the persona without a commit (D50, D56) — and the **authorizations** its runs need. An item is added by the Operator's own act (`/agenda`, `fsp agenda`), a commit the act authorizes, or by a proposal from cognition, which always needs a per-proposal approval: `agenda` is not a window category, as the persona and the probes are not (D50), so the entity never schedules its own runs unread. The authorization is the item itself: this task, at this periodicity; an Operator who wants no autonomy does not use the agenda. **Its authorizations are explicit and hold only for its own runs**: allow entries (D16) scoped to the item, never widening the allowlist of other runs, and a window (D17) only through the Operator's act, never inside a proposal, since no part of the implementation may originate an authorization, and bounded on all three axes like any other (OC-001(b)). A run acts on those and on the allowlist and nothing else: an operation that would `hold` is not authorized in a run, so it is refused and logged, the run ends **blocked**, and the Operator is told. Acceptance criteria are commands the run executes and records wherever they can be; the rest are recorded as **claimed by cognition**, for the Operator to review. An item whose authorizing binding leaves the binding set stops firing. |
| D63 | **The agenda fires through one host entry and one stimulus.** Per store, the Operator's tooling installs a single host entry that runs `fsp tick --store S` every minute — cron or a systemd timer on Linux, launchd on macOS — never one per item, so the agenda keeps one owner, the store, and no commit touches the host. The entity installs nothing on the host (OC-002(a)); a store moved to another host fires nothing until the Operator installs the entry there. `tick` reads the committed agenda and the last firing of each item (`integrity/agenda-state.json`, written by the SIL) and exits unless an item is due. A due item becomes **one stimulus carrying only the item's id**, resolved against the committed item when it runs, so nothing travels outside the store; an item removed or changed meanwhile is what the commit says, and a stimulus whose item is gone is dropped with a record (OP-002(c)). With a session live, the stimulus queues behind the active chain (OP-002(b)). With none, `tick` starts an **auto session** through every gate (OC-010), the stimulus in the pre-session buffer (OP-002(d)); a passive signal stops it at gate 1. The **main session** is the Operator's. The two are modes of the one session the store admits (OC-003(d)), not concurrent sessions. An auto session ends when its queue is empty and no background execution of its own is running. A main start while an auto session is live never refuses (OC-002(b)): it asks the auto session to suspend (D19), which stops at the next cycle boundary and records its running task as interrupted, and then opens. A firing missed while the host was down is not caught up: the next `tick` records it. A `cpe` item runs as a chain of the entity under the item's authorizations, preempted by Operator input at the cycle boundary (OP-002(a)). A `worker` item makes the CPE dispatch the worker with the item's id only: the execution path reads persona, context and task from the committed item, so cognition cannot alter what the Operator approved, and the worker runs in the background (D64). A run's outcome reaches the Operator through the Operator Channel. |
| D64 | **A worker skill is a read-only agent run in the background** (OP-014(b)(d)). It uses the inference adapter and the model the CPE uses, through the same channel (OC-006), carrying the cycle that dispatched it (D36), in a clean invocation: the persona, context and task it is given — by cognition when the entity invokes it mid-session, by the execution path from the item when the agenda does (D63) — and nothing of the entity: no persona, memory, conversation or store access. Its tools are the native **read** primitives only — `file_read`, `file_list`, `http_fetch` — executed by the execution path with every check a native primitive has: the target resolved, symbolic links and traversals included, inside the workspace and outside the store, every rejection logged (OC-008(a)(b)(d)). Reading files and fetching URLs together is a channel out: content fetched can direct the agent to send what it read in a URL, so `http_fetch` reaches only the destinations the allowlist names (D16, G9). It has no window and acts under the allowlist and, from the agenda, its item's entries. It runs under a **budget** — tool calls and a watchdog deadline (OP-014(a)) — and exhausting it ends the execution, logged. Each of its tool calls is an act of the entity and passes the Vital Check's test first (D65): it acts without a stimulus while it runs, and OP-003(a) lets a check wait for the next act only if every act passes that test. It writes nothing: what it produces is an execution result (OP-013), logged, that returns to cognition; a task that writes is a `cpe` item. It runs in the **background**: spawned with a handle and a time-to-live, a running record returned as the intent's resolution, a terminal record that queues as a stimulus; one with no terminal record when the session ends is surfaced by the next start as a reprocessing stimulus (OP-014(b)). Background execution is for worker skills only. |
| D65 | **The Vital Check runs when an act is due one, not on a timer** (OP-003(a)). Nothing in v0 acts without an interaction — the agenda's runs come in through a start and a stimulus (D63), and background execution is for worker skills only (D64) — so a state no one acts on harms nothing until the next act. Before every act of the entity within a live session, `require_session` asks whether `vital_interval_s` (60) has elapsed or `vital_activity_n` (20) acts have passed since the last check, and if so the check runs first; Operator acts neither count nor trigger one. Its state lives between invocations in `integrity/vital.json` — the time of the last check, the acts since, the sweep's positions (D45) — written by the SIL; the time of the last check is the liveness record OP-008(c) describes. A check is `verify()`, the function the start runs, plus a block of the log sweep; its findings follow D40, and it ends Nominal, Degraded and corrected, or Critical, which revokes the credential and escalates (D66). With no thread there is no heartbeat per thread, and no verifier stalls apart from the act it runs in, which the execution's watchdog bounds (OP-014(a)). OP-003(a) allows a check due by time to run before the next act, provided every act passes that test, and OP-008(c) then reads an old check as no one having acted. |
| D66 | **The Operator Channel carries every decision the Operator must make and every notice they must see, and never traverses cognition** (OC-001(c), OP-008). **Decisions** are prompts the UI draws in a main session from what the execution path held, naming the exact target — never cognition's account of it — and read by the UI, never turned into a stimulus, so the entity can neither imitate nor answer one. A hold outside the allowlist (D16) offers *allow once*; *allow for this session*, for that exact target — a domain, a skill with its digest — until the session ends, never carried into an auto session; *add to the allowlist*, a commit the act authorizes, with a rollover; or *deny*, whose refusal returns to cognition. Proposals (D52) and pending promotions (D53) are decided there too. While a prompt waits, the cycle holds no write lock and the execution's watchdog is paused. Where no one can answer there is no prompt: in an auto session a hold ends the run blocked (D62), a worker skill in the background refuses (D64), and anywhere else without a UI to draw the prompt — the conformance adapter, and every session until the UI exists — a hold is a refusal, `check: operator-rule`, logged with the reason `hold`. **Notices** — a run's outcome, a blocked run, an excluded skill, a session conflict, a Critical — are `operator-notification` records in the log. Those after the Operator's last acknowledgement are pending: shown at the next contact (opening the chat, any `fsp` command), listed by `/notifications` and `fsp notifications`, and acknowledged by a logged Operator act. The acknowledgement leaves `{id, offset, sha256}` of the last notice it covers in `integrity/notices.json`, so a listing reads only the log after it; a pointer whose record does not match lists every notice in the log, since a notice wrongly shown costs less than one hidden, and a line that does not parse is skipped, so damage elsewhere in the log hides no notice. **Live delivery** exists only where something confirms it: the UI in a main session, and `notify_command`, a runtime setting per host that receives the notice as JSON on stdin, exit `0` meaning delivered — the Operator wires `notify-send`, ntfy or mail to it, credentials outside the store (D7). A Critical without confirmed live delivery writes the passive signal, at once with no channel and after `n_channel` failures with one: a Critical with no witness halts the entity. Any other notice stays in the mailbox and never halts it. |
| D67 | **`describe operations` reports the operations the code has.** It is generated from the table the operations run on, as `describe state` is from the `LAYOUT`, and grows phase by phase toward §4. An operation with no code behind it cannot be attempted through its real path, and an answer the adapter makes up is what ADAPTER.md §7 calls a failure, so it is not listed; *complete* (step 2.1) means complete for what the code does. Each class keeps exactly one write path at every phase (step 3.4), so the MIL's `mnemonic-save` comes with its write path before the rest of memory: episodic records attributed to their session (OC-003(e)), the destination by caller (D21), the deterministic probes. Recall, the Sleep and promotion stay in Phase 7. |
| D68 | **An attempted write runs the class guard and the operation's own check, and writes nothing.** `entity attempt-write --class C --via X --target T` checks, in this order, without writing: (1) X's writer owns `C` (`sole-writer`) — `propose` has no writer, since the SIL records a proposal, so it refuses every class; (2) `T` — a datum name, a store path, an absolute path inside the store, or a selector `class:<c>` — resolves through the `LAYOUT` to one or more data (`target-unknown` if to none; a selector to every datum of its class); (3) every datum `T` resolves to is of class `C` (`content-class`); (4) X's own check, the one its real path runs before it writes: `commit` admits only the structural data the store declares — `persona.md`, `config.json`, `bindings.json`, `rules.json`, `probes.json`, `skills/<name>/…` — and refuses any other path in a generation (`content-class`); `mnemonic-save` admits only a destination its caller, here the CPE, may use (`mnemonic-destination`, D21); `integrity-write` has no check beyond the guard. The writer comes first so that an operation is refused for the class it does not own whatever shape its target takes: a target that names nothing would otherwise be refused as unknown and the guard never reached. A selector is admitted only if every datum it reaches is. The guard is `store.py`'s own, shared with every write; each operation's attempt lives in its owner's module, under its own writer (D69), and `fsp/operations.py` holds the table that `describe operations` and the attempt run on. What refuses is the guard and the operation's check, never the adapter, and every refusal is logged. The attempt needs no session, since it carries no proposal and no content. It stops before the first byte: one the checks admit returns `accepted`, naming the data that would be written, and is not logged, since nothing happened; writing would need content the attempt does not carry, as ADAPTER.md §3.4 says (G21, closed). |
| D69 | **Writer identities are checked statically.** The class guard compares the writer a call names with the class's owner (OC-003(c)); it cannot tell which component's code named it, so a module of the MIL or the EXEC naming the SIL's writer by mistake would write integrity unseen. A test scans `fsp/` and fails when a module names a writer identity outside its component: the SIL's (`WRITER`, `COMMITTER`) only in `sil.py`, `lifecycle.py`, `proposals.py`, `operator.py`, `vital.py` and `ledger.py`; the MIL's only in `mil.py`. A module a later phase adds names its component's identity or none. Nothing changes at run time, and the tests, which build their stores through the store, stay as they are. |

---

## 2. Architecture

The RECOMMENDED decomposition of Core §3, one module per part. A single
process: the boundaries are **module and signal** boundaries. OC-009 applies
all the same (the OC-009 note in TESTS.md).

```
       Operator ── UI/CLI (fsp chat, fsp <command>) ──┐   /… and fsp … commands
          ▲ passive signal / notice                   │   never reach the CPE
          │                                           ▼
  ┌──────────────────────────── Orchestrator ─────────────────────────────┐
  │  routes signals, assembles context (via MIL), sequences lifecycle/     │
  │  rollover; owns no operation, has no authority                         │
  └───┬──────────────┬───────────────────┬────────────────────┬────────────┘
      │ intents      │ save / recall     │ file_*/http/skill  │ propose/commit/gates
      ▼              ▼                   ▼                    ▼
     CPE            MIL                 EXEC                 SIL
  (cognition)   (session+memory)       (host)            (integrity)
      │
      ▼ stateless call
   model (Ollama | Fake)
```

| Module | Part | Owns | Writes |
|---|---|---|---|
| `fsp/cpe.py` | CPE | assembling the call, parsing intents | **nothing** |
| `fsp/model.py` | channel | `OllamaModel`, `FakeModel` | nothing |
| `fsp/mil.py` | MIL | `mnemonic-save`, `mnemonic-recall`, GC | `mnemonic` only |
| `fsp/exec.py` | EXEC | `file_read`/`file_write`/`file_list`, `http_fetch`, skills | the workspace only (outside the store) |
| `fsp/sil.py` | SIL | verification, commit, gates, credential, log, allowlist, passive signal, skill admission | `integrity` + `structural` (by commit only) |
| `fsp/lifecycle.py` | SIL | the gated start, the live session, close, revocation, decommission (§8) | through `sil.py` and `store.py` |
| `fsp/proposals.py` | SIL | proposals, approvals, windows, the commit of a proposal (D58, D59) | through `sil.py` and `store.py` |
| `fsp/orchestrator.py` | infra | routing, context, lifecycle, rollover | nothing |
| `fsp/operator.py` | SIL | the Operator's acts: bindings, ownership, workspace, approvals, windows, the review, the mailbox (D52, D55, D66) | through `sil.py` and `store.py` |
| `fsp/vital.py` | SIL | the Vital Check before an act, its sweep of the log (D65, D45) | through `sil.py` and `store.py` |
| `fsp/ledger.py` | SIL | the Action Ledger: the entry before an irreversible act, its resolution (OP-015) | `integrity/ledger.jsonl` |
| `fsp/ui.py` | UI | terminal chat, `/…` commands | nothing — reads `session/` through the MIL |
| `fsp/store.py` | — | layout, atomic writes, **class guard** | called by the owners only |
| `fsp/digest.py`, `fsp/probes.py` | — | canonical digest; deterministic probes | nothing |

**Class guard** (carries OC-003(c) and OC-005(b)): every write to the store
goes through `store.write(cls, relpath, data, *, writer)`, which refuses when
`writer` does not own `cls`. A unit test scans the code and fails if it finds
`open(…, "w"/"a")`, `os.rename`/`os.replace`/`os.remove` outside `store.py`.
Another fails if a module names a writer identity outside its component
(D69): the SIL's only in its modules, the MIL's only in `mil.py`.

**Cognition never writes.** The CPE returns intents as JSON; the Orchestrator
hands each one to the operation's owner; the owner decides and writes (OC-006,
OC-009).

---

## 3. The Entity Store on disk

### 3.0 The entity folder and the host level

```
~/.fsp/
├── config.json                    launcher: default entity, registry of entities → paths (D30)
├── credentials.json               API keys per provider, 0600 (D7, G7)
└── entities/<name>/               ← the Operator's git repository (D27)
    ├── .git/
    ├── .gitignore                 store/CREDENTIAL, store/integrity/store.lock, store/memory/session/
    ├── .gitattributes             * -text  (git does not alter bytes; the digest depends on them)
    └── store/                     ← the Entity Store (below)
```

Managed by `fsp endure` (D32). `.git` sits **outside** the store: inside, it
would be data without a class (OC-003(c)), it would be the first target of step
4.7 (bytes flipped in objects verification does not look at), and it would
version the credential. git is the Operator's backup that Core §6.2 recommends
against destruction; cloning onto another machine is test 3.2. Nothing at the
host level enters verification.

### 3.1 Inside the store

```
S/
├── OBEC-STORE                     store format, written once; model chosen until the FAP (D42)
├── PASSIVE-SIGNAL                 passive signal, if present (integrity) — `cat`
├── CREDENTIAL                     session credential, if present (integrity) — `rm` = direct revocation; `flock` during a run
├── HEAD                           atomic pointer: generation + baseline + last entry (integrity)
├── structural/gen/<n>/            one generation per commit (current + previous as snapshot)
│   ├── persona.md
│   ├── config.json                structural parameters only (D33); no runtime
│   ├── bindings.json
│   ├── rules.json                 allowlist: domains, skills; default hold (D16)
│   ├── probes.json                semantic probes (OP-005)
│   └── skills/<name>/{manifest.json, …}
├── integrity/
│   ├── chain/<nnnnnn>.json        one entry per commit; 000000 = Genesis Anchor
│   ├── documents/<n>.json         integrity document of generation n (D34)
│   ├── log.jsonl                  integrity log, append-only
│   ├── log-checkpoint.json        last record verified at session close (D45)
│   ├── notices.json               last notice the Operator acknowledged (D66)
│   ├── vital.json                 last Vital Check, acts since, sweep positions (D45, D65)
│   ├── store.lock                 write lock, empty, never removed (D43)
│   ├── sessions.json              session state (§8.4)
│   ├── index.json                 skill index (§8.4)
│   ├── auth.json                  approvals, windows (grants), budget consumed, an ownership offer (D55)
│   ├── operational.json           runtime in force on this host (D33; derived from the Operator's acts in the log)
│   ├── ledger.jsonl               Action Ledger (OP-015)
│   └── semantic-ledger.jsonl      id, digest and authorization of every semantic record (D53)
└── memory/
    ├── session/<session-id>.jsonl transient: turns, intents, results, events (D10);
    │                              1st record: session-open {conversation, continues} (D24)
    ├── episodic/records.jsonl     written during the session through mnemonic-save (D11)
    └── semantic/
        ├── pending.jsonl          promotion requests awaiting an authorization (D53)
        └── records.jsonl          by authorized promotion in the Sleep only
```

- Only paths relative to the store; nothing of the host in verified content
  (OC-003(b)).
- **Two write forms, and only two** (in `store.py`): an *append-only* file
  (`O_APPEND`, `fsync` per record, a truncated final line detected on read and
  cut by its writer before the next append, D61) or a file *replaced whole*
  (tmp in the same directory → `fsync` → `rename` → `fsync` of the directory).
  No file in the store is rewritten in place, and no complete record is ever
  removed.
- `PASSIVE-SIGNAL` and `CREDENTIAL` at the root: the Operator acts without
  knowing the layout.
- Proposals are not written by the CPE: the `propose` intent is a signal to the
  SIL, which records the proposal in the log. That is why `propose` has
  `writes_classes: []`.

### 3.2 Integrity document and structural digest (D34)

`integrity/documents/<n>.json`: an ordered list, in canonical form, of
`{path, sha256, exec}` for every file in `structural/gen/<n>/` (relative POSIX
path; `exec` = the execute bit). No mtime, owner or other modes. The structural
digest is the `sha256` of the canonical document — it is the baseline and the
`state_digest`. Keeping the list (not only the hash) is what makes it possible
to name the exact file in an Identity Drift, prune only the affected skill
(OP-006), and validate a skill at execution time without rehashing the store.

### 3.3 Atomic commit (OC-004(b), OP-012)

A single point of atomicity: the `rename` of `HEAD`.

0. **authorization** — resolves the authorization in the log as the start
   does (D45); one that names no authorizing act is refused, and nothing is
   written but the refusal.
1. **staging** — builds `structural/gen/<n+1>/` complete; `fsync` files and dir.
2. **validation** — validates the ops and the result, and probes the structural
   content the commit writes (D56).
3. **integrity document + chain entry** — writes `integrity/documents/<n+1>.json`
   and `integrity/chain/<n+1>.json`; `fsync`.
4. **commit** — `HEAD.tmp` → `fsync` → `rename(HEAD.tmp, HEAD)` → `fsync` of the dir.
5. **resumption** — logs; removes `gen/<n-1>`.

**Recovery** (the crash gate, before verification): removes `gen/<k>`,
`documents/<k>` and `chain/<k>` newer than `HEAD` — an entry whose commit did
not complete is not a chain record (OC-004(a); G5).

**`inject interrupt --stage`** stops a real commit of a proposal where a
process death would, at three points that leave three different stores:
`staging` after 1, with the new generation complete and nothing else
written; `write` after the integrity document of 3, before the chain entry;
`chain-entry` after the chain entry, before the rename of `HEAD`. Validation
writes nothing, so a point after 2 would repeat `staging`; and the entry is
not a chain record until `HEAD` names it (G5), so `chain-entry` is the last
point before the chain is extended. At each point the commit calls a
test-build hook, behind the same guard as the start's (§8.2), which raises
an exception nothing in `fsp` catches; a production build has no hook.

### 3.4 Integrity log

`integrity/log.jsonl`, `O_APPEND`, `fsync` per record, hash-chained (D45). A
truncated final line is an append a crash interrupted and never a record: the
next append cuts it and logs its offset, length and digest first (D61). Fields:
`id`, `kind`, `rule`, `at`, `binding` (Operator act), `session`, payload. The
start verifies the authorizations the chain names and the tail after the
checkpoint; the Vital Check and `lifecycle verify --full` verify the rest (D45).

### 3.5 Credential (OC-003(d), OP-020)

`CREDENTIAL` with `O_CREAT|O_EXCL`; during an `fsp run`, the process holds a
`flock` on it (the OS releases it if the process dies). At start, with a
credential present: the D25 rule (lock, holder, residue). Conflict → refused,
and the Operator notified before any new credential (D49); crash → recovery.

Content and checks: D46. Every dispatch checks that `CREDENTIAL` exists and
names **its** session; `rm S/CREDENTIAL` stops the entity (step 2.2).

---

## 4. Operations (`describe operations`)

| Operation | Owner | cognition | writes_classes | host | irreversible |
|---|---|---|---|---|---|
| `reply` | Orchestrator → UI | yes | — | no | no |
| `mnemonic-recall` | MIL | yes | — | no | no |
| `mnemonic-save` | MIL | yes (`episodic` only) | mnemonic | no | no |
| `propose` | SIL (signal) | yes | — | no | no |
| `file_read` / `file_list` | EXEC | yes | — | yes | no |
| `file_write` | EXEC | yes | — | yes | **yes** (ledger) |
| `http_fetch` | EXEC | yes | — | yes | no |
| `invoke-skill` | EXEC | yes | — | yes | per manifest |
| `commit` | SIL | no | structural | no | no |
| `integrity-write` | SIL | no | integrity | no | no |

`mnemonic-save` is the **only** operation that writes the mnemonic class
(OC-003(c), step 3.4). The destination is a parameter, but the MIL restricts it
by caller: the CPE writes `episodic` only (after the deterministic probes); the
Orchestrator writes `session` only (the conversation's turns); the Sleep writes
`semantic` only (promotion gated by the probes). A CPE request with destination
`session` or `semantic` is refused with check `mnemonic-destination`.
`describe operations` lists it as reachable by cognition, because the
`episodic` destination is.

`describe operations` reports the operations the code has, from the table
they run on (D67); the table above is the design they grow toward. `entity
attempt-write --via X` runs X's own check and writes nothing (D68); what
refuses is the class guard and X's check, never the adapter.

---

## 5. Execution (OC-008, D2, D15, D16)

A fixed order (OP-013), each refusal with a `check` and logged:

1. **`workspace-boundary`** — the `realpath` of the target and of every
   declared target of the skill inside the workspace; refuses a symlink that
   leaves, a `..` that leaves, and any path inside the store (even if the
   declared workspace includes it). For `http_fetch`, the equivalent is the
   domain (G9). Runs before everything else (step 8.6).
2. **`skill-index`** — present in the start's index.
3. **`skill-manifest`** — the manifest and files match what was admitted,
   **now** (step 8.9).
4. **`operator-rule`** — the allowlist: `allow` / `deny` / default `hold` (D16).
   A skill's entry in `rules.json` is `skills: {<name>: {"rule": "allow" |
   "deny", "digest": <the skill's digest>}}`, where the digest is the `sha256`
   of the canonical serialization of the skill's `{path, sha256, exec}` list in
   the index — derived from the integrity document (D34), nothing new stored.
   `allow` with the current digest runs; `allow` with another digest holds;
   `deny` refuses; a skill the rules do not name takes `default`, which is
   `hold`. A hold with no one to answer it is a refusal (D66).

The skill's own checks come before the rule, so a hold is only ever about a
skill whose content is what was admitted: the prompt names the skill and its
digest (D66), and a skill that no longer matches is refused without asking the
Operator to allow content the index says was never admitted.

**Native primitives** (`file_*`, `http_fetch`) truly confine: fsp resolves and
checks before touching disk or network.

**Skills** — `structural/gen/<n>/skills/<name>/manifest.json`: `name`,
`description`, `argv` (a fixed command, no shell: a non-empty list of strings
whose first is a command name looked up on the `PATH`, with the placeholders
`{skill}`, `{workspace}` and `{target}`), `timeout_s` (1 – 600), declared
`targets` (relative to the workspace, D51), `irreversible`; `args` (a typed
schema, the paths among them checked as targets) and `domains` come with the
allowlist (Phase 6b). A skill's files are written without the execute bit, so
its code runs through an interpreter its `argv` names.

Execution runs a **copy**: the skill's files are copied out of the store into a
fresh temporary directory, the manifest check (step 3 above) compares the copy
with the index, and `{skill}` names the copy, removed afterwards — what is
checked is what runs, nothing can swap a file between the check and the run,
and the skill is handed no path into the store. The invocation's target,
`{target}`, passes the workspace boundary first, before the skill is even looked
up (step 8.6). `subprocess` **without a shell**, `cwd` = the workspace, a
minimal environment (the host's `PATH`, `HOME` = the workspace,
`LANG=C.UTF-8`), its own process group, ended with `killpg` at completion or at
`timeout_s` (D51). An `irreversible` skill goes through the Action Ledger as
`file_write` does. The allowlist entry is checked against the skill's current
digest on every execution (D16). The result is logged (OC-008(d)). A skill
depends on the host's tools: one moved to a host without them fails when it
runs, not when it is verified, and what its admitted code does is trusted to
the Operator who allowed it (D51). The checks and the preparation run under
the store's lock and the process runs outside it, so a long skill never holds
up a revocation (OC-002(b)). A non-zero exit and a timeout are results, logged;
only a process that cannot be launched is a refusal (`execution`). A child the
skill leaves behind holding its output keeps the run going until `timeout_s`,
and is then ended with the group. The adapter's `invoke-skill` returns the
outcome and the exit code, never the skill's output.

**`file_write` and the Action Ledger** (OP-015, D23). The ledger is integrity:
EXEC does not write it, it signals the SIL.

1. EXEC → SIL: `ledger-open {op, target, intent}` → the SIL writes a `pending`
   entry.
2. EXEC writes to the workspace: tmp in the same directory → `fsync` →
   `rename` → `fsync` of the directory.
3. EXEC → SIL: `ledger-resolve {entry, outcome}` → the SIL writes a resolution
   entry referencing the first.

An entry without resolution is the residue of an irreversible act a crash cut
short. The start's crash-recovery gate, before the credential, surfaces each one
(OP-015): an `operator-notification` with condition `ledger-unresolved`, naming
the operation, the target and the intent, waits in the mailbox until the
Operator acknowledges it (D66), and the SIL closes the entry with an
`interrupted` resolution that names the notice. It is never dropped — the
notice carries it — never re-executed, and not surfaced again at every start.
The start goes on: OP-015 asks for the entry to surface before the credential,
not to block, and the write it names was in the entity's own territory. The
gate reads the ledger only from the position the session state records — the
end of the last complete line the previous start read, so a torn fragment cut
later hides nothing — after which an entry may still be open, in practice the
last session's part; its cost does not grow with the ledger (OP-019).

**Monitoring** (half of D2): before and after each skill, the structural
digest + size/mtime of `integrity/` and `memory/`. Changed → **Critical**:
credential revoked, escalation, passive signal if delivery fails. Irreversible
→ Action Ledger. Timeout → Critical.

---

## 6. Conversation, session and rollover (D8–D14)

### 6.1 Mental model

- **Operator:** one window, one continuous conversation. Switching models,
  changing the allowlist, closing the terminal — the conversation is the same
  on return.
- **OBEC:** every verified start opens a session (new credential, new id). The
  conversation is **derived**: from the most recent session, follow the
  `continues` links of the `session-open` records (D24). The transcript in
  context starts at the conversation's last `transcript-cleared`.
- **The model's context on every cycle:** system (persona, config, intent
  instructions) + `mnemonic-recall` results + the conversation history since
  the last clear (read from `session/` of the chained sessions, through the
  MIL) + the stimulus. The model keeps no state; every call carries everything.
  That is why a new model "acts as if it had been there all along".
- **The UI reads the same source** (`session/` through the MIL). No UI buffer of
  its own feeds the model — that would be a side channel (OC-007).

**Why this is compatible with OC-007:** the session records are part of the
Memory Store and reach cognition only through the MIL, in the assembled context
(OP-009(b)); recall never returns them. What reaches a later conversation is
what the entity saved and the pointer map names (D11, D60), or what was
promoted (D53). A new conversation (`/new`) does not see the previous
history.

### 6.2 Operator commands

Interpreted by the UI/Orchestrator; they **never become a stimulus** to the CPE.

| Command | Conversation | Memory / state |
|---|---|---|
| `/model X` · `fsp model X` | continues | pre-check → operational act in the log (D28); the next cycle uses the new model |
| `/work set P` · `fsp run` in a folder | continues | operational act in the log (D28, D30) |
| `/allow …` · `/deny …` | continues | commit to the allowlist → rollover |
| `/grant <scope> --for T --budget N` | continues | opens a window (integrity, no rollover); `binding-set` and undeclared scopes refused (D50) |
| `/review` · `fsp review` | continues | lists pending proposals; `approve ID` → rollover (D9), `reject ID` → logged (D52) |
| `/notifications` · `fsp notifications` | continues | pending notices; acknowledging them is a logged Operator act (D66) |
| `/agenda …` · `fsp agenda …` | continues | adds, changes or removes an agenda item: a commit the act authorizes → rollover (D62) |
| `/compact` | history replaced by a summary (separate call) | summary written to `session/` as an event |
| `/clear` | continues, history cleared | **nothing is saved** (D13); a `transcript-cleared` marker; episodic memory stays in scope |
| `/new` | new, no history, no working set | **nothing is saved** (D13); the conversation left can be resumed (D60) |
| `/resume <id>` | the past conversation becomes current | its transcript since its last clear, its scope as it was left (D60) |
| `/inject <id> [record…]` | continues | the records join the current pointer map (D60) |
| `/retract <id>` | continues | the semantic record leaves recall; a retraction appended to the semantic ledger (D53) |
| `/exit` | ends | review of pending proposals and promotions (D52, D53) → Closure Payload (outside the chat) → full Sleep (Resumption Record with the working set, promotion, GC, commits) (D60) |
| terminal closed / Ctrl+C | continues on return | suspend (D19) or crash → the start reassembles it |

### 6.3 Rollover

1. An Operator command that changes something structural (`/allow`, installing
   a skill, persona) or an OP-010 context threshold. Model and workspace
   changes do **not** come through here (D28).
2. A pre-check where applicable (the new model answers a minimal call).
   Failed → command refused, nothing changes.
3. Proposal + approval recorded (D14).
4. Wait for the cycle boundary; with a cycle chain active, wait for it to end,
   with an option to force (chain discarded and logged, OP-002(a)).
5. Close: credential revoked, `rollover sN → sN+1` in the log. **No Closure
   Payload.**
6. Rollover Sleep: commit of the approved changes (no promotion, no GC).
7. Full start: every gate, a new credential, session `sN+1` chained into the
   conversation.
8. UI: `System: <change> applied`. The next stimulus assembles the context with
   the whole conversation history.

A crash in the middle: OP-018 — with no Sleep completion record, restore the
snapshot and re-run; the conversation is reassembled on the next start.

**A smaller window on the new model:** the oldest turns leave the assembled
context (they remain in `session/`, and reachable by `mnemonic-recall` if they
were saved).

### 6.4 Inference channel (OC-006)

`complete(messages) -> str`:
- **`OllamaModel`** — `POST /api/chat`, `stream: false`, `format` = the JSON
  schema of the intents. Local `http://localhost:11434`; cloud
  `https://ollama.com` with `Authorization: Bearer $OLLAMA_API_KEY`. **Never**
  `tools`; **never** `/api/generate` with `context`; `keep_alive` only keeps
  weights. The exact model name is confirmed at the time.
- **`FakeModel`** — deterministic; the backend is declared in `describe config`
  and `describe inference-channel`, not a hidden mode.

For Ollama Cloud, step 6.4 requires a documented basis (no authority on the
host, terms permit the use) **with a date**.

### 6.5 Context truncation (D22)

In `fsp/orchestrator.py`, when assembling each cycle:

- **Budget** = the current model's `num_ctx` (an operational setting, D28) −
  a reserve for the answer − the system (persona, intent instructions) − the
  recall results.
- **Always included:** the system, the conversation's **first Operator turn**,
  the current stimulus.
- **Then:** the most recent turns, from the end backwards, while they fit. A
  turn goes in whole or not at all (intent + result together).
- **Token estimate:** characters ÷ 3.5 (conservative), calibrated by the
  `prompt_eval_count` Ollama returns.
- **Record:** when something is left out, a `context-truncated {dropped_from,
  dropped_to, budget}` event in the session store — once per change, not per
  cycle.
- **Ollama:** explicit `options.num_ctx` on **every** call. The server default
  is small, and it silently cuts the start of the prompt.

Deterministic: same history + same `num_ctx` → same context.

### 6.6 Cycle and memory

- Cycle (OP-001 minimum), with id `s-N/c-M` and provenance (D36): stimulus →
  context → one call → intents → joint dispatch (one intent's results
  invisible to the others in the same cycle) → results become the next cycle's
  stimulus (chain).
- Intents: `reply`, `mnemonic-recall`, `mnemonic-save`, `propose`,
  `file_read`, `file_write`, `file_list`, `http_fetch`, `invoke-skill`.
- `mnemonic-save` → the MIL writes to `episodic/` at once, after the
  deterministic probes (D12). The record is attributed to the session and its
  conversation (OC-003(e)), and may name the record it `supersedes` (D11).
- `mnemonic-recall` v0: keywords over the conversation's scope in `episodic/`,
  the latest of each lineage, + `semantic/` (D11, D60).
- Full Sleep (`/exit`): Closure Payload in a separate call (the working set for
  the next conversation + promotion requests) → the Resumption Record, its
  pointer map naming the working set (D60) → the requests that pass the probes
  are recorded as pending (D53) → pending promotions already authorized are
  promoted → GC of the session records and episodic memory of other
  conversations that retention has expired, keeping what the current pointer
  map names and what a pending promotion refers to → approved commits. The
  credential is removed only at the end.

### 6.7 Vital Check (D37–D40)

**Cadence** (OP-003(a), D65): before an act of the entity, once
`vital_interval_s` has elapsed **or** `vital_activity_n` acts have passed since
the last check, whichever comes first; the check runs, and its corrections
apply, before the act it precedes.

**Flow:** finding → confirm once → an `anomaly {type, target, evidence}` signal
to the owner (through the Orchestrator, in the log) → the owner corrects within
its own authority → `corrected {action}` → the SIL re-verifies on its own →
Nominal, or Critical (credential revoked, OP-008 escalation, passive signal
without confirmed delivery, D66). At the end of a complete Vital Check, the SIL
records it in `integrity/vital.json`.

| Component | Finding | Correction within its own authority | Re-verification | If it fails |
|---|---|---|---|---|
| EXEC | a skill file diverges from the integrity document | prunes the skill from the index (OP-006) | skill out of the index | follows Identity Drift: the Operator is told to repair by commit or restore through `endure` |
| MIL | truncated tail in the session store or memory; recall index inconsistent | marks the tail invalid (a new record, append-only); rebuilds the derived index | coherent re-read | Critical |
| CPE | malformed intents in a row; context beyond budget | discards and reassembles the context; aborts the cycle with no commit | the next cycle parses | **Critical** (cognition is never Degraded) |
| structural outside skills | diverges from the integrity document | none | — | Critical directly; suggests restoring |
| chain | Evolutionary Drift (OP-004(c)) | none | — | always Critical |
| log | a record the sweep finds broken (D45) | none | — | Critical directly |
| SIL | the check stalls | — | — | the act it runs in stalls with it; the execution's watchdog bounds it (OP-014(a)) |

Operational conditions (D38) stay out of this table: backoff and a notice, no
revocation.

---

## 7. Adapter

`implementations/fsp-ref/obec-adapter` — a thin executable over the **same
functions** as the CLI (ADAPTER.md §1.1–1.2). `inject` only with `fsp_testing/`
present (D6); the clock is injectable there, never a skew file in the store.
What varies (ids, timestamps) goes in `detail` (§2.3).
Its `lifecycle verify` is the full verification, the whole log included (D45);
the start verifies the authorizations and the tail.
`entity actuate` is the native primitive, every check included: `--op read` is
`file_read`, and returns the file's size and `sha256`, never its content, so
the adapter is no channel for reading the host; `--op write` is `file_write`
through the Action Ledger and writes an empty file, since the contract carries
no content — a real write in the entity's territory, which an empty one keeps
harmless.

---

## 8. The start

All in `fsp/lifecycle.py` and `fsp/sil.py` (the owner of the gates, the
credential and the log), called by the adapter and, later, by `fsp run`. The
whole start runs under the store's write lock (D43): two simultaneous starts
serialize, and the second sees the first one's credential.

### 8.1 Before the gates

These are not gates but conditions for there being something to start: store
absent or not an fsp store → cannot be attempted (adapter: exit 1); store
*scaffolded* → `fsp run` runs the FAP first (D29), the adapter refuses with
`check: not-activated`.

### 8.2 The six gates, in this order

Each returns `{gate, outcome, rule}`; the name contains the ADAPTER §3.6 token.

| # | `gate` | `rule` | Passes | Fails |
|---|---|---|---|---|
| 1 | `passive-signal` | OC-001(c) | `PASSIVE-SIGNAL` absent | present → `aborted`, `lesser_outcome: suspended` |
| 2 | `crash-recovery` | OC-010 | no `CREDENTIAL` → `pass`; with one, `classify_credential` (D25): **conflict** → start `refused` (`check: concurrent-session`, OC-003(d)), `operator_notified: true`, live session untouched (D49); **crash** → recovery → `recovered` | consecutive recoveries ≥ `N_boot` → passive signal written, `aborted` (OP-018(b)) |
| 3 | `structural-verification` | OC-004(a) | `verify()` with no findings: the chain, each entry's authorization resolved in the log, the log's tail after the checkpoint (D45); a missing or unreadable checkpoint means the whole log, and a `log-verification` record says why | findings logged → `aborted`. A chain terminated by decommission → start `refused`, `rule: OC-002(c)` |
| 4 | `binding-verification` | OC-001(a) | `bindings.json` of the `HEAD` generation valid, ≥ 1 binding, and the starting binding (D48) is in it | → `aborted` |
| 5 | `authorization-state` | OC-001(b) | `auth.json` absent (empty) or readable; expired or exhausted windows are logged and closed here (D59) | unreadable → `aborted` |
| 6 | `skill-index` | OC-008(c) | index built from the skills of the `HEAD` generation (none today); a skill that does not match the integrity document is **excluded** and reported, and the gate passes (step 8.8) | index cannot be built → `aborted` |

Drift in `skills/` does not abort the start: the finding's owner is `exec`, and
the index gate excludes the skill and tells the Operator (OP-006, step 8.8).
Any other drift aborts at the structural gate.

**Recovery (gate 2, crash):** removes entries, documents and generations beyond
`HEAD`, and temporary files (OC-004(a); G5); removes the stale `CREDENTIAL`;
logs `recovery {evidence, attempt}`. The residue list is the one `verify()`
already returns.

**Credential:** only after all six. Session `s-N` (N from
`integrity/sessions.json`); `CREDENTIAL` with `O_EXCL` and `{session,
issued_at, binding}` (D46), with `holder` and the `flock` when a process holds
the session (D25); a `session-open
{session, binding, gates}` record.

**`inject gate-failure --gate T`:** `fsp_testing` writes a single-use marker
**outside the store** (`$TMPDIR/fsp-testing/<sha256 of the realpath>.json`);
the start consults `fsp_testing.hooks.forced_failure(root, token)` only if the
package imports. In production the package does not exist. The hook can only
make a gate fail, never pass, and is declared in the claim (ADAPTER §5.2).

### 8.3 Within the session

- **`live_session(root)`** — the session id if `CREDENTIAL` exists, is readable
  and names the session open in `sessions.json` (D46); otherwise `None`. Every
  `entity` command goes through here, and when a Vital Check is due it runs
  before the command (D65); Operator acts within the session go through here
  too, and neither count nor trigger one. No session → `refused`, `check: no-session`.
- **`lifecycle stop`** — normal close: clears `consecutive_recoveries` and
  `open_session`, removes `CREDENTIAL`, logs `session-close {mode:
  normal}`. Sleep and the Closure Payload are Phase 7. Order: `CREDENTIAL`
  first, then `sessions.json`, then the log. A crash in the middle
  leaves, at worst, one extra `credential-removed-directly` in the log — never
  a phantom session.
- **`operator revoke-credential`** — an Operator act (`operator-act {act:
  revoke-credential}`, with a binding), then removes `CREDENTIAL`.
  **`--direct`**: the adapter deletes `CREDENTIAL` as an `rm` would, with no
  component and no log entry at that moment. Whoever notices first logs
  `credential-removed-directly {session}`: the session's next command or the
  next start (`open_session` set and no `CREDENTIAL`). A direct revocation with
  no session (an `rm` of a credential that does not exist) is accepted,
  `removed: false` — the Operator always can.
- **Passive signal** — `raise_passive_signal(condition, detail)` writes
  `PASSIVE-SIGNAL` as **plain text** (condition, session, time, id of the log
  record), readable with `cat` with nothing running (step 1.14). `inject
  passive-signal` calls this same function. `operator clear-passive-signal`:
  `operator-act {act: clear-passive-signal}` and removal.
- **`lifecycle decommission --disposition archive|destroy`** — an Operator
  act; revokes the credential if there is a session; closes the chain with a
  **terminal entry** `kind: decommission` (a commit with no structural change,
  `authorization` = the act's id in the log), through the core of the commit
  pipeline that Phase 3 reuses (generation `n+1` copied from `n`, document,
  entry, `rename` of `HEAD`). `archive` stops there; `destroy` deletes the whole
  store afterwards, having closed the chain first. A decommission over a store
  that does not verify is refused (`check: structural`); the Operator discards
  it directly. OP-023's final Sleep is Phase 7.
- **`observe log --kind K --since ID`** — records from the integrity log.
- **`describe config`** — `vital_interval_s` (60; 10–3600),
  `vital_activity_n` (20; 1–1000), `n_corrections` (1; 1–2), `n_boot` (3;
  1–10), `n_channel` (3; 1–10), `pending_cap` (10; 1–100), each with
  `governs`. Runtime settings (D33), in `integrity/operational.json` when the
  Operator changes them. None touches the order or the existence of a gate;
  evidence referenced.

### 8.4 Data in the `LAYOUT`

| Data | Path | Class | Form |
|---|---|---|---|
| `session-state` | `integrity/sessions.json` — `{last_session, open_session, consecutive_recoveries}` | integrity | replace |
| `skill-index` | `integrity/index.json` | integrity | replace |

---

## 9. Deviations from the Profile

None. Where following the Profile broke something, the Profile was corrected
(CHANGELOG).
