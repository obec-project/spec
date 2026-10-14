# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Semantic promotion: what was authorized, written once, record first and
ledger second; and retraction (D53, D81)."""

from __future__ import annotations

import json
from unittest import mock

from helpers import TempDirTest

from fsp import lifecycle, mil, operator, probes, proposals, sil
from fsp.digest import canonical, sha256
from fsp.sil import Refused
from fsp.store import Store


class PromotionApplyTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def request(self, **kw):
        fields = {
            "slug": "short answers",
            "category": "guidance",
            "content": "The Operator prefers short answers.",
            **kw,
        }
        with self.store.write_lock():
            return mil.request_promotion(self.store, "s-1", **fields)

    def promote(self, pid):
        with self.store.write_lock():
            return mil.promote(self.store, "s-1", pid)

    def ledger(self, kind=None):
        return [e for e in sil.semantic_ledger(self.store) if kind in (None, e["kind"])]

    def assert_nothing_written(self):
        self.assertEqual(mil.semantic_records(self.store), [])
        self.assertEqual(sil.semantic_ledger(self.store), [])

    def test_an_approved_request_is_promoted(self):
        pid = self.request()
        operator.approve_promotion(self.S, pid)
        sid = self.promote(pid)
        records = mil.semantic_records(self.store)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["id"], sid)
        self.assertTrue(sid.startswith("S-"))
        self.assertEqual(rec["slug"], "short answers")
        self.assertEqual(rec["category"], "guidance")
        self.assertEqual(rec["content"], "The Operator prefers short answers.")
        self.assertIsNone(rec["supersedes"])
        self.assertEqual(rec["session"], "s-1")
        self.assertEqual(rec["conversation"], mil.conversation_of(self.store, "s-1"))
        self.assertEqual(rec["promotion"], pid)
        self.assertIsNone(rec["binding"])
        entries = self.ledger("promotion")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], sid)
        self.assertEqual(entries[0]["digest"], sha256(canonical(rec)))
        self.assertEqual(entries[0]["promotion"], pid)
        self.assertEqual(entries[0]["authorization"], rec["authorization"])
        logged = lifecycle.observe_log(self.S, kind="promotion")["records"]
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0]["promotion"], pid)
        self.assertEqual(logged[0]["record"], sid)

    def test_the_operator_s_text_is_what_is_promoted(self):
        pid = self.request()
        edit = {
            "slug": "terse",
            "category": "rule",
            "content": "Answer in one paragraph.",
        }
        operator.approve_promotion(self.S, pid, edit=edit)
        self.promote(pid)
        (rec,) = mil.semantic_records(self.store)
        self.assertEqual(rec["slug"], "terse")
        self.assertEqual(rec["category"], "rule")
        self.assertEqual(rec["content"], "Answer in one paragraph.")
        self.assertEqual(
            rec["binding"],
            proposals.read_auth(self.store)["promotions"][pid]["binding"],
        )
        self.assertEqual(rec["session"], "s-1")

    def test_without_authorization_the_request_stays_pending(self):
        pid = self.request()
        self.assertIsNone(self.promote(pid))
        self.assert_nothing_written()

    def test_a_rejected_request_is_never_promoted(self):
        pid = self.request()
        operator.reject_promotion(self.S, pid)
        self.assertIsNone(self.promote(pid))
        self.assert_nothing_written()

    def test_a_window_promotes_and_spends_its_budget(self):
        operator.grant(self.S, scope="memory.semantic", expiry="+1h", budget=1)
        sid = self.promote(self.request())
        self.assertIsNotNone(sid)
        (rec,) = mil.semantic_records(self.store)
        self.assertEqual(rec["id"], sid)
        (grant,) = proposals.read_auth(self.store)["grants"]
        self.assertEqual(grant["used"], 1)
        self.assertEqual(grant["state"], "closed")
        self.assertEqual(grant["closed"], "exhausted")

    def test_promotion_happens_once(self):
        pid = self.request()
        operator.approve_promotion(self.S, pid)
        first = self.promote(pid)
        second = self.promote(pid)
        self.assertEqual(first, second)
        self.assertEqual(len(mil.semantic_records(self.store)), 1)
        self.assertEqual(len(self.ledger("promotion")), 1)

    def test_an_interrupted_promotion_is_completed(self):
        pid = self.request()
        operator.approve_promotion(self.S, pid)
        with mock.patch.object(
            sil, "semantic_ledger_append", side_effect=OSError("crash")
        ):
            with self.assertRaises(OSError):
                self.promote(pid)
        self.assertEqual(len(mil.semantic_records(self.store)), 1)
        self.assertEqual(self.ledger(), [])
        sid = self.promote(pid)
        (rec,) = mil.semantic_records(self.store)
        self.assertEqual(rec["id"], sid)
        (entry,) = self.ledger("promotion")
        self.assertEqual(entry["id"], sid)
        self.assertEqual(entry["digest"], sha256(canonical(rec)))

    def test_a_changed_request_is_not_promoted(self):
        pid = self.request()
        operator.approve_promotion(self.S, pid)
        path = self.store.path(mil.PENDING)
        (rec,) = mil.pending_promotions(self.store)
        rec["content"] = "The Operator prefers long answers."
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        self.assertIsNone(self.promote(pid))
        self.assert_nothing_written()

    def test_the_probes_run_again_at_promotion(self):
        pid = self.request()
        operator.approve_promotion(self.S, pid)
        with mock.patch.object(probes, "scan", return_value=[{"id": "p-test"}]):
            with self.assertRaises(Refused) as ctx:
                self.promote(pid)
        self.assertEqual(ctx.exception.check, "self-representation")
        self.assert_nothing_written()

    def test_supersedes_must_name_a_live_record(self):
        pid = self.request(supersedes="S-0000")
        operator.approve_promotion(self.S, pid)
        with self.assertRaises(Refused) as ctx:
            self.promote(pid)
        self.assertEqual(ctx.exception.check, "supersedes")
        self.assertEqual(ctx.exception.rule, "OP-009(f)")
        self.assert_nothing_written()

    def test_retraction_is_appended_to_the_ledger(self):
        pid = self.request()
        operator.approve_promotion(self.S, pid)
        sid = self.promote(pid)
        out = operator.retract_semantic(self.S, sid)
        (entry,) = self.ledger("retraction")
        self.assertEqual(entry["id"], sid)
        self.assertEqual(entry["act"], out["log_records"][0])
        self.assertEqual(out["record"], sid)
        with self.assertRaises(Refused) as ctx:
            operator.retract_semantic(self.S, sid)
        self.assertEqual(ctx.exception.check, "semantic-retracted")
        with self.assertRaises(Refused) as ctx:
            operator.retract_semantic(self.S, "S-0000")
        self.assertEqual(ctx.exception.check, "semantic-unknown")
        self.assertEqual(len(self.ledger("retraction")), 1)

    def test_a_retracted_record_cannot_be_superseded(self):
        pid = self.request()
        operator.approve_promotion(self.S, pid)
        sid = self.promote(pid)
        operator.retract_semantic(self.S, sid)
        again = self.request(supersedes=sid, slug="short answers, again")
        operator.approve_promotion(self.S, again)
        with self.assertRaises(Refused) as ctx:
            self.promote(again)
        self.assertEqual(ctx.exception.check, "supersedes")
        self.assertEqual(len(mil.semantic_records(self.store)), 1)
