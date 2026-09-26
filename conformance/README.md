# Conformance

**Status: in progress.** Nothing here is usable yet.

An implementation is **OBEC-Core conformant** if and only if it passes the ten
tests defined in [obec-core.md §2](../spec/obec-core.md). Conformance is a test
result, not a reading of the document, and a claim must be accompanied by the
suite output.

## What goes here

| File | Status | Purpose |
|---|---|---|
| [`ADAPTER.md`](ADAPTER.md) | **done** | The contract an implementation exposes so the suite can drive it. The specification leaves storage formats and operation sets implementation-defined, so the suite cannot inspect internals — it drives an adapter that speaks OBEC vocabulary. |
| [`TESTS.md`](TESTS.md) | **done** | The ten tests formalized into 77 assertable steps against adapter commands. |
| [`runner/`](runner/) | **done** | The harness that drives an adapter and emits a claim. Python 3, stdlib only. Ships a deliberately breakable stub that validates the suite. |
| [`CLAIMS.md`](CLAIMS.md) | **done** | The register of who claims what, at which specification and suite version, with the review and withdrawal process. |

## Two kinds of test

Not every invariant can be proven by running a system. OC-006 (stateless
inference only) and OC-009 (signal boundaries) are structural properties of how
the implementation is built, not behaviors it exhibits at runtime.

- **Executable** — the suite drives the adapter and asserts the outcome.
- **Attested** — the implementation declares the property with evidence (a
  pointer to the code that establishes it), and a reviewer signs off.

A claim states which tests were executed and which were attested. Conflating the
two would make the suite look stronger than it is.

## What the suite cannot establish

The adapter is written by the implementer being tested, so **a dishonest adapter
passes**. The suite detects error, not fraud — the same posture the specification
takes toward the Semi-Trusted host. The mitigations are procedural: the adapter
source is published with the claim, and the claim is reproducible by a third
party. [ADAPTER.md §6](ADAPTER.md#6-what-the-suite-cannot-establish) states the
limits in full.

## Suite versioning

The suite has its own version line, independent of the specification's
([Core §4.1](../spec/obec-core.md#41-what-is-version-bound)). A suite release may
test an existing guarantee more closely; an implementation that passed an earlier
suite is conformant to the suite it passed, and says which.
