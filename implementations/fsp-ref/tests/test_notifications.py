# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

from helpers import TempDirTest

from fsp import lifecycle, operator, proposals, sil
from fsp.digest import canonical
from fsp.sil import Refused
from fsp.store import LAYOUT, Store
from fsp.verify import verify
from fsp_testing import hooks


class NotificationsTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        self.addCleanup(hooks.clear_clock, self.S)

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def conflict(self):
        out = lifecycle.start(self.S)
        self.assertEqual(out.outcome, "refused")

    def pending(self):
        return operator.notifications(self.S)["notifications"]

    def test_a_fresh_store_has_no_pending_notice(self):
        self.assertEqual(
            operator.notifications(self.S),
            {"notifications": [], "pointer_reset": False},
        )

    def test_a_notice_is_pending_until_acknowledged(self):
        lifecycle.start(self.S)
        self.conflict()
        pending = self.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["condition"], "concurrent-session")
        out = operator.acknowledge_notifications(self.S)
        self.assertEqual(out["acknowledged"], [pending[0]["id"]])
        self.assertTrue(out["log_records"])
        act = self.log("operator-act")[-1]
        self.assertEqual(act["act"], "notifications-acknowledged")
        self.assertEqual(act["through"], pending[0]["id"])
        self.assertEqual(act["count"], 1)
        self.assertEqual(act["binding"], "op-1")
        self.assertEqual(act["rule"], "OP-008(a)")
        self.assertEqual(self.pending(), [])

    def test_a_notice_after_the_acknowledgement_is_pending(self):
        lifecycle.start(self.S)
        self.conflict()
        operator.acknowledge_notifications(self.S)
        self.conflict()
        pending = self.pending()
        self.assertEqual(len(pending), 1)
        newest = self.log("operator-notification")[-1]
        self.assertEqual(pending[0]["id"], newest["id"])

    def test_acknowledging_nothing_records_nothing(self):
        n = len(self.log("operator-act"))
        self.assertEqual(
            operator.acknowledge_notifications(self.S),
            {"acknowledged": [], "log_records": []},
        )
        self.assertEqual(len(self.log("operator-act")), n)
        self.assertFalse(self.store.exists("integrity/notices.json"))

    def test_a_pointer_that_does_not_match_lists_every_notice(self):
        lifecycle.start(self.S)
        self.conflict()
        operator.acknowledge_notifications(self.S)
        self.conflict()
        ptr = self.store.read_json("integrity/notices.json")
        ptr["sha256"] = "sha256:" + "0" * 64
        with open(self.store.path("integrity/notices.json"), "wb") as f:
            f.write(canonical(ptr))
        out = operator.notifications(self.S)
        self.assertEqual(len(out["notifications"]), 2)
        self.assertTrue(out["pointer_reset"])

    def test_a_line_that_does_not_parse_hides_no_notice(self):
        lifecycle.start(self.S)
        self.conflict()
        with open(self.store.path("integrity/log.jsonl"), "ab") as f:
            f.write(b"not a record\n")
        self.conflict()
        self.assertEqual(len(self.pending()), 2)

    def test_the_pointer_file_is_classified(self):
        self.assertIn("notices-pointer", [d.name for d in LAYOUT])
        lifecycle.start(self.S)
        self.conflict()
        operator.acknowledge_notifications(self.S)
        lifecycle.stop(self.S)
        self.assertEqual(verify(self.S).findings, [])

    def test_a_critical_reaches_the_mailbox(self):
        lifecycle.start(self.S)
        with open(self.p("S", "structural", "gen", "0", "persona.md"), "ab") as f:
            f.write(b"\nmore")
        hooks.advance_clock(self.S, 60)
        with self.assertRaises(Refused):
            proposals.propose(
                self.S,
                [{"op": "set-persona", "content": "You are a helpful assistant."}],
            )
        self.assertEqual(self.pending()[-1]["condition"], "vital-critical")
