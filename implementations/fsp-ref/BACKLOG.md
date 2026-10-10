# fsp-ref — backlog

What is left to build, in order. Design is in [DESIGN.md](DESIGN.md); what is
done is in [CHANGELOG.md](CHANGELOG.md).

---

## 1. Phases

Each phase ends with `run.py --only …` green on its invariants
([AGENTS.md](AGENTS.md)). Phases 0–3 are done.

| Phase | Scope | Suite |
|---|---|---|
| **4** | the Vital Check before an act of the entity, by interval and by activity (D65), with `integrity/vital.json`; the check, its states and self-repair (D37, D40), the sweep of the log (D45); the mailbox of notices and its acknowledgement as functions, and a Critical writing the passive signal (D66) | — (unit tests) |
| **5** | operations table, class guard, a real `attempt-write` (G12) | OC-001 1.9, OC-002 2.1, OC-003(c), OC-005 |
| **6** | actuation inside the workspace (declared since Phase 3), allowlist with digest-pinned skills (D16), a hold and the Operator's four answers to it (D66), native primitives, `http_fetch`, skills in their invocation context (D51), monitoring | OC-008, OC-002 2.2, 5.4 |
| **7** | session records, the conversation and its recall scope (D11, D60), `mnemonic-save`/`mnemonic-recall`, the probes over memory (D12), promotion under authorization and the semantic ledger (D53), `/resume`, `/inject` and `/retract`, Sleep | OC-007, OC-003(e), OC-002(d) |
| **8** | CPE, `FakeModel`, `OllamaModel`, cycle, chat UI, commands, rollover, the process holding the session: `holder` and the `flock` on `CREDENTIAL` (D25), suspend (D19); the prompts and `/notifications` (D66), the rest of the review (D52): `fsp review` and `/review`, approval mid-session triggering a rollover, the review at `/exit` and before the first stimulus, the pending count in the UI, the entity told past the pending cap, proposals a window committed shown in the review; `describe boundaries` | OC-006, OC-009 (attested), OC-001 1.16 (attested) |
| **9** | the full suite; 3.2 on a VM or remote machine; claim | **the trigger for announcing the repository** |
| **10** | a complete interactive `fsp init`, including a name already in use (D54), `fsp endure` (D32), `~/.fsp/config.json`/`credentials.json`, `notify_command` (D66) | — (the Operator's tooling; a real 3.2 through `endure clone` on a VM) |
| **11** | the agenda (D62): `agenda.json`, `/agenda` and `fsp agenda`, the `agenda` proposal op, items' scoped authorizations; `fsp tick` and its host entry installed by `fsp init`/`endure`, the auto session and the main start suspending it (D63); worker skills, run in the background (D64) | — (unit tests) |

After that: a test entity on Ollama, operated for days, measuring what
[open question 1](../../design/OPEN-QUESTIONS.md) asks for.

### Carried into the phases

- **Phase 7 — the probes over memory tell the entity's words from others'.**
  Episodic memory records the conversation, and a first-person pattern flags
  an Operator's *I feel* as readily as the entity's. The probes of D12 must
  run on what is attributed to the entity — its turns and what it
  consolidates — not on the whole transcript.
- **Phase 8 — `fsp run` in a folder D30 refuses** (`~`, the entity folder):
  what `run` does instead is not decided.
- **Phase 10 — the entity folder** (`.git`, `.gitignore`, `.gitattributes`,
  D27) is scaffolded by `fsp init`/`endure`; the store's own scaffolding is
  done.
- **Phase 10 — D30 against the registered stores** of `~/.fsp/config.json`.
  Until the registry exists, a workspace is checked against its own store and
  `~/.fsp`.
- **Phase 11 — the periodicity of an item** has no format yet (D62).
- **Phase 11 — a run's outcome reaches the Operator** through the Operator
  Channel (D63), and no channel outside the UI is decided: an auto session
  has no UI.

---

## 2. Outside v0 (Profile, SHOULD)

- Checkpoints (OP-007(c)). When they come in, the chain gets the split D45
  gives the log: the start verifies since the last checkpoint, and the Vital
  Check and `lifecycle verify --full` cover the entries before it.
- Corroborated escalation with a second reporter (OP-008(c)) — the evidence,
  the time of the last check in `integrity/vital.json`, comes with Phase 4
  (D65).
- Background execution (OP-014(b)) of anything but worker skills (D64).
- "Live" delivery to the Operator beyond the UI and a file.
- An OS sandbox.

---

## 3. Gaps in the specification and the contract

Where the specification does not suffice, it is a defect of the specification
([AGENTS.md](AGENTS.md)): each gap below is to be decided and corrected in the
specification in a commit of its own. Closed gaps are in the CHANGELOG.

- **G6 — file mode outside the digest.** Largely resolved in fsp by D34 (the
  execute bit is in the integrity document).
- **G7 — secrets vs. completeness.** The API key lives outside the store (D7).
- **G9 — network.** OC-008 defines the workspace as a territory of files; a
  network destination does not appear. Worker skills make it concrete: an
  agent that reads files and fetches URLs can send what it read out in a URL,
  so fsp bounds `http_fetch` by the allowlist's destinations (D64).
- **G12 — "exactly one path" for mnemonic.** Resolved in fsp (D21) with a
  single operation. The specification could say that destinations within a
  class (session, episodic, semantic) are legitimate parameters of the single
  path.
- **G14 — "crash scenario" is not defined mechanically.** OP-018 says a
  credential present at start signals a crash; OC-003(d) says a credential that
  does not match a crash is a conflict. The specification does not say what
  tells them apart. fsp uses residue of interrupted work or a lock no process
  holds (D25); the specification should name the criterion, or say it is the
  implementation's, with the requirement that it be deterministic.
- **G16 — a workspace that contains the store.** OC-008(b) requires
  disjointness; it does not say whether a declaration containing the store is
  refused or trimmed. fsp refuses (D30).
- **G17 — per-cycle provenance** (optional, Profile). Nothing in the
  specification asks that the model that originated an intent be recorded.
  OP-001 could recommend it (D36): it is what makes it possible, when a model
  turns out to be problematic, to find everything it did — including the
  memories it saved.
- **G20 — scheduled triggers have a home and no mechanism.** The Core says,
  in a note to OC-002 and in the glossary's *Stimulus*, that schedules are
  structural content and a trigger firing executes standing Operator
  authority. It does not say what fires a trigger, whether a firing opens a
  session or needs one, what a firing does while a session is live — the
  store admits one (OC-003(d)) — or what a run may do with no Operator
  present to answer a hold. fsp decides all four (D62, D63); the Profile
  could carry them as a clause of its own.
