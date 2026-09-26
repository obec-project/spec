# Backlog

What is left to do in this repository, by priority. What is done is in
[CHANGELOG.md](CHANGELOG.md). The reference implementation keeps its own
backlog in [implementations/fsp-ref/BACKLOG.md](implementations/fsp-ref/BACKLOG.md).

The repository is public for early reading and is **announced when the
reference implementation passes every executed step of the suite**. Attested
steps go with evidence and review; step 3.2 requires a real second host;
4.9–4.12 stay *unestablished* for everyone until a second version exists.

---

## 1. Before announcing

- **The reference implementation passes the suite** — the trigger above.
  Phases 3–9 of [fsp-ref's backlog](implementations/fsp-ref/BACKLOG.md).
- **`.github/ISSUE_TEMPLATE/challenge-invariant.md`** — the most important
  template, because it turns [CONTRIBUTING §7](CONTRIBUTING.md#7-challenging-an-invariant)
  from an invitation into a process: fields for which of the ten invariants,
  which of the five forms (*not testable*, *restatement*, *policy*,
  *unsatisfiable*, *names structure*), and the argument with its evidence.
  Alongside it, less urgent:
  - `open-question.md`, for contributions on
    [design/OPEN-QUESTIONS.md](design/OPEN-QUESTIONS.md);
  - `conformance-claim.md`, with the instructions and checklist for submitting
    a conformance result.
- **On announcing, update the status** in the [README](README.md#status-this-is-a-proposal)
  and in [implementations/README.md](implementations/README.md) — the two
  places that say the repository is published for early reading and that no
  implementation has passed the suite.

## 2. Needs the author

- **"Implemented twice, in Python and in TypeScript, and entities have run
  under it"** appears in four documents. Confirm the framing, and whether those
  implementations can be cited (repository, commit, period). If they can, they
  become partial evidence for open question 1 instead of "nobody measured".
- **How long did they run, and what broke?** Any number — sessions, store size,
  something that degraded — turns open question 1 from speculation into
  observation. Something that broke probably deserves an open question of its
  own.
- **Open question 5** (portability vs. hardware-backed keys) says there may be
  no construction that satisfies both. If the author already knows there is,
  or is not, the text is weaker than it needs to be.
- **Not verifiable from inside the repository:** whether the repository
  description (153 characters) reads well; whether the "proposal" framing is
  calibrated — it may be too modest, since the architecture has run twice and
  the documents spend much of their length on what is not known; and the
  trademark risk of "OBEC" (a search found no conflict in software or AI; not
  legal advice).

## 3. Community and tooling

- **Before 2026-10-19: keep fsp-ref's Python 3.9 job alive.** `ubuntu-latest`
  moves to Ubuntu 26 on that date
  ([runner-images#14748](https://github.com/actions/runner-images/issues/14748)).
  Python 3.9 has been end-of-life since October 2025, and `setup-python` is
  unlikely to ship it for the new image, which would break the job that
  checks fsp-ref's declared floor. Either pin that job's image, as the suite's
  3.8 job already pins `ubuntu-22.04`, or raise fsp-ref's floor — which
  changes its decision D1.
- **Move the CI actions off Node 20.** `actions/checkout@v4` and
  `actions/setup-python@v5` target Node 20, which GitHub has deprecated and
  already forces onto Node 24
  ([changelog](https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/)).
  Upgrade both to their Node 24 majors.
- `CODE_OF_CONDUCT.md` — the convention; its absence is noticed.
- `.github/PULL_REQUEST_TEMPLATE.md` — materializes what
  [CONTRIBUTING §5](CONTRIBUTING.md#5-pull-requests) already requires: the
  revision kind, the continuity impact and the affected rules.
- **A claims validator** — a script or GitHub Action that checks the integrity
  and schema of the `.json` and `.md` files submitted to `conformance/claims/`.
- **A CI status badge** in the README.

## 4. Specification — during or after the reference implementation

- **Gaps found by the reference implementation**, to be decided and corrected
  in the specification: [fsp-ref BACKLOG §3](implementations/fsp-ref/BACKLOG.md#3-gaps-in-the-specification-and-the-contract).
- **Diagrams** — the OC-010 start sequence, and store vs. model in the Primer.
  No block diagram in Core §3 (open question 10).
- **A taxonomy of standing-grant scopes** (open question 9) — the
  implementation will have to choose one; bring it back to the Profile.
- **Example artifacts** (Genesis Anchor, chain entry, passive signal) — as "one
  realization", in `implementations/`, not in `spec/`.
- **Run step 1.16 partially:** stop the reasoning, cause an escalation,
  observe the passive signal.

## 5. Extensions — after the reference implementation

Core §6.3 names both as planned and not yet written. Both are to be written
from OBEC, without porting HACA-Security or HACA-CMI.

- **Security** — hardens the host assumption from Semi-Trusted to
  **adversarial**. Under it there are **no standing grants**: a grant's budget
  and expiry live in state and time the host controls, and an adversarial host
  can roll back the one and skew the other; every structural change and every
  promotion requires a per-change approval the Operator signs. Blocked by open
  question 5 (hardware-backed keys vs. the portability of OC-003(b)). Decide
  that before writing it. Its scope includes
  **memory poisoning**: a false fact or a planted instruction promoted into
  semantic memory shapes every later session, and the deterministic probes of
  OC-002(d) look only for what that clause forbids. OP-009(c) lets an
  implementation put promotion under Operator authorization; the extension
  decides what more is required — the probabilistic probe layer (OP-005(b)),
  provenance that finds and withdraws what one source promoted (fsp-ref D36).
- **CMI** (Cognitive Mesh Interface) — needs at least two entities operating
  under the reference implementation.

## 6. Repository layout — later

- Separate repositories for `implementations/` and `ietf/` once they have
  content, adjusting the README's layout table with them.
- `conformance/` moves to its own repository when the suite has an independent
  release, which Core §4.1's separate version lines call for.
