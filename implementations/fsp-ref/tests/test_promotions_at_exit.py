# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Promotions recorded with the Closure Payload and decided before the close,
the phases a Closure ran, and a decommission over an interrupted commit (D80,
D81, D83, D94)."""

from __future__ import annotations

import json
from unittest import mock

from helpers import TempDirTest

from fsp import chain, lifecycle, mil, model, operator, probes, proposals, sil
from fsp.sil import Refused
from fsp.store import Store, remove_as_operator


class Base(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def promotion(self, slug="short answers", **kw):
        return {
            "slug": slug,
            "category": "guidance",
            "content": "The Operator prefers short answers.",
            **kw,
        }

    def payload(self, *promotions):
        return {
            "consolidation": "We planned the release.",
            "working_set": [],
            "message": "Next: tag it.",
            "promotions": list(promotions),
        }

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def sessions(self):
        return self.store.read_json(lifecycle.SESSIONS)

    def auth(self):
        return proposals.read_auth(self.store)

    def domain(self, domain="example.com"):
        pid = proposals.propose(self.S, [{"op": "allow-domain", "domain": domain}])[
            "proposal"
        ]
        operator.approve(self.S, pid)
        return pid


class RecordClosureTests(Base):
    def test_the_requests_are_recorded_with_the_payload(self):
        out = operator.record_closure(
            self.S, self.payload(self.promotion("a"), self.promotion("b"))
        )
        self.assertEqual(lifecycle.live_session(self.S), "s-1")
        self.assertEqual(out["session"], "s-1")
        self.assertEqual(out["refused"], [])
        pending = mil.pending_promotions(self.store)
        self.assertEqual([r["id"] for r in pending], out["requests"])
        self.assertEqual([r["index"] for r in pending], [0, 1])
        (payload,) = [
            r
            for r in mil.session_records(self.store, "s-1")
            if r["kind"] == "closure-payload"
        ]
        self.assertEqual({r["closure"] for r in pending}, {payload["id"]})
        self.assertEqual(out["closure"], payload["id"])
        listed = operator.review_list(self.S)["promotions"]
        self.assertEqual([p["promotion"] for p in listed], out["requests"])
        self.assertIsNone(self.sessions()["closing"])
        self.assertEqual(self.log("session-close"), [])

    def test_a_flagged_promotion_is_refused_and_not_offered(self):
        flagged = self.promotion("flagged", content=probes.REFERENCE_TEXTS[0])
        out = operator.record_closure(self.S, self.payload(flagged, self.promotion()))
        self.assertEqual(out["refused"], [0])
        self.assertEqual(len(out["requests"]), 1)
        self.assertEqual(
            [r["id"] for r in mil.pending_promotions(self.store)], out["requests"]
        )
        refusals = [r for r in self.log("refusal") if r["rule"] == "OC-002(d)"]
        self.assertEqual([r["check"] for r in refusals], ["self-representation"])
        listed = operator.review_list(self.S)["promotions"]
        self.assertEqual([p["promotion"] for p in listed], out["requests"])

    def test_the_review_lists_only_the_live_session_s_last_payload(self):
        operator.record_closure(self.S, self.payload(self.promotion("old")))
        out = operator.record_closure(self.S, self.payload(self.promotion("new")))
        listed = operator.review_list(self.S)["promotions"]
        self.assertEqual([p["promotion"] for p in listed], out["requests"])

    def test_the_review_lists_none_without_a_payload(self):
        with self.store.write_lock():
            mil.request_promotion(self.store, "s-1", **self.promotion())
        self.assertEqual(operator.review_list(self.S)["promotions"], [])
        lifecycle.stop(self.S)
        self.assertEqual(operator.review_list(self.S)["promotions"], [])


class ClosePromotionTests(Base):
    def test_the_approved_request_is_promoted_in_that_closures_sleep(self):
        first, second = operator.record_closure(
            self.S, self.payload(self.promotion("a"), self.promotion("b"))
        )["requests"]
        operator.approve_promotion(self.S, first)
        operator.reject_promotion(self.S, second)
        out = operator.close_conversation(self.S)
        (record,) = mil.semantic_records(self.store)
        self.assertEqual(record["promotion"], first)
        self.assertEqual(out["sleep"], {"promoted": [record["id"]], "refused": []})
        (complete,) = self.log("sleep-complete")
        self.assertEqual(complete["promoted"], [record["id"]])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_undecided_requests_are_not_promoted(self):
        operator.record_closure(
            self.S, self.payload(self.promotion("a"), self.promotion("b"))
        )
        out = operator.close_conversation(self.S)
        self.assertEqual(out["sleep"], {"promoted": [], "refused": []})
        self.assertEqual(mil.semantic_records(self.store), [])
        self.assertEqual(sil.semantic_ledger(self.store), [])

    def test_a_window_promotes_at_the_close_and_spends_its_budget(self):
        operator.grant(self.S, scope="memory.semantic", expiry="+1h", budget=5)
        operator.record_closure(
            self.S, self.payload(self.promotion("a"), self.promotion("b"))
        )
        out = operator.close_conversation(self.S)
        self.assertEqual(len(out["sleep"]["promoted"]), 2)
        self.assertEqual(len(mil.semantic_records(self.store)), 2)
        (grant,) = self.auth()["grants"]
        self.assertEqual(grant["used"], 2)

    def test_a_request_of_an_earlier_payload_is_never_promoted(self):
        lifecycle.stop(self.S)
        res = lifecycle.start(self.S, hold=True)
        self.addCleanup(res.holder.release)
        (old,) = operator.record_closure(self.S, self.payload(self.promotion("old")))[
            "requests"
        ]
        operator.approve_promotion(self.S, old)
        out = lifecycle.suspend(self.S, signal="SIGINT", chain=False)
        self.assertIs(out["suspended"], True)
        self.assertEqual(out["session"], res.session)
        self.assertEqual([r["session"] for r in self.log("closure-begin")], ["s-1"])
        res.holder.release()
        again = lifecycle.start(self.S, hold=True)
        self.addCleanup(again.holder.release)
        self.assertEqual(again.outcome, "accepted")
        new = operator.record_closure(self.S, self.payload(self.promotion("new")))[
            "requests"
        ][0]
        operator.approve_promotion(self.S, new)
        closed = operator.close_conversation(self.S)
        (record,) = mil.semantic_records(self.store)
        self.assertEqual(record["promotion"], new)
        self.assertEqual(closed["sleep"]["promoted"], [record["id"]])
        self.assertNotIn(
            old, [r["promotion"] for r in mil.semantic_records(self.store)]
        )

    def test_closing_without_a_payload_is_refused(self):
        with self.assertRaises(Refused) as caught:
            operator.close_conversation(self.S)
        self.assertEqual(caught.exception.check, "closure-missing")
        self.assertEqual(caught.exception.rule, "OP-009(d)")
        self.assertEqual(lifecycle.live_session(self.S), "s-1")
        self.assertTrue(self.store.exists(lifecycle.CREDENTIAL))
        self.assertIsNone(self.sessions()["closing"])
        (refusal,) = [r for r in self.log("refusal") if r["check"] == "closure-missing"]
        self.assertEqual(refusal["rule"], "OP-009(d)")


class ExitTests(Base):
    def test_exit_conversation_records_then_closes(self):
        out = operator.exit_conversation(self.S, self.payload(self.promotion()))
        self.assertEqual(len(out["requests"]), 1)
        self.assertEqual(
            [r["id"] for r in mil.pending_promotions(self.store)], out["requests"]
        )
        self.assertEqual(
            out["closure"], mil.pending_promotions(self.store)[0]["closure"]
        )
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertIsNone(self.sessions()["closing"])
        self.assertEqual(out["log_records"][0], self.log("operator-act")[-1]["id"])

    def test_exit_with_closure_still_ends_the_conversation(self):
        mil.stimulate(self.S, "let us plan")
        fake = model.FakeModel([json.dumps(self.payload(self.promotion()))])
        out = operator.exit_with_closure(self.S, channel=fake, date="2026-10-14")
        self.assertEqual(out["cycle"], "s-1/c-1")
        self.assertEqual(len(out["requests"]), 1)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertEqual(len(self.log("closure-complete")), 1)


class PhasesRanTests(Base):
    def phases(self):
        (complete,) = self.log("closure-complete")
        return complete["phases"]

    def test_a_plain_stop_ran_integrity_only(self):
        with mock.patch.object(lifecycle, "observe_log", side_effect=AssertionError):
            lifecycle.stop(self.S)
        self.assertEqual(self.phases(), ["integrity"])

    def test_new_ran_the_sleep(self):
        with mock.patch.object(lifecycle, "observe_log", side_effect=AssertionError):
            operator.new_conversation(self.S)
        self.assertEqual(self.phases(), ["sleep", "integrity"])

    def test_an_approved_proposal_ran_the_endure_phase(self):
        self.domain()
        with mock.patch.object(lifecycle, "observe_log", side_effect=AssertionError):
            lifecycle.stop(self.S)
        self.assertEqual(self.phases(), ["endure", "integrity"])

    def test_the_marker_keeps_the_phases_that_ran(self):
        self.domain()
        with mock.patch.object(
            lifecycle.sil, "write_log_checkpoint", side_effect=OSError("crash")
        ):
            with self.assertRaises(OSError):
                lifecycle.stop(self.S)
        closing = self.sessions()["closing"]
        self.assertEqual(closing["done"], ["sleep", "endure"])
        self.assertEqual(closing["ran"], ["endure"])


class DecommissionTests(Base):
    def test_an_interrupted_commit_is_resolved_before_the_terminal_entry(self):
        pid = self.domain()
        real = sil.commit_generation

        def crash(*args, **kwargs):
            real(*args, **kwargs)
            raise RuntimeError("crash after HEAD")

        with mock.patch.object(proposals.sil, "commit_generation", crash):
            with self.assertRaises(RuntimeError):
                proposals.commit(self.S, pid)
        committed = sil.read_head(self.store)["entry"]
        self.assertIn("committing", self.auth()["proposals"][pid])
        self.assertTrue(remove_as_operator(self.S, lifecycle.CREDENTIAL))
        out = lifecycle.decommission(self.S, "archive")
        (recovered,) = self.log("commit-recovered")
        self.assertEqual(recovered["proposal"], pid)
        self.assertEqual(recovered["entry"], committed)
        self.assertIn(recovered["id"], out["log_records"])
        entries = [r["entry_kind"] for r in self.log("commit")]
        self.assertEqual(entries, ["commit", "decommission"])
        kinds = [
            self.store.read_json(chain.entry_relpath(n))["kind"]
            for n in range(1, out["entry"] + 1)
        ]
        self.assertEqual(kinds.count("commit"), 1)
        self.assertEqual(kinds[-1], "decommission")
        self.assertEqual(out["entry"], committed + 1)
        self.assertNotIn(pid, self.auth()["proposals"])
        self.assertEqual(self.log("endure-complete"), [])
