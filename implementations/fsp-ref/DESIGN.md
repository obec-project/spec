# fsp-ref — design

The architecture of fsp-ref and the decisions in force, with the reason for
each. A decision that is replaced leaves this file and is recorded in
[CHANGELOG.md](CHANGELOG.md). What is still to be built is in
[BACKLOG.md](BACKLOG.md).

**fsp-ref** — *Filesystem Substrate Platform*, the reference implementation of
OBEC-Core 0.9.1 over a filesystem and POSIX primitives. A future `dbsp-ref`
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
| D1 | **Python, standard library only**, POSIX (Linux/macOS). Floor 3.9. No Windows. |
| D2 | **Skill confinement comes from admission and monitoring**: a commit authorized by the Operator, the Skill Index, manifest validation at execution time, typed arguments, declared targets checked against the workspace, execution logged and observed. No confinement by the OS. The revision of OC-008(a) this requires is **clarifying** (G1). |
| D3 | **The model through the Ollama API** (local `gemma4` or Ollama Cloud) + a **deterministic fake model** for the suite and the tests. |
| D4 | Name **`fsp-ref`**, in `implementations/fsp-ref/`. |
| D5 | The runner and fsp-ref are both Python; **neither imports code from the other** (G3). |
| D6 | **`inject` exists only in the `fsp_testing/` package**; a production build is the package absent → exit 2. Nothing else. |
| D7 | API keys live in `~/.fsp/credentials.json` (0600), never in the entity's folder (G7). |
| D8 | **A conversation is not a session.** The conversation is what the Operator sees: one window, continuous, cleared only when they ask. An OBEC session is the life of one credential. A conversation spans sessions. (§6) |
| D9 | **Rollover**: the single "apply now" mechanism for a **structural** change (allowlist, skill, persona, probes): Sleep + a full start, transparent, no Closure Payload, conversation preserved. Model and workspace do **not** need it (D28). (§6.3) |
| D10 | **The session store** (`memory/session/<id>.jsonl`, append-only, transient) is the single source for the UI **and** for context assembly. Owner: MIL. |
| D11 | **Episodic memory is written during the session**, freely, by the CPE signalling the MIL (`mnemonic-save`). **Only promotion from episodic to semantic goes through the Sleep**, gated by the probes. (G10) |
| D12 | **Deterministic probes run on every episodic write** (regex, negligible cost) and on promotion. |
| D13 | **`/clear` clears without saving.** If the Operator wants something kept, they ask the entity first. |
| D14 | **An Operator act is already an approval.** For a structural change (e.g. `/allow`), the command records proposal + approval in one act, through the Operator's channel. Text in the chat is never a command: `/…` is interpreted before the CPE. |
| D15 | **The CPE has no shell.** Reading and writing only through native `file_read`/`file_write`/`file_list` (real confinement); network only through native `http_fetch`; any command becomes a **skill** with a fixed `argv` and typed arguments. |
| D16 | **Allowlist** (OP-016 rules, for CPE intents only) = **domains** (`http_fetch`) + **skills** (execution). Outside the allowlist: **`hold`** (ask the Operator). |
| D17 | **Approval window** = a standing grant by scope, for a structural change of any kind. Always with expiry, budget and scope (OC-002(b)); the UI warns before it closes, and only the Operator renews it. Personal companion: a wide, long window. Company: never opened. |
| D18 | The second host for step 3.2: **a VM or a real remote machine**, never a container on the same host. |
| D19 | **Suspend vs. crash**: `SIGHUP`/`SIGINT`/`SIGTERM` caught → *suspend* (revoke the credential, log, exit); the next start is normal and reassembles the conversation. A real crash goes through the recovery gate and also reassembles it. |
| D20 | **Protected scopes**: `binding-set`, `rules` (allowlist), `workspace` and `probes` are out of reach of any window — a direct Operator act only. Requires a change to the specification (G11). |
| D21 | **The MIL has two operations:** `mnemonic-save` (the only operation that writes the mnemonic class) and `mnemonic-recall`. The allowed destination depends on the caller: CPE → `episodic` only (after the probes); Orchestrator → `session` only; Sleep → `semantic` only (promotion gated by the probes). Operation name = intent name. Resolves G12. |
| D22 | **Deterministic context truncation**, in the Orchestrator, always (not only on rollover): the Operator's first turn + the latest turns that fit the budget; a `context-truncated` event in the session store. Explicit `options.num_ctx` on every Ollama call. (§6.5) |
| D23 | **Action Ledger through the SIL**: EXEC signals, the SIL writes `pending` before and a resolution entry after (append-only, never updated). A `file_write` in the workspace is atomic (tmp → fsync → rename → fsync dir) and only then resolved. (§5) |
| D24 | **No `conversation.json`.** The conversation is derived from the session store: the first record of each session carries `conversation` and `continues`; `/clear` writes `conversation-cleared`. Everything in `memory/` is append-only. (§3) |
| D25 | **Crash vs. live session** (G14), refined by D39. A credential present at start is decided **in this order, each step reached only if the previous one did not decide**: (1) the `flock` on `CREDENTIAL` **held** by another process, **or the lock state undeterminable** (an error from `flock`) → **conflict**, consulting nothing else — neither residue (a live session in the middle of a commit has staging) nor `PULSE` (a live process may be late touching it); (2) lock free and residue of interrupted work (orphan generation or entry, Sleep without completion) → **crash**; (3) lock free, no residue: `PULSE` fresh → **conflict** (a live session with no process, ADAPTER.md §2.5), stale → **crash**. Encoded in `sil.classify_credential`, tested exhaustively. |
| D26 | **The conformance fixture skill** (ADAPTER.md §3.6) lives in `fsp_testing/`, beside `inject`: package absent in production, no fixture. |
| D27 | **`fsp init` = scaffolding only**, interactive: experimental and security disclaimer (yes/no); entity name; folder (default `~/.fsp/entities/<name>/`); model, with a pre-check and an API key if needed; `git init` in the entity folder (layout in §3.0); final summary. **Writes neither the Genesis nor `HEAD`.** |
| D28 | **Model and workspace are operational settings**, not structural: an Operator act recorded in the integrity log, no commit, no rollover, effective from the next cycle. Outside the Genesis. `fsp run` in a folder declares that folder the workspace; `/work set P` and `/model X` change it mid-session. Every cycle records which model answered. Resolves G4. |
| D29 | **FAP — First Activation Protocol**: the first `fsp run` without an Anchor. The only moment a Genesis may be written: the Operator's binding, persona (provided or default), the OC-001(d) probes, digest → Genesis → `HEAD` (the atomic point, OP-017); the disclaimer acceptance and the model chosen at init become the first Operator acts in the log. Then a normal start with every gate issues the credential. Adapter: `lifecycle init` = scaffolding + non-interactive FAP, no session. |
| D30 | **A workspace never crosses a store**: refused if it equals, lies inside, or contains `~/.fsp` or any store registered in `~/.fsp/config.json` (by `realpath`). In practice this refuses `/` and `~`. |
| D31 | **The allowlist stays structural** (commit + rollover to take effect in the session; protected scope, D20). |
| D32 | **`fsp endure`** manages the entity's git repository: `status`, `commit`, `remote set`, `push`, `pull`, `clone <url> [name]` (alias `fsp init --clone`). **Fast-forward only**: divergent histories are an identity fork (OC-003(d)), never a merge — fsp refuses and explains. `commit` takes the store's write lock. `remote set` warns that the repository must be private. `fsp run` may warn when the remote is ahead. After a `clone`: normal gates (no FAP), workspace = current folder, the model reconfirmed if the last one does not exist on the host, keys asked for again. (§3.0) |
| D33 | **Structural vs. runtime**, the general criterion (G15). *Structural* = what the entity is, or its bounds; verified on every start; changed by commit (the entity may propose, except for protected scopes, D20): persona, skills, probes, bindings, allowlist, parameters that shape memory. *Runtime* = how the Operator uses the entity now; **only the Operator changes it**, by a direct act in the log, no commit; it lives in the store (OC-003(a)) but is **resolved per host**: model, endpoint, `num_ctx`, workspace, timeouts, session store retention, UI preferences. Generalizes D28. |
| D34 | **Integrity document** (`integrity/documents/<n>.json`, one per generation): a canonical list `[{path, sha256, exec}]` of **all** structural content — structural config, persona, bindings, probes, allowlist, and every skill file by file (manifest **and** code). Excluded: runtime, memory, the session store, the log. `sha256(document)` = the baseline in `HEAD` = the chain entry's `state_digest`. Written in the commit pipeline before the `rename` of `HEAD`. Boot: a full hash of every file, the exact difference reported, three values that must agree. A Vital Check optimization outside v0 may skip files whose size and mtime are unchanged; the boot never does. The execute bit is included (G6). |
| D35 | **Implementation fingerprint** (version + hash of the fsp code) recorded in the log on every start — **audit, not a gate**; the start warns if it changed since the previous session. It never enters verification: the fsp code does not travel with the store (OC-003(b)), and a tampered fsp would lie about its own hash (defence against a hostile host belongs to the Security extension). |
| D36 | **Provenance of every effect of the entity.** A `model-fingerprint` record in the log on every start and every `/model` (provider, name, **weights digest** when the server reports one, `num_ctx`, endpoint). Every cycle has an id (`s-42/c-17`) and points to the fingerprint in force; every dispatched intent carries the cycle, and its owner passes it to whatever it records: a host action and a skill (log), a proposal (log), an episodic memory (Memory Store), a turn (session store). Every record answers **who authorized** (binding) and **who originated** (session, cycle, model). The log keeps actions, not full text; none of this enters the chain (the model is runtime, D33). The digest is declared by the server: audit, not guarantee. (G17) |
| D37 | **The Vital Check in v0** (OP-003). Its **skeleton** lands in Phases 1, 2 and 4, because leaving it for later turns it into a patch: a thread-safe store (lock); verification that returns **findings** `{type, target, owner, evidence}`, the same function at boot and in the Vital Check; Nominal/Degraded/Critical states; the anomaly → correction → external re-verification protocol, as signals in the log (OC-009); a `check()`/`correct(anomaly)` interface on each component; a halt path (Critical stops dispatch at the cycle boundary, OP-020); a heartbeat per thread with cadence by interval and by activity (OP-003(a)). The concrete **checks** arrive gradually, each phase with those of the component it builds. (§6.7) |
| D38 | **An operational condition is not an integrity anomaly.** Model unavailable, network down, workspace deleted: integrity is intact, so it is **neither** Degraded nor Critical — retry with backoff and **tell the Operator** (e.g. "model unavailable, `/model` to switch"), revoking nothing. The same logic as OP-010 ("a capacity condition, not an anomaly"). |
| D39 | **`PULSE`** at the store root: the session id written once at opening; after that only the **mtime** changes, touched by the SIL **at the end of every complete Vital Check** (not by a blind timer). A stale pulse = a verifier that did not answer (OP-008(c)) and, with no lock, a dead session (D25). A `flock` on `CREDENTIAL` during a real `fsp run`, with the file opened `O_RDWR` (NFS emulates `flock` with `fcntl`, which needs write access for an exclusive lock), probed by `store.flock_exclusive(blocking=False)`: an error is not "free". Integrity class, declared in `describe state`; outside the integrity document and git. |
| D40 | **Self-repair:** detected → **confirm once** (re-read; if gone, it was noise, log it and continue) → **one correction** by the owner → external re-verification by the SIL → if it failed, escalate. Up to **2** corrections, default **1** (a runtime setting with a fixed ceiling). |
| D41 | **Chain ids are hashes.** Every integrity artifact is canonical JSON; an entry's id = `sha256` of its bytes; `predecessor` = the previous entry's id; `HEAD` = `{entry, entry_id, baseline}`. **`genesis_digest` = the id of the Genesis Anchor**, which carries a `nonce`: two entities with the same initial state and the same Operator have equal `head_digest` and different `genesis_digest` (OP-017: reinitializing creates another entity). Any byte changed in a committed entry breaks a link. |
| D42 | **`OBEC-STORE` is written once**, at scaffolding: `{format, format_version, implementation}` and, if init chose one, `model` (which the FAP turns into an Operator act). *Scaffolded* vs. *active* **derives from the presence of `HEAD`** — no file is rewritten to change state. |
| D43 | **Write lock** = `flock` on **`integrity/store.lock`**, opened `O_RDWR|O_CREAT`, plus a per-process reentrant `RLock`. Reason: `flock(2)` on Linux says that over NFS the lock becomes `fcntl`, and an exclusive one needs a file open for writing — impossible on a directory (SMB is similar); macOS untested. The file is classified data (integrity, form `lock`): empty, never written, **never removed** (deleting a held lock would let in a second owner; the FAP's residue cleanup preserves it); bytes in it are a verification finding. **Fails closed:** any `flock` error other than contention → `LockUnavailable` (`check: store-lock`), nothing is written. Lock state is shared per store within a process: two `Store` objects on the same root would otherwise deadlock when nested, since `flock` is per open descriptor. |
| D44 | **The FAP writes the founding log records before `HEAD`.** Until the `rename` of `HEAD` nothing is committed; the next FAP deletes everything except `OBEC-STORE` and starts over. It refuses a non-empty directory that is not an fsp store (it never deletes what is not its own). |
| D45 | **The log is hash-chained from its first record** (`prev` = sha256 of the previous record; ids `L-nnnnnn`). *Verifying* the log is Phase 3, together with resolving the chain's authorizations (step 4.6). |
| D46 | **The credential = `S/CREDENTIAL`**: the OP-020 artifact, at the root beside `PASSIVE-SIGNAL`, so the Operator can act without knowing the layout. **Content:** canonical JSON `{session, issued_at, binding}` — `session` is the session id (`s-N`, the same as in the D36 cycle ids), `binding` the Operator's in whose name the start ran. **It is neither a secret nor a bearer of authority:** authority comes from the gates that issued it; the file only marks which session is live. **Every dispatch checks existence *and* identity:** file present, parseable, `session` equal to the dispatching session's. Absent, unreadable or another session's → the session is revoked and stops (fail-closed) — otherwise a new credential issued after a revocation would validate the old session's dispatches. **Revocation**, two paths with the same effect: through the SIL (remove, and log `credential-revoked`) or direct (`rm S/CREDENTIAL`, OP-021, no component); the direct one is logged by whoever detects it first (dispatch, Vital Check or the next start). Created with `O_EXCL`; `flock` on the same file opened `O_RDWR` during an `fsp run` (D39). |
| D47 | **`PULSE` by activity in the adapter.** In an `fsp run`, the SIL touches `PULSE` at the end of every Vital Check (D39, Phase 4). The adapter has no process between invocations: **every invocation that acts within the live session touches `PULSE`** after checking the credential (liveness by activity, like OP-003(a)'s activity cadence). Interval `pulse_interval_s`, default **600**, declared in `describe config`; ADAPTER.md §2.5 admits the bound (G18). |
| D48 | **Identity of the Operator's channel.** Every Operator act is made *as* a binding. `fsp`: the Operator id configured for the entity on the host (`~/.fsp/config.json`, Phase 10; until then `--operator`). Adapter: optional `--operator ID` (§2.4 allows extra flags), **default = the founding binding recorded in the Genesis** (ADAPTER.md §3.3, G19). If that binding is not active, the act is refused (`check: binding`) — what to do with an empty set of bindings is Phase 3. The start is also made as a binding: the credential's `binding` (D46) and that of the `session-open` record. |
| D49 | **A conflict at start: refuse and notify, do not revoke the live session.** OP-020 says a conflict is Critical, with *"the conflicting credential revoked"*. In fsp a conflict is only declared when the other session is alive (lock held, lock state unknown, or a fresh `PULSE` — D25): revoking it would let a mistaken second start bring down a legitimate session, and the start out of order is the second one. OC-003(d) only requires the Operator to be notified before any new credential, which is met. An Operator who wants the session dead has direct revocation (`rm S/CREDENTIAL`). A deviation recorded in §9. |

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
  (reasoning)   (session+memory)       (host)            (integrity)
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
| `fsp/sil.py` | SIL | verification, commit, gates, credential, log, grants, allowlist, passive signal, skill admission | `integrity` + `structural` (by commit only) |
| `fsp/lifecycle.py` | SIL | the gated start, the live session, close, revocation, decommission (§8) | through `sil.py` and `store.py` |
| `fsp/orchestrator.py` | infra | routing, context, lifecycle, rollover | nothing |
| `fsp/operator.py` | Operator channel | Operator acts → SIL | nothing directly |
| `fsp/ui.py` | UI | terminal chat, `/…` commands | nothing — reads `session/` through the MIL |
| `fsp/store.py` | — | layout, atomic writes, **class guard** | called by the owners only |
| `fsp/digest.py`, `fsp/probes.py` | — | canonical digest; deterministic probes | nothing |

**Class guard** (carries OC-003(c) and OC-005(b)): every write to the store
goes through `store.write(cls, relpath, data, *, writer)`, which refuses when
`writer` does not own `cls`. A unit test scans the code and fails if it finds
`open(…, "w"/"a")`, `os.rename`/`os.replace`/`os.remove` outside `store.py`.

**Reasoning never writes.** The CPE returns intents as JSON; the Orchestrator
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
    ├── .gitignore                 store/CREDENTIAL, store/PULSE, store/integrity/store.lock, store/memory/session/
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
├── PULSE                          liveness: session id + mtime touched on every complete Vital Check (D39)
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
│   ├── store.lock                 write lock, empty, never removed (D43)
│   ├── sessions.json              session state (§8.4)
│   ├── index.json                 skill index (§8.4)
│   ├── auth.json                  approvals, windows (grants), budget consumed
│   ├── operational.json           runtime in force on this host (D33; derived from the Operator's acts in the log)
│   └── ledger.jsonl               Action Ledger (OP-015)
└── memory/
    ├── session/<session-id>.jsonl transient: turns, intents, results, events (D10);
    │                              1st record: session-open {conversation, continues} (D24)
    ├── episodic/records.jsonl     written during the session through mnemonic-save (D11)
    └── semantic/records.jsonl     by promotion in the Sleep only
```

- Only paths relative to the store; nothing of the host in verified content
  (OC-003(b)).
- **Two write forms, and only two** (in `store.py`): an *append-only* file
  (`O_APPEND`, `fsync` per record, a truncated final line detected on read) or
  a file *replaced whole* (tmp in the same directory → `fsync` → `rename` →
  `fsync` of the directory). No file in the store is rewritten in place.
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

1. **staging** — builds `structural/gen/<n+1>/` complete; `fsync` files and dir.
2. **validation** — validates the ops and the result.
3. **integrity document + chain entry** — writes `integrity/documents/<n+1>.json`
   and `integrity/chain/<n+1>.json`; `fsync`.
4. **commit** — `HEAD.tmp` → `fsync` → `rename(HEAD.tmp, HEAD)` → `fsync` of the dir.
5. **resumption** — logs; removes `gen/<n-1>`.

**Recovery** (the crash gate, before verification): removes `gen/<k>`,
`documents/<k>` and `chain/<k>` newer than `HEAD` (G5). `inject interrupt
--stage`: `staging` = after 1, `write` = after 2, `chain-entry` = after 3.

### 3.4 Integrity log

`integrity/log.jsonl`, `O_APPEND`, `fsync` per record, hash-chained (D45). A
truncated final line is detected and logged, never silently repaired. Fields:
`id`, `kind`, `rule`, `at`, `binding` (Operator act), `session`, payload.

### 3.5 Credential (OC-003(d), OP-020)

`CREDENTIAL` with `O_CREAT|O_EXCL`; during an `fsp run`, the process holds a
`flock` on it (the OS releases it if the process dies). At start, with a
credential present: the D25 rule (lock, residue, `PULSE`). Conflict → refused,
and the Operator notified before any new credential (D49); crash → recovery.

Content and checks: D46. Every dispatch checks that `CREDENTIAL` exists and
names **its** session; `rm S/CREDENTIAL` stops the entity (step 1.2).

---

## 4. Operations (`describe operations`)

| Operation | Owner | reasoning | writes_classes | host | irreversible |
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
`describe operations` lists it as reachable by reasoning, because the
`episodic` destination is.

`entity attempt-write --via X` routes through the real operation X; what
refuses is the class guard, never the adapter.

---

## 5. Execution (OC-008, D2, D15, D16)

A fixed order (OP-013), each refusal with a `check` and logged:

1. **`workspace-boundary`** — the `realpath` of the target and of every
   declared target of the skill inside the workspace; refuses a symlink that
   leaves, a `..` that leaves, and any path inside the store (even if the
   declared workspace includes it). For `http_fetch`, the equivalent is the
   domain (G9). Runs before everything else (step 8.6).
2. **`operator-rule`** — the allowlist: `allow` / `deny` / default `hold` (D16).
3. **`skill-index`** — present in the start's index.
4. **`skill-manifest`** — the manifest and files match what was admitted,
   **now** (step 8.9).

**Native primitives** (`file_*`, `http_fetch`) truly confine: fsp resolves and
checks before touching disk or network.

**Skills** — `structural/gen/<n>/skills/<name>/manifest.json`: `name`,
`description`, `argv` (a fixed command with `{arg}` placeholders), `args`
(schema: type, pattern/regex, and which ones are paths — checked as targets),
declared `targets`, declared `domains`, `irreversible`, `timeout_s`. Execution:
`subprocess` **without a shell** (`argv` as a list), `cwd` = the workspace, a
minimal environment, a watchdog. The result is logged (OC-008(d)).

**`file_write` and the Action Ledger** (OP-015, D23). The ledger is integrity:
EXEC does not write it, it signals the SIL.

1. EXEC → SIL: `ledger-open {op, target, intent}` → the SIL writes a `pending`
   entry.
2. EXEC writes to the workspace: tmp in the same directory → `fsync` →
   `rename` → `fsync` of the directory.
3. EXEC → SIL: `ledger-resolve {entry, outcome}` → the SIL writes a resolution
   entry referencing the first.

An entry without resolution at the next start goes to the Operator **before**
the credential; never re-executed.

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
  `continues` links of the `session-open` records back to the last
  `conversation-cleared` (D24).
- **The model's context on every cycle:** system (persona, config, intent
  instructions) + `mnemonic-recall` results + the conversation history since
  the last clear (read from `session/` of the chained sessions, through the
  MIL) + the stimulus. The model keeps no state; every call carries everything.
  That is why a new model "acts as if it had been there all along".
- **The UI reads the same source** (`session/` through the MIL). No UI buffer of
  its own feeds the model — that would be a side channel (OC-007).

**Why this is compatible with OC-007:** the conversation history is transient
operational context of an operation that continues; what lasts beyond the
conversation is what the entity saved (`mnemonic-save`, D11) or promoted. A new
conversation (`/clear`, `/new`) does not see the previous history; only
`mnemonic-recall`. The Profile needs to name this (G8).

### 6.2 Operator commands

Interpreted by the UI/Orchestrator; they **never become a stimulus** to the CPE.

| Command | Conversation | Memory / state |
|---|---|---|
| `/model X` · `fsp model X` | continues | pre-check → operational act in the log (D28); the next cycle uses the new model |
| `/work set P` · `fsp run` in a folder | continues | operational act in the log (D28, D30) |
| `/allow …` · `/deny …` | continues | commit to the allowlist → rollover |
| `/grant <scope> --for T --budget N` | continues | opens a window (integrity, no rollover) |
| `/compact` | history replaced by a summary (separate call) | summary written to `session/` as an event |
| `/clear` · `/new` | new, no history | **nothing is saved** (D13); only the `conversation-cleared` marker |
| `/exit` | ends | Closure Payload (outside the chat) → full Sleep (promotion, GC, commits) |
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
  deterministic probes (D12). The record is attributed to the session
  (OC-003(e)).
- `mnemonic-recall` v0: keywords over `episodic/` + `semantic/`.
- Full Sleep (`/exit`): Closure Payload in a separate call (working context for
  the next conversation + promotion requests) → episodic → semantic promotion
  gated by the probes → GC of `session/` for ended conversations → approved
  commits. The credential is removed only at the end.

### 6.7 Vital Check (D37–D40)

**Cadence** (OP-003(a)): every declared interval **or** every K cycles,
whichever comes first; it runs in a thread and applies corrections at the cycle
boundary.

**Flow:** finding → confirm once → an `anomaly {type, target, evidence}` signal
to the owner (through the Orchestrator, in the log) → the owner corrects within
its own authority → `corrected {action}` → the SIL re-verifies on its own →
Nominal, or Critical (credential revoked, OP-008 escalation, passive signal if
delivery fails). At the end of a complete Vital Check, the SIL touches `PULSE`.

| Component | Finding | Correction within its own authority | Re-verification | If it fails |
|---|---|---|---|---|
| EXEC | a skill file diverges from the integrity document | prunes the skill from the index (OP-006) | skill out of the index | follows Identity Drift: the Operator is told to repair by commit or restore through `endure` |
| MIL | truncated tail in the session store or memory; recall index inconsistent | marks the tail invalid (a new record, append-only); rebuilds the derived index | coherent re-read | Critical |
| CPE | malformed intents in a row; context beyond budget | discards and reassembles the context; aborts the cycle with no commit | the next cycle parses | **Critical** (reasoning is never Degraded) |
| structural outside skills | diverges from the integrity document | none | — | Critical directly; suggests restoring |
| chain | Evolutionary Drift (OP-004(c)) | none | — | always Critical |
| SIL | does not run | — | stale `PULSE` seen by the others | escalation (corroborated: outside v0) |

Operational conditions (D38) stay out of this table: backoff and a notice, no
revocation.

---

## 7. Adapter

`implementations/fsp-ref/obec-adapter` — a thin executable over the **same
functions** as the CLI (ADAPTER.md §1.1–1.2). `inject` only with `fsp_testing/`
present (D6); the clock is injectable there, never a skew file in the store.
What varies (ids, timestamps) goes in `detail` (§2.3).

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
| 1 | `passive-signal` | OC-002(c) | `PASSIVE-SIGNAL` absent | present → `aborted`, `lesser_outcome: suspended` |
| 2 | `crash-recovery` | OC-010 | no `CREDENTIAL` → `pass`; with one, `classify_credential` (D25): **conflict** → start `refused` (`check: concurrent-session`, OC-003(d)), `operator_notified: true`, live session untouched (D49); **crash** → recovery → `recovered` | consecutive recoveries ≥ `N_boot` → passive signal written, `aborted` (OP-018(b)) |
| 3 | `structural-verification` | OC-004(a) | `verify()` with no findings | findings logged → `aborted`. A chain terminated by decommission → start `refused`, `rule: OC-001(c)` |
| 4 | `binding-verification` | OC-002(a) | `bindings.json` of the `HEAD` generation valid, ≥ 1 binding, and the starting binding (D48) is in it | → `aborted` |
| 5 | `authorization-state` | OC-002(b) | `auth.json` absent (empty) or readable. Phase 3: expired or exhausted windows logged and closed here | unreadable → `aborted` |
| 6 | `skill-index` | OC-008(c) | index built from the skills of the `HEAD` generation (none today); a skill that does not match the integrity document is **excluded** and reported, and the gate passes (step 8.8) | index cannot be built → `aborted` |

Drift in `skills/` does not abort the start: the finding's owner is `exec`, and
the index gate excludes the skill and tells the Operator (OP-006, step 8.8).
Any other drift aborts at the structural gate.

**Recovery (gate 2, crash):** removes entries, documents and generations beyond
`HEAD`, and temporary files (G5); removes the stale `CREDENTIAL` and `PULSE`;
logs `recovery {evidence, attempt}`. The residue list is the one `verify()`
already returns.

**Credential:** only after all six. Session `s-N` (N from
`integrity/sessions.json`); `CREDENTIAL` with `O_EXCL` and `{session,
issued_at, binding}` (D46); `PULSE` with the session id; a `session-open
{session, binding, gates}` record.

**`inject gate-failure --gate T`:** `fsp_testing` writes a single-use marker
**outside the store** (`$TMPDIR/fsp-testing/<sha256 of the realpath>.json`);
the start consults `fsp_testing.hooks.forced_failure(root, token)` only if the
package imports. In production the package does not exist. The hook can only
make a gate fail, never pass, and is declared in the claim (ADAPTER §5.2).

### 8.3 Within the session

- **`live_session(root)`** — the session id if `CREDENTIAL` exists, is readable
  and names the session open in `sessions.json` (D46); otherwise `None`. Every
  `entity` command and every Operator act within the session goes through here
  and touches `PULSE` (D47). No session → `refused`, `check: no-session`.
- **`lifecycle stop`** — normal close: clears `consecutive_recoveries` and
  `open_session`, removes `CREDENTIAL` and `PULSE`, logs `session-close {mode:
  normal}`. Sleep and the Closure Payload are Phase 7. Order: `CREDENTIAL` and
  `PULSE` first, then `sessions.json`, then the log. A crash in the middle
  leaves, at worst, one extra `credential-removed-directly` in the log — never
  a phantom session.
- **`operator revoke-credential`** — an Operator act (`operator-act {act:
  revoke-credential}`, with a binding), then removes `CREDENTIAL` and `PULSE`.
  **`--direct`**: the adapter deletes `CREDENTIAL` as an `rm` would, with no
  component and no log entry at that moment. Whoever notices first logs
  `credential-removed-directly {session}`: the session's next command or the
  next start (`open_session` set and no `CREDENTIAL`). A direct revocation with
  no session (an `rm` of a credential that does not exist) is accepted,
  `removed: false` — the Operator always can.
- **Passive signal** — `raise_passive_signal(condition, detail)` writes
  `PASSIVE-SIGNAL` as **plain text** (condition, session, time, id of the log
  record), readable with `cat` with nothing running (step 2.14). `inject
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
- **`describe config`** — `pulse_interval_s` (600; 60–86400), `n_boot` (3;
  1–10), `n_channel` (3; 1–10), each with `governs`. Runtime settings (D33), in
  `integrity/operational.json` when the Operator changes them. None touches the
  order or the existence of a gate; evidence referenced.

### 8.4 Data in the `LAYOUT`

| Data | Path | Class | Form |
|---|---|---|---|
| `session-state` | `integrity/sessions.json` — `{last_session, open_session, consecutive_recoveries}` | integrity | replace |
| `skill-index` | `integrity/index.json` | integrity | replace |

---

## 9. Deviations from the Profile

All SHOULD, all recorded.

| Profile | fsp-ref | Reason |
|---|---|---|
| OP-009(a)(b): cognitive consolidation only at close; Memory Store written only in the Sleep | episodic written during the session (`mnemonic-save`); only promotion goes through the Sleep | memory grows without depending on `/exit` (D11) |
| OP-009(d)/OP-010: resumption through a Resumption Record | rollover reassembles the conversation from `session/` | a transparent switch, with no payload polluting the conversation (D9) |
| OP-016: the workspace declaration is structural | the workspace is an operational setting in the log (D28) | it changes constantly; a host path does not belong to the identity (G4) |
| OP-017: first activation issues the credential | the FAP writes the Genesis; the credential comes from the start that follows it, with every gate | even the first session goes through OC-010 |
| OP-020: a session conflict is Critical and revokes the conflicting credential | refuses the start and notifies the Operator; the live session continues (D49) | the one out of order is the second start, not the session the lock or `PULSE` shows alive |
| OP-018: a crash without a payload loses the session's progress | the conversation is reassembled on the next start | usability (D8); what was not saved stays transient |
