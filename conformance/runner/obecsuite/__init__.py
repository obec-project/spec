"""OBEC conformance suite runner.

Drives an implementation's conformance adapter (see ../../ADAPTER.md) through
the tests of ../../TESTS.md and emits a claim.

The runner never inspects an Entity Store's contents, with one deliberate
exception: step 4.7 corrupts bytes blindly, precisely so that one check
depends on nothing the implementation says about itself.
"""

SUITE_VERSION = "0.1.0"
TARGETS = "OBEC-Core 0.9.0"
