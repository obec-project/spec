# fsp-ref — backlog

What is left to build, in order. Design is in [DESIGN.md](DESIGN.md); what is
done is in [CHANGELOG.md](CHANGELOG.md).

---

## 1. Phases

Each phase ends with `run.py --only …` green on its invariants
([AGENTS.md](AGENTS.md)). Phases 0–2 are done.

| Phase | Scope | Suite |
|---|---|---|
| **3** | log verification (checkpoint, D45), Operator acts, bindings, proposals, approval, windows (G11/G13 first), atomic commit + recovery, `inject interrupt`, `inject corrupt --kind commit-unauthorized` | OC-002(a)(b), OC-004, 10.3 |
| **4** | heartbeat and the Vital Check skeleton (D37–D40), `PULSE` from the Vital Check, the `CREDENTIAL` `flock` in a real run, suspend (D19) | — (unit tests) |
| **5** | operations table, class guard, a real `attempt-write` (G12) | OC-003(c), OC-005 |
| **6** | workspace, allowlist, native primitives, `http_fetch`, skills, monitoring | OC-008, OC-001 1.2, 5.4 |
| **7** | session store, conversation, `mnemonic-save`/`mnemonic-recall`, probes, promotion, Sleep | OC-007, OC-003(e), OC-001(d) |
| **8** | CPE, `FakeModel`, `OllamaModel`, cycle, chat UI, commands, rollover | OC-006, OC-009 (attested) |
| **9** | the full suite; 3.2 on a VM or remote machine; claim | **the trigger for announcing the repository** |
| **10** | a complete interactive `fsp init`, `fsp endure` (D32), `~/.fsp/config.json`/`credentials.json` | — (the Operator's tooling; a real 3.2 through `endure clone` on a VM) |

After that: a test entity on Ollama, operated for days, measuring what
[open question 1](../../design/OPEN-QUESTIONS.md) asks for.

### Carried into the phases

- **Phase 3 — verify the log.** A flipped byte in `integrity/log.jsonl` is not
  detected yet (the `expectedFailure` test in `tests/test_fap_verify.py`):
  verify the `prev` chain. There is a tension with OP-019 (the cost of a start
  does not grow with age): verifying the whole log at start grows with the
  log; the alternative is a checkpoint of the last verified record plus an
  incremental Vital Check. The runner's step 4.7 flips bytes in "files under
  the store" — if it picks the log, that decides it.
- **Phase 3 — `inject corrupt --kind commit-unauthorized`** exits 2 until
  `verify` resolves each entry's `authorization` against what was recorded.
  Today `verify` only requires that it exists.
- **Phase 3 — step 10.3** comes with the commit.
- **Phase 7 — the default probes** (`defaults/probes.json`) exist as structural
  content of the Genesis; nothing runs them yet.
- **Phase 10 — the entity folder** (`.git`, `.gitignore`, `.gitattributes`,
  D27) is scaffolded by `fsp init`/`endure`; the store's own scaffolding is
  done.

---

## 2. Outside v0 (Profile, SHOULD)

- The probabilistic layer of the probes (OP-005(b)).
- Checkpoints (OP-007(c)).
- Corroborated escalation with a second reporter (OP-008(c)) — the evidence
  (`PULSE`) already exists.
- Background execution (OP-014(b)).
- Worker skills (OP-014(d)).
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
- **G8 — a conversation that spans sessions.** The Profile has no such concept,
  and OC-007 only works with it defined (transient context crosses sessions
  within a conversation; knowledge crosses conversations only through the
  Memory Store). A note in the Profile, generalizing OP-010's restart to
  rollover.
- **G9 — network.** OC-008 defines the workspace as a territory of files; a
  network destination does not appear.
- **G10 — episodic memory during the session.** Propose changing OP-009 to
  fsp's design (D11).
- **G11 — protected scopes** (D20): today only `binding-set` is protected by
  OC-002(a); propose extending it to `rules`, `workspace` and `probes`.
- **G12 — "exactly one path" for mnemonic.** Resolved in fsp (D21) with a
  single operation. The specification could say that destinations within a
  class (session, episodic, semantic) are legitimate parameters of the single
  path.
- **G13 — scope vocabulary** ([open question 9](../../design/OPEN-QUESTIONS.md)):
  the suite already assumes one; fsp will need a hierarchical one
  (`skills.install`, `configuration.model`, …).
- **G14 — "crash scenario" is not defined mechanically.** OP-018 says a
  credential present at start signals a crash; OC-003(d) says a credential that
  does not match a crash is a conflict. The specification does not say what
  tells them apart. fsp uses residue of interrupted work or stale liveness
  (D25); the specification should name the criterion, or say it is the
  implementation's, with the requirement that it be deterministic.
- **G15 — structural vs. runtime configuration.** The OC-003(c) table (kernel)
  and the glossary put all of "configuration" in structural. fsp's criterion
  (D33): structural shapes the entity or its bounds; runtime is current use,
  changed only by the Operator, kept in integrity. Proposed revision: limit
  "configuration" to what shapes the entity and add "operational settings" to
  the integrity row. It touches the normative table — **classify when
  writing** (probably *clarify*).
- **G16 — a workspace that contains the store.** OC-008(b) requires
  disjointness; it does not say whether a declaration containing the store is
  refused or trimmed. fsp refuses (D30).
- **G17 — per-cycle provenance** (optional, Profile). Nothing in the
  specification asks that the model that originated an intent be recorded.
  OP-001 could recommend it (D36): it is what makes it possible, when a model
  turns out to be problematic, to find everything it did — including the
  memories it saved.
