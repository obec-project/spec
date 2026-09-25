# fsp-ref — working here

How to work on fsp-ref. What it is and how to run it is in the
[README](README.md); the architecture and the decisions in force are in
[DESIGN.md](DESIGN.md); what is left is in [BACKLOG.md](BACKLOG.md). The
repository's commit convention and change classification are in
[CONTRIBUTING.md](../../CONTRIBUTING.md) and apply here.

## Rules

1. **OBEC only.** Allowed sources: `spec/`, `conformance/` (ADAPTER.md,
   TESTS.md), COMPLIANCE.md and `design/`. **Nothing from HACA**, nor from
   FCP/FCP-TS.
2. **The runner's and the stub's code is not a design source.** If getting
   something right requires reading `conformance/runner/`, that is a gap in
   ADAPTER.md — record it in [BACKLOG.md §3](BACKLOG.md#3-gaps-in-the-specification-and-the-contract)
   and correct the document; do not copy the code.
3. **Where the specification does not suffice, it is a defect of the
   specification.** Record it in BACKLOG.md §3, decide, and correct the
   specification in a commit of its own — do not resolve it only in the code.
4. **The simplest thing that satisfies the ten.** The Profile is SHOULD: only
   what an entity needs to actually operate goes in; deviations are recorded in
   [DESIGN.md §9](DESIGN.md#9-deviations-from-the-profile).
5. **The suite is the judge.** Each phase ends with `run.py --only …` green on
   the phase's invariants. The trigger for announcing the repository: **every
   executed step passes** (3.2 with a real second host; 4.9–4.12 stay
   *unestablished* for everyone).
6. **fsp-ref targets the latest OBEC release.** A release of the
   specification moves `OBEC_VERSION` and the documents that name the version
   in the same commit.
7. **No real entity before 1.0** (OC-004(a) records the version in the Genesis
   Anchor). Development stores are disposable.

## Invariants of the code

- **Every write to a store goes through `fsp/store.py`.** `tests/test_store.py`
  scans the code and fails on a raw `open(…, "w"/"a")`, `os.rename`,
  `os.replace` or `os.remove` anywhere else.
- **Standard library only** (D1). No dependency, not even for tests.
- **`fsp` imports `fsp_testing` only behind a guard**: the start's hook
  (DESIGN.md §8.2) and the adapter's `inject` (D6). A production build is the
  package absent, and must still run.
- **Code comments cite decisions by number** (`D25`, `G14`) and sections of
  DESIGN.md; the reasoning lives there, not in the comment.

## Verification

From `implementations/fsp-ref/`:

```sh
python3 -m unittest discover -s tests
```

The suite, from `conformance/runner/`:

```sh
python3 run.py --adapter ../../implementations/fsp-ref/obec-adapter --only OC-010,OC-002,OC-001,OC-003
```

CI runs the unit tests on every push and pull request.

## Finishing a change

A change is complete when BACKLOG.md loses the item, CHANGELOG.md records it
under its phase, and DESIGN.md reflects any decision that changed. A replaced
decision leaves DESIGN.md and is recorded in the CHANGELOG.
