# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

from unittest import mock

from helpers import TempDirTest

from fsp import lifecycle, sil
from fsp.store import Store
from fsp.verify import sweep_log


class SweepReadTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def test_read_range_reads_at_most_its_length(self):
        rel = "integrity/log.jsonl"
        with open(self.store.path(rel), "rb") as f:
            whole = f.read()
        self.assertEqual(self.store.read_range(rel, 0, 10), whole[:10])
        self.assertEqual(self.store.read_range(rel, len(whole) - 3, 100), whole[-3:])
        self.assertEqual(self.store.read_range(rel, 0, 0), b"")
        self.assertEqual(self.store.read_range("integrity/ledger.jsonl", 0, 10), b"")

    def test_the_sweep_reads_a_bounded_block_not_the_rest_of_the_log(self):
        for _ in range(5):
            lifecycle.start(self.S)
            lifecycle.stop(self.S)
        with open(self.store.path("integrity/log.jsonl"), "rb") as f:
            size = len(f.read())
        self.assertGreater(size, 2048)

        real = Store.read_range
        sizes = []

        def spy(store, relpath, offset, length):
            sizes.append(length)
            return real(store, relpath, offset, length)

        with mock.patch.object(Store, "read_range", spy), mock.patch.object(
            Store, "read_from", side_effect=AssertionError("read_from")
        ):
            finding, pos, reset = sweep_log(self.store, None, 300)

        self.assertIsNone(finding)
        self.assertIsNone(reset)
        self.assertIsNotNone(pos)
        self.assertLess(pos["offset"], 300)
        self.assertLessEqual(max(sizes), 1024)
