# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""OBEC conformance suite runner.

Drives an implementation's conformance adapter (see ../../ADAPTER.md) through
the tests of ../../TESTS.md and emits a claim.

The runner never inspects an Entity Store's contents, with one deliberate
exception: step 4.7 corrupts bytes blindly, precisely so that one check
depends on nothing the implementation says about itself.
"""

SUITE_VERSION = "0.1.1"
TARGETS = "OBEC-Core 0.9.1"
