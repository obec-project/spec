# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

from helpers import TempDirTest

from fsp import ledger, lifecycle, sil
from fsp.store import Store


class LedgerTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def records(self):
        return self.store.read_jsonl(ledger.LEDGER)[0]

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def notices(self, condition):
        return [
            r for r in self.log("operator-notification") if r["condition"] == condition
        ]

    def raw(self, data):
        with open(self.store.path(ledger.LEDGER), "ab") as f:
            f.write(data)

    def test_an_entry_opens_and_resolves(self):
        a = ledger.open_entry(
            self.store,
            op="file_write",
            target="notes.txt",
            intent="save notes",
            session="s-1",
        )
        self.assertTrue(a.startswith("A-"))
        ledger.resolve_entry(self.store, a, "done", session="s-1")
        recs = self.records()
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["kind"], "open")
        self.assertEqual(recs[1]["kind"], "resolve")
        self.assertEqual(recs[1]["entry"], a)
        self.assertEqual(recs[1]["outcome"], "done")

    def test_unresolved_lists_only_open_entries(self):
        a = ledger.open_entry(
            self.store, op="op", target="t", intent="i", session="s-1"
        )
        b = ledger.open_entry(
            self.store, op="op", target="t", intent="i", session="s-1"
        )
        ledger.resolve_entry(self.store, a, "done", session="s-1")
        pending, damaged, end = ledger.unresolved(self.store, 0)
        self.assertEqual([e["id"] for e in pending], [b])
        self.assertEqual(damaged, [])
        self.assertEqual(end, ledger.size(self.store))

    def test_unresolved_reads_from_the_offset(self):
        a = ledger.open_entry(
            self.store, op="op", target="t", intent="i", session="s-1"
        )
        off = ledger.size(self.store)
        b = ledger.open_entry(
            self.store, op="op", target="t", intent="i", session="s-1"
        )
        pending, _damaged, _end = ledger.unresolved(self.store, off)
        self.assertEqual([e["id"] for e in pending], [b])
        self.assertNotIn(a, [e["id"] for e in pending])

    def test_an_offset_past_the_end_reads_from_the_start(self):
        a = ledger.open_entry(
            self.store, op="op", target="t", intent="i", session="s-1"
        )
        pending, _damaged, _end = ledger.unresolved(self.store, 10**9)
        self.assertEqual([e["id"] for e in pending], [a])

    def test_a_damaged_line_is_reported_and_skipped(self):
        a = ledger.open_entry(
            self.store, op="op", target="t", intent="i", session="s-1"
        )
        off = ledger.size(self.store)
        self.raw(b"not json\n")
        b = ledger.open_entry(
            self.store, op="op", target="t", intent="i", session="s-1"
        )
        pending, damaged, _end = ledger.unresolved(self.store, 0)
        self.assertEqual([e["id"] for e in pending], [a, b])
        self.assertEqual(damaged, [off])

    def test_a_torn_tail_is_cut_and_logged_before_the_next_entry(self):
        ledger.open_entry(self.store, op="op", target="t", intent="i", session="s-1")
        self.raw(b'{"id": "A-')
        ledger.open_entry(self.store, op="op", target="t", intent="i", session="s-1")
        self.assertEqual(len(self.records()), 2)
        torn = self.log("torn-append")[-1]
        self.assertEqual(torn["path"], ledger.LEDGER)
        self.assertEqual(torn["bytes"], 10)

    def test_the_start_surfaces_an_open_entry_and_closes_it(self):
        lifecycle.start(self.S)
        a = ledger.open_entry(
            self.store,
            op="file_write",
            target="notes.txt",
            intent="save notes",
            session=lifecycle.live_session(self.S),
        )
        lifecycle.stop(self.S)
        res = lifecycle.start(self.S)
        self.assertTrue(res.operator_notified)
        notices = self.notices("ledger-unresolved")
        self.assertEqual(len(notices), 1)
        self.assertIn(a, notices[0]["detail"])
        last = self.records()[-1]
        self.assertEqual(last["kind"], "resolve")
        self.assertEqual(last["entry"], a)
        self.assertEqual(last["outcome"], "interrupted")
        self.assertEqual(last["notice"], notices[0]["id"])
        gate = next(g for g in res.gates if g["gate"] == "crash-recovery")
        self.assertEqual(gate["ledger_surfaced"], [a])
        offset = self.store.read_json(lifecycle.SESSIONS)["ledger_offset"]
        self.assertLess(offset, ledger.size(self.store))
        self.assertEqual(ledger.unresolved(self.store, offset)[0], [])

    def test_a_surfaced_entry_is_not_surfaced_again(self):
        lifecycle.start(self.S)
        a = ledger.open_entry(
            self.store,
            op="file_write",
            target="notes.txt",
            intent="save notes",
            session=lifecycle.live_session(self.S),
        )
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        res = lifecycle.start(self.S)
        notices = self.notices("ledger-unresolved")
        self.assertEqual(len(notices), 1)
        self.assertIn(a, notices[0]["detail"])
        gate = next(g for g in res.gates if g["gate"] == "crash-recovery")
        self.assertNotIn("ledger_surfaced", gate)

    def test_the_start_reports_a_damaged_line(self):
        self.raw(b"not json\n")
        res = lifecycle.start(self.S)
        self.assertEqual(len(self.notices("ledger-damaged")), 1)
        self.assertTrue(res.operator_notified)
        self.assertTrue(res.credential_issued)

    def test_a_torn_tail_does_not_hide_the_next_entry_from_the_start(self):
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        self.raw(b'{"id": "A-')
        lifecycle.start(self.S)
        a = ledger.open_entry(
            self.store,
            op="file_write",
            target="notes.txt",
            intent="save notes",
            session=lifecycle.live_session(self.S),
        )
        lifecycle.stop(self.S)
        res = lifecycle.start(self.S)
        gate = [g for g in res.gates if g["gate"] == "crash-recovery"][0]
        self.assertEqual(gate.get("ledger_surfaced"), [a])
        self.assertEqual(self.notices("ledger-damaged"), [])
