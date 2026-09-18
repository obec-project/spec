# Implementations

**Status: in progress.**

No implementation currently claims OBEC conformance. A reference platform — a
filesystem realization, using only POSIX primitives such as atomic rename and
append-only logs — is in progress and will land here once it passes the ten
tests.

An implementation claiming conformance must provide a conformance adapter (see
[../conformance/](../conformance/)) and publish its suite output.
