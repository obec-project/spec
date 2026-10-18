# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Semantic promotion requests and the Operator's decision on them (D53, D77, D80)."""

from __future__ import annotations

from helpers import TempDirTest

from fsp import lifecycle, mil, operator, probes, proposals, sil
from fsp.sil import Refused
from fsp.store import Store


class PromotionTests(TempDirTest):
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

    def promotions(self):
        return proposals.read_auth(self.store)["promotions"]

    def test_a_request_is_a_pending_record(self):
        pid = self.request()
        pending = mil.pending_promotions(self.store)
        self.assertEqual(len(pending), 1)
        rec = pending[0]
        self.assertEqual(rec["id"], pid)
        self.assertTrue(pid.startswith("PP-"))
        self.assertEqual(rec["slug"], "short answers")
        self.assertEqual(rec["category"], "guidance")
        self.assertEqual(rec["content"], "The Operator prefers short answers.")
        self.assertEqual(rec["session"], "s-1")
        self.assertEqual(rec["conversation"], mil.conversation_of(self.store, "s-1"))
        self.assertIsNone(rec["supersedes"])
        self.assertEqual(
            rec["digest"],
            mil.promotion_digest(
                "short answers", "guidance", "The Operator prefers short answers.", None
            ),
        )

    def test_content_the_probes_flag_is_not_offered(self):
        with self.assertRaises(Refused) as ctx:
            self.request(content=probes.REFERENCE_TEXTS[0])
        self.assertEqual(ctx.exception.check, "self-representation")
        self.assertEqual(ctx.exception.rule, "OC-002(d)")
        self.assertEqual(mil.pending_promotions(self.store), [])

    def test_a_slug_the_probes_flag_is_not_offered(self):
        with self.assertRaises(Refused) as ctx:
            self.request(slug=probes.REFERENCE_TEXTS[0][:120])
        self.assertEqual(ctx.exception.check, "self-representation")
        self.assertEqual(mil.pending_promotions(self.store), [])

    def test_an_unknown_category_is_refused(self):
        with self.assertRaises(Refused) as ctx:
            self.request(category="self")
        self.assertEqual(ctx.exception.check, "category")
        self.assertEqual(ctx.exception.rule, "OP-009(f)")

    def test_a_bad_slug_is_refused(self):
        for slug in ("", "a\nb"):
            with self.subTest(slug=slug):
                with self.assertRaises(Refused) as ctx:
                    self.request(slug=slug)
                self.assertEqual(ctx.exception.check, "slug")
                self.assertEqual(ctx.exception.rule, "OP-009(f)")

    def test_approval_records_the_digest(self):
        pid = self.request()
        out = operator.approve_promotion(self.S, pid)
        digest = mil.pending_promotions(self.store)[0]["digest"]
        self.assertEqual(out["digest"], digest)
        self.assertEqual(self.promotions()[pid]["digest"], digest)
        acts = lifecycle.observe_log(self.S, kind="operator-act")["records"]
        self.assertEqual(acts[-1]["act"], "approve-promotion")
        self.assertEqual(acts[-1]["promotion"], pid)
        self.assertEqual(acts[-1]["digest"], digest)
        self.assertEqual(self.promotions()[pid]["record"], acts[-1]["id"])

    def test_an_approval_may_carry_the_operator_s_text(self):
        pid = self.request()
        edit = {
            "slug": "terse",
            "category": "rule",
            "content": "Answer in one paragraph.",
        }
        operator.approve_promotion(self.S, pid, edit=edit)
        entry = self.promotions()[pid]
        digest = mil.promotion_digest("terse", "rule", "Answer in one paragraph.", None)
        self.assertEqual(entry["digest"], digest)
        self.assertNotEqual(
            entry["digest"], mil.pending_promotions(self.store)[0]["digest"]
        )
        self.assertEqual(entry["edit"], edit)

    def test_the_operator_s_text_passes_the_probes_too(self):
        pid = self.request()
        edit = {
            "slug": "terse",
            "category": "rule",
            "content": probes.REFERENCE_TEXTS[0],
        }
        with self.assertRaises(Refused) as ctx:
            operator.approve_promotion(self.S, pid, edit=edit)
        self.assertEqual(ctx.exception.check, "self-representation")
        self.assertEqual(self.promotions(), {})

    def test_rejection_is_recorded(self):
        pid = self.request()
        out = operator.reject_promotion(self.S, pid)
        self.assertIn("rejected", self.promotions()[pid])
        self.assertEqual(self.promotions()[pid]["rejected"], out["log_records"][0])

    def test_a_decided_or_unknown_promotion_is_refused(self):
        pid = self.request()
        operator.approve_promotion(self.S, pid)
        with self.assertRaises(Refused) as ctx:
            operator.approve_promotion(self.S, pid)
        self.assertEqual(ctx.exception.check, "promotion-decided")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")
        with self.assertRaises(Refused) as ctx:
            operator.approve_promotion(self.S, "PP-0000")
        self.assertEqual(ctx.exception.check, "promotion-unknown")

    def test_the_review_lists_undecided_promotions(self):
        promotion = {
            "slug": "short answers",
            "category": "guidance",
            "content": "The Operator prefers short answers.",
        }
        payload = {
            "consolidation": "We talked.",
            "working_set": [],
            "message": "Next.",
            "promotions": [promotion, {**promotion, "slug": "other"}],
        }
        a, b = operator.record_closure(self.S, payload)["requests"]
        operator.reject_promotion(self.S, a)
        listed = operator.review_list(self.S)["promotions"]
        self.assertEqual([p["promotion"] for p in listed], [b])
        self.assertEqual(listed[0]["content"], "The Operator prefers short answers.")
        self.assertEqual(listed[0]["slug"], "other")

    def test_a_window_may_cover_semantic_promotion(self):
        out = operator.grant(self.S, scope="memory.semantic", expiry="+1h", budget=3)
        grants = proposals.read_auth(self.store)["grants"]
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["id"], out["grant"])
        self.assertEqual(grants[0]["scope"], "memory.semantic")
        self.assertEqual(grants[0]["state"], "open")
