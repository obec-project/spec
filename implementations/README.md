# Implementations

**Status: in progress.**

No implementation currently claims OBEC conformance — the suite is new, and
the reference implementation is partway through it.

The architecture itself has been implemented twice under the predecessor
specification, in Python and in TypeScript, and entities have operated under
both. The reference implementation for OBEC, [fsp-ref](fsp-ref/) — a
filesystem realization using only POSIX primitives such as atomic rename and
append-only logs — is in progress here, written from this specification alone.

What those earlier runs did not establish is longevity and cost, which is
[open question 1](../design/OPEN-QUESTIONS.md).

An implementation claiming conformance must provide a conformance adapter (see
[../conformance/](../conformance/)) and publish its suite output.
