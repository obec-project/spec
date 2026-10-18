# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Test-only package: fault injection and the conformance fixture skill.

Its presence is what makes a build a test build (D6, D26). A production
build ships without it, and every ``inject`` command then exits 2
(ADAPTER.md §5).
"""
