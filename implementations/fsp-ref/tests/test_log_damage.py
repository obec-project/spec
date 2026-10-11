# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

import json

from helpers import TempDirTest

from fsp import lifecycle, sil
from fsp.digest import is_canonical, sha256
from fsp.store import Store
from fsp.verify import verify


class LogDamageTest(TempDirTest):
    """A damaged integrity log is a finding, never an exception, and a new
    record still chains to the bytes of the line before it (D45)."""

    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def log_path(self):
        return self.store.path("integrity/log.jsonl")

    def lines(self):
        with open(self.log_path(), "rb") as f:
            data = f.read()
        return data.split(b"\n")[:-1]

    def rewrite_last(self, new_line):
        lines = self.lines()
        lines[-1] = new_line
        with open(self.log_path(), "wb") as f:
            f.write(b"\n".join(lines) + b"\n")

    def test_is_canonical_is_false_instead_of_raising(self):
        self.assertTrue(is_canonical({"a": 1}, b'{"a":1}'))
        self.assertFalse(is_canonical({"a": 1}, b'{"a": 1}'))
        self.assertFalse(is_canonical({"a": float("nan")}, b'{"a":NaN}'))

    def test_read_last_line_skips_a_torn_fragment(self):
        complete = self.lines()[-1]
        with open(self.log_path(), "ab") as f:
            f.write(b'{"torn":')
        self.assertEqual(self.store.read_last_line("integrity/log.jsonl"), complete)
        self.assertIsNone(self.store.read_last_line("integrity/ledger.jsonl"))

    def test_records_chain_by_the_bytes_of_the_line_before(self):
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        lines = self.lines()
        for before, after in zip(lines, lines[1:]):
            self.assertEqual(json.loads(after)["prev"], sha256(before))
        self.assertTrue(verify(self.S, full_log=True).chain_intact)

    def test_a_value_canonical_refuses_in_the_log_is_a_finding(self):
        lines = self.lines()
        lines[0] = lines[0].replace(b'"prev":null', b'"prev":NaN', 1)
        with open(self.log_path(), "wb") as f:
            f.write(b"\n".join(lines) + b"\n")
        report = verify(self.S, full_log=True)
        found = [
            f
            for f in report.findings
            if f.type == "log-record" and f.evidence.get("problem") == "not-canonical"
        ]
        self.assertTrue(found)

    def test_a_value_canonical_refuses_in_head_is_a_finding(self):
        with open(self.store.path("HEAD"), "wb") as f:
            f.write(b'{"baseline":NaN,"entry":0,"entry_id":"x"}')
        report = verify(self.S)
        found = [
            f
            for f in report.findings
            if f.type == "head-invalid" and f.evidence.get("problem") == "not-canonical"
        ]
        self.assertTrue(found)

    def test_a_last_record_that_does_not_parse_lets_the_start_record_its_abort(self):
        damaged = self.lines()[-1][:-2] + b"#}"
        self.rewrite_last(damaged)
        n = len(self.lines())
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "aborted")
        self.assertEqual(res.gates[-1]["gate"], "structural-verification")
        record = json.loads(self.lines()[n])
        self.assertEqual(record["prev"], sha256(damaged))
        self.assertEqual(record["id"], "L-%06d" % (n + 1))

    def test_a_last_record_with_nan_lets_the_start_record_its_abort(self):
        damaged = self.lines()[-1].replace(b'"prev":"', b'"x":NaN,"prev":"', 1)
        self.rewrite_last(damaged)
        last_id = json.loads(damaged)["id"]
        n = len(self.lines())
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "aborted")
        record = json.loads(self.lines()[n])
        self.assertEqual(record["prev"], sha256(damaged))
        self.assertEqual(record["id"], "L-%06d" % (int(last_id[2:]) + 1))
