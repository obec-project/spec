# fsp-ref — backlog

What is left to build, in order. Design is in [DESIGN.md](DESIGN.md); what is
done is in [CHANGELOG.md](CHANGELOG.md).

---

## 1. Phases

Each phase ends with `run.py --only …` green on its invariants
([AGENTS.md](AGENTS.md)). Phases 0–5, 6a, 6b, 7, 8a and 8b-1 are done; 8b
is in four steps.

| Phase | Scope | Suite |
|---|---|---|
| **8b-2** | the phases that ran kept in `closing` (D83); decommission finishing or undoing an interrupted commit before its Endure (D94); promotions recorded with the payload and decided at `/exit` (D53, D80, D81); the UI rolling over when an authorized proposal waits (D95); `/allow` and `/deny` as the Operator's proposal and approval, and `set-parameter` (D96); `ui.choose` and the review as menus — at the open, `/review`, `/exit`, `fsp review` — with the commits windows made (D97); the closure without a current turn (D98); a test that the entity is told past the pending cap (D52) | — |
| **8b-3** | the Operator Channel's prompts in the UI: a hold's four answers (D66), *allow for this session*, the prompt at the boundary (D74) | — |
| **8b-4** | preemption and queueing (OP-002(a)(b)(c)); `/compact`; OP-010's thresholds and the restart they cause, on rollover's mechanism; the token estimate calibrated by `prompt_eval_count` (D88) | — |
| **9** | the full suite; 3.2 on a VM or remote machine; claim | **the trigger for announcing the repository** |
| **10** | a complete interactive `fsp init`, the first activation through `fsp run` (D29), including a name already in use (D54), `fsp repo` (D32), `~/.fsp/config.json`/`credentials.json`, `notify_command` (D66) | — (the Operator's tooling; a real 3.2 through `repo clone` on a VM) |
| **11** | the agenda (D62): `agenda.json`, `/agenda` and `fsp agenda`, the `agenda` proposal op, items' scoped authorizations; `fsp tick` and its host entry installed by `fsp init`/`repo`, the auto session and the main start suspending it (D63); worker skills, run in the background (D64) | — (unit tests) |

After that: a test entity on Ollama, operated for days, measuring what
[open question 1](../../design/OPEN-QUESTIONS.md) asks for.

### Carried into the phases

- **Phase 10 — the entity folder** (`.git`, `.gitignore`, `.gitattributes`,
  D27) is scaffolded by `fsp init`/`repo`; the store's own scaffolding is
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
