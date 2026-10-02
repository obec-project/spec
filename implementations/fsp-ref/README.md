# fsp-ref

**Filesystem Substrate Platform** — a reference implementation of
OBEC-Core 0.12.0 over a filesystem and POSIX primitives: atomic rename,
append-only files, `fsync`, `flock`.

**Status: in progress. Not conformant, and not usable as an entity yet.**
The store, the chain back to the Genesis Anchor, first activation, the gated
start, sessions, revocation, the passive signal and decommission are in
place, and so are the Operator's acts on bindings and the workspace,
proposals, approvals, authorization windows and the commit of a proposal,
validated against the deterministic probes. Verification of the integrity
log, host actuation and everything cognitive are not.

Python 3.10+, standard library only, Linux or macOS.

```sh
python3 -m unittest discover -s tests          # the implementation's own tests
./obec-adapter lifecycle init --store /tmp/S --operator op-1
./obec-adapter lifecycle verify --store /tmp/S
```

The adapter implements the [conformance adapter contract](../../conformance/ADAPTER.md)
and returns exit code `2` for every command not built yet. `fsp_testing/`
holds fault injection and exists only in test builds: without it, every
`inject` command exits `2`.

[DESIGN.md](DESIGN.md) has the architecture and the decisions behind it,
[BACKLOG.md](BACKLOG.md) what is left, [CHANGELOG.md](CHANGELOG.md) what has
been built, and [AGENTS.md](AGENTS.md) the rules for working on it.

## Layout

| | |
|---|---|
| `fsp/store.py` | the store layout, the two write forms, the content-class guard |
| `fsp/digest.py` | canonical JSON, the integrity document, digests |
| `fsp/chain.py` | the Genesis Anchor, chain entries, `HEAD` |
| `fsp/verify.py` | verification, returning findings |
| `fsp/sil.py` | the integrity log, first activation, bindings, the passive signal, the commit pipeline |
| `fsp/lifecycle.py` | the gated start, the live session, close, revocation, decommission |
| `fsp/operator.py` | the Operator's acts: bindings, the workspace, approvals, windows |
| `fsp/proposals.py` | proposals, the authorization state, the commit of a proposal |
| `fsp/probes.py` | the deterministic probes over structural content |
| `fsp/defaults/` | the persona and probes first activation writes |
| `fsp/config.py` | the configuration surface |
| `fsp/clock.py` | the clock, and the one windows are judged by, which a test build can advance |
| `fsp/describe.py` | introspection for `describe`, generated from the tables the code runs on |
| `fsp/adapter.py`, `obec-adapter` | the conformance adapter |
| `fsp_testing/` | test builds only: fault injection, the start's hooks, the fixture skill |
