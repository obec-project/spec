# Working in this repository

How to work on OBEC. What the project is and where each thing lives is in the
[README](README.md); how a change is proposed, classified and committed is in
[CONTRIBUTING.md](CONTRIBUTING.md), which governs everything here. This file
lists what is easy to get wrong.

The reference implementation has its own rules in
[implementations/fsp-ref/AGENTS.md](implementations/fsp-ref/AGENTS.md).

## Where things are recorded

| | |
|---|---|
| [README.md](README.md) | what OBEC is, the documents, the project's status — stated there once |
| [design/](design/) | the design: ADRs for the specification's shape, and [OPEN-QUESTIONS.md](design/OPEN-QUESTIONS.md) for what is unsettled. There is no root DESIGN.md |
| [BACKLOG.md](BACKLOG.md) | what is left, by priority |
| [CHANGELOG.md](CHANGELOG.md) | what changed and why, under *Unreleased* until a release |

A change is complete when its item leaves BACKLOG.md, CHANGELOG.md records it
under the right heading, and `design/` reflects any decision about the
specification's shape that changed.

## Rules that are easy to break

- **The kernel is a verbatim extract of Core §2.** A normative sentence changes
  in [spec/obec-kernel.md](spec/obec-kernel.md) and
  [spec/obec-core.md](spec/obec-core.md) identically, in the same commit.
  `tests/test_kernel_verbatim.py` enforces it, versions included.
- **Every kernel change is exactly one of four kinds** — editorial, clarify,
  harden, weaken ([CONTRIBUTING §3](CONTRIBUTING.md#3-classifying-a-change)) —
  and the kind is the commit type. It decides the version bump and whether
  existing entities survive. A **weaken** requires the Specification Owner's
  explicit approval; never make one on your own initiative.
- **A requirement change moves its conformance test in the same change**
  ([CONTRIBUTING §5](CONTRIBUTING.md#5-pull-requests)), and a change to what
  conformance means bumps the suite's version, which is independent of the
  specification's.
- **Commits** follow [CONTRIBUTING §4](CONTRIBUTING.md#4-commit-convention):
  the project's own types (`editorial`, `clarify`, `harden`, `weaken`, `test`,
  `profile`, `design`, `docs`, `impl`, `ietf`, `chore`), a body wrapped at 72
  columns, and **no attribution trailers of any kind** — the log is a
  governance record.
- **Released history keeps its names.** The 0.9.0 CHANGELOG entry says
  `HC-nnn` because that release did; the invariants are `OC-nnn` from 0.9.1.
  Do not "fix" old entries. Identifiers freeze at 1.0.
- **The specification, the suite and the code do not mention HACA.** OBEC's
  predecessor belongs to its history, in `design/` and the CHANGELOG; the
  specification is self-contained, and nothing is ported from HACA or its
  implementations.
- **The suite and an implementation share no code.** Where an implementation
  needs to read the runner to get something right, the gap is in
  [conformance/ADAPTER.md](conformance/ADAPTER.md), and the document is what
  gets fixed.
- **No real entity before 1.0.** OC-004(a) records the major version in the
  Genesis Anchor. Every store made while working here is disposable.
- **Licensing:** a new code file starts with the SPDX header the others carry
  (`Apache-2.0`, `Copyright 2026 Jonas Orrico`). A new document at the root is
  added to the list in [LICENSE](LICENSE).
- **Everything is written in English.**

## Operational facts

- **The repository is public but not announced.** It is published for early
  reading; the announcement waits until the reference implementation passes
  every executed step of the suite ([BACKLOG.md](BACKLOG.md)). The status in
  the README and `implementations/README.md` says so, and changes then.
- **Releases are tags** (`vX.Y.Z`). The version fields — the spec documents'
  frontmatter, the suite version in TESTS.md, ADAPTER.md and `SUITE_VERSION` —
  change only in a release commit, which turns *Unreleased* in the CHANGELOG
  into that release's entry. Between releases, `main` keeps the last release's
  numbers and every change goes under *Unreleased*.
- **A push to `main` runs CI**: the verbatim test, the suite against the stub
  on Python 3.8 – 3.14, and fsp-ref's unit tests on 3.9 – 3.14. It deploys
  nothing.
- The runner writes `claim.md` and `claim.json` to the working directory
  unless given `--out`. Both are git-ignored; submitted claims live in
  `conformance/claims/` under another name.

## Verification

```sh
# from conformance/runner
python3 -m unittest -v tests/test_kernel_verbatim.py   # the kernel is a verbatim extract of §2
python3 -m unittest -v tests/test_stub.py              # the suite against the stub (~80 s)

# from implementations/fsp-ref
python3 -m unittest discover -s tests                  # the reference implementation
```

A change to `spec/` runs the verbatim test; a change to `conformance/` runs
both runner tests; a change to `implementations/fsp-ref/` runs its tests and,
when behaviour changes, the suite against its adapter.
