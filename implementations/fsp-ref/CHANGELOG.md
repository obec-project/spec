# fsp-ref — changelog

What changed in fsp-ref, by phase, and why. fsp-ref has no release of its own
yet; it targets OBEC-Core 0.9.1. Changes to the specification and the suite
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
