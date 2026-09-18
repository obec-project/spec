# The conformance runner

```
python3 run.py --adapter ./your-obec-adapter
```

Drives an implementation's [conformance adapter](../ADAPTER.md) through the
[ten tests](../TESTS.md) and writes a claim: `claim.md` for a human,
`claim.json` for a machine.

Standard library only, Python 3.8+. Being testable should cost an implementer
no toolchain they do not already have, and the runner and the implementation
never share a language — they speak the adapter contract.

## Options

| Flag | |
|---|---|
| `--adapter` | the adapter executable (required) |
| `--adapter-b` | an adapter on a **second host** for the relocation test. Without it, step 3.2 reports *unestablished* — see below |
| `--host-b` | where to place the relocated copy |
| `--implementation` | name and revision under test, recorded in the claim |
| `--only OC-003,OC-008` | run a subset |
| `--out PREFIX` | output prefix (default `claim`) |
| `--keep-stores` | do not delete the disposable stores |

Exit code is `0` when conformant, `1` otherwise.

## What it does not claim

**Step 3.2 needs a second host to mean anything.** Portability fails when a
verification depends on something that does not travel with the store — a
hostname, a TPM, a platform keystore. Copy a store to another directory on the
same machine and all of those are identical, so a host-coupled implementation
verifies exactly like a portable one. The runner therefore reports 3.2
*unestablished* unless `--adapter-b` is supplied, and records that adapter's
command in the claim so a reviewer can judge whether it was genuinely
elsewhere. An ssh wrapper is enough:

```sh
#!/bin/sh
exec ssh host-b /opt/impl/obec-adapter "$@"
```

Reporting a pass for a check that cannot fail would be the overstatement
[ADAPTER.md §6](../ADAPTER.md#6-what-the-suite-cannot-establish) warns about.

**A dishonest adapter passes.** The adapter is written by the implementer being
tested. The suite detects error, not fraud.

## The stub

`stub/obec-adapter-stub` is a toy implementation with a conforming adapter. It
is not an OBEC implementation and must never be used as one. It exists to
validate the suite, because a runner that has never seen a failure is a runner
nobody should trust:

```sh
python3 run.py --adapter ./stub/obec-adapter-stub          # 59 pass, 0 fail
OBEC_STUB_BREAK=oc008a python3 run.py --adapter ./stub/obec-adapter-stub
```

| Break | Violates | Caught by |
|---|---|---|
| `oc002b` | commits without checking authorization | OC-002 |
| `oc003b` | folds the hostname into verification | OC-003 — **only with a real `--adapter-b`** |
| `oc008a` | skips the workspace boundary check | OC-008 |
| `oc008d` | refuses without naming the check | OC-001, OC-002, OC-003, OC-005, OC-008 |
| `oc010` | issues a credential on a failed gate | OC-002, OC-004, OC-010 |

`oc008d` failing five tests at once is the point of the refusal triple: a
system that blocks correctly but cannot say which check blocked is unauditable
everywhere at once, not in one place.

The stub is also the shortest complete answer to *"what does my adapter have to
look like"* — around 500 lines, every command in the contract.

`OBEC_STUB_PRODUCTION=1` makes every `inject` command return exit 2, which is
what a production build must do.

## The suite's own tests

```sh
python3 -m unittest discover -s tests
```

`tests/test_stub.py` runs the suite against the stub unbroken and in every
break above, and holds each break to exactly the tests the table names.
`oc003b` is proved with a second adapter that reports another hostname
(`OBEC_STUB_HOSTNAME`), which the stub honors for that purpose only.

`tests/test_kernel_verbatim.py` is the check [OBEC-Core §4.1](../../spec/obec-core.md#41-what-is-version-bound)
asks for: [obec-kernel.md](../../spec/obec-kernel.md) addresses the same
clauses as the Core's §2, every kernel sentence appears there word for word,
and every §2 sentence carrying an RFC 2119 keyword appears in the kernel.

## Layout

```
run.py                 entry point
obecsuite/adapter.py   invocation, JSON parsing, the three exit codes
obecsuite/result.py    pass / fail / unestablished / error / attested
obecsuite/assertions.py the refusal triple and friends
obecsuite/store.py     disposable stores, blind corruption for step 4.7
obecsuite/harness.py   step recording, log resolution
obecsuite/tests.py     the ten tests, step numbers matching TESTS.md
obecsuite/claim.py     claim emission
stub/                  the toy adapter
tests/                 the suite's own tests
```
