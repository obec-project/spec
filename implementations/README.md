# Implementations

**Status: in progress.**

No implementation currently claims OBEC conformance — the suite is new, and
no implementation has passed it yet.

The architecture itself has been implemented twice under the predecessor
specification, in Python and in TypeScript, and entities have operated under
both. Two implementations are here, both written from this specification
alone, over a filesystem and POSIX primitives such as atomic rename and
append-only logs:

- [**fsp-ref-min**](fsp-ref-min/DESIGN.md), the reference implementation: the
  smallest program that keeps the ten invariants, written to be read. It is
  being designed.
- [**fsp-ref-profile**](fsp-ref-profile/), which also follows the
  Implementation Profile. It is partway through the suite and frozen at
  OBEC-Core 0.12.0. It may later be completed against the whole Profile.

What those earlier runs did not establish is longevity and cost, which is
[open question 1](../design/OPEN-QUESTIONS.md).

An implementation claiming conformance must provide a conformance adapter (see
[../conformance/](../conformance/)) and publish its suite output.
