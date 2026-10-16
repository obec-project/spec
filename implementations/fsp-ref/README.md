# fsp-ref

**Filesystem Substrate Platform** — a reference implementation of
OBEC-Core 0.12.0 over a filesystem and POSIX primitives: atomic rename,
append-only files, `fsync`, `flock`.

**Status: in progress. Not conformant, and not usable as an entity yet.**
The store, the chain back to the Genesis Anchor, first activation, the gated
start, sessions, revocation, the passive signal and decommission are in
place, and so are the Operator's acts on bindings and the workspace,
proposals, their review and the cap on pending ones, approvals,
authorization windows and the commit of a proposal,
validated against the deterministic probes, episodic memory saved through
the same probes, the verification of the
integrity log, the Vital Check before an act of the entity, the
Operator's mailbox of notices, the operations table with its attempted
writes, the Action Ledger, and reading, writing and listing files inside the
workspace, and skills run from a verified copy under the Operator's rule,
which a proposal changes one entry at a time, with typed arguments, under
a watchdog and the monitor of what an execution touched. So are the
allowlist's domains and `http_fetch`, and memory: the session store and the
conversation, recall by words and by lineage, semantic promotion under the
Operator's authorization and its ledger, the Closure after every close — Sleep,
Endure, Integrity — resumed after a crash, with an interrupted commit finished
or undone, and rollover, `/exit` with a Closure Payload, `/new`, `/resume` and
`/inject`. So is cognition without a UI: the inference channel to a local
Ollama or a declared fake, context assembled by priority within a budget,
the cycle and its chain, and the Closure Payload emitted by the model. So
is the live session: `bin/fsp run`, a line REPL whose process holds the
session and suspends it on a signal or the end of input, its decisions as
menus chosen with the arrow keys: the review of proposals, the promotions
decided at `/exit`, and rollover whenever an authorized change waits. The
Operator Channel's prompts for a held act, preemption and `/compact` are
not.

Python 3.10+, standard library only, Linux or macOS.

```sh
python3 -m unittest discover -s tests          # the implementation's own tests
./obec-adapter lifecycle init --store /tmp/S --operator op-1
./obec-adapter lifecycle verify --store /tmp/S
cd ~/project && /path/to/fsp-ref/bin/fsp run --store /tmp/S   # the chat; ~/project is the workspace
/path/to/fsp-ref/bin/fsp review --store /tmp/S                # the review, from a shell
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
| `fsp/lifecycle.py` | the gated start, the live session and the process holding it, suspend, close and its Closure, rollover, revocation, decommission |
| `fsp/operator.py` | the Operator's acts: bindings, the workspace, approvals, windows, `/allow` and `/deny` |
| `fsp/proposals.py` | proposals, the authorization state, the commit of a proposal, the Closure's Endure phase |
| `fsp/exec.py` | the native primitives `file_read`, `file_write`, `file_list` and `http_fetch`, inside the workspace and outside the store, and skills under the watchdog |
| `fsp/monitor.py` | the picture of what an execution touched, compared after it |
| `fsp/manifest.py` | a skill's manifest, checked at the start and before it runs, and its digest |
| `fsp/ledger.py` | the Action Ledger, and the entries a crash left open surfaced at the start |
| `fsp/mil.py` | the memory path: the session store and the conversation, `mnemonic-save` and `mnemonic-recall`, promotion and the semantic ledger, the consolidation, the pointer map |
| `fsp/sleep.py` | the Closure's Sleep phase: consolidation, garbage collection, promotion |
| `fsp/model.py` | the inference channel: the `ollama` and `fake` backends |
| `fsp/cycle.py` | the cognitive cycle, its chain, and the Closure Payload's emission |
| `fsp/context.py` | the sources of assembled context, and its assembly |
| `fsp/vital.py` | the Vital Check before an act of the entity |
| `fsp/probes.py` | the deterministic probes over structural content and memory |
| `fsp/defaults/` | the persona and probes first activation writes |
| `fsp/config.py` | the configuration surface |
| `fsp/clock.py` | the clock, and the one windows are judged by, which a test build can advance |
| `fsp/operations.py` | the operations the code has, and an attempted write through each |
| `fsp/describe.py` | introspection for `describe`, generated from the tables the code runs on |
| `fsp/ui.py`, `bin/fsp` | `fsp run`: the line REPL and its `/…` commands |
| `fsp/adapter.py`, `obec-adapter` | the conformance adapter |
| `fsp_testing/` | test builds only: fault injection, the start's hooks, the fixture skill |
