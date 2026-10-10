# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

from helpers import TempDirTest

from fsp import config, lifecycle, operator, proposals, sil
from fsp.sil import Refused
from fsp.store import INTEGRITY, Store

PERSONA = [{"op": "set-persona", "content": "You are a helpful assistant."}]
SKILL = [{"op": "install-skill", "name": "example", "files": {"SKILL.md": "# example\n"}}]


class ReviewTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def test_the_list_is_empty_without_proposals(self):
        self.assertEqual(operator.review_list(self.S), {"proposals": []})

    def test_the_list_shows_pending_proposals_in_order(self):
        lifecycle.start(self.S)
        p1 = proposals.propose(self.S, PERSONA)["proposal"]
        p2 = proposals.propose(self.S, SKILL)["proposal"]
        operator.approve(self.S, p1)
        out = operator.review_list(self.S)["proposals"]
        self.assertEqual([e["proposal"] for e in out], [p1, p2])
        for e in out:
            self.assertEqual(
                set(e.keys()),
                {"proposal", "digest", "session", "record", "categories", "approved"},
            )
        self.assertEqual(out[0]["categories"], ["persona"])
        self.assertEqual(out[1]["categories"], ["skills.install"])
        self.assertTrue(out[0]["approved"])
        self.assertFalse(out[1]["approved"])
        self.assertLess(out[0]["record"], out[1]["record"])

    def test_the_list_over_unreadable_authorization_is_refused(self):
        self.store.replace_json(INTEGRITY, lifecycle.AUTH, [], writer=sil.WRITER)
        before = len(self.log("refusal"))
        with self.assertRaises(Refused) as cm:
            operator.review_list(self.S)
        self.assertEqual(cm.exception.check, "authorization-state")
        self.assertEqual(len(self.log("refusal")), before)

    def test_rejecting_removes_the_proposal_and_logs_the_act(self):
        lifecycle.start(self.S)
        pid = proposals.propose(self.S, PERSONA)["proposal"]
        digest = self.store.read_json(lifecycle.AUTH)["proposals"][pid]["digest"]
        out = operator.reject(self.S, pid)
        self.assertTrue(out["log_records"])
        act = self.log("operator-act")[-1]
        self.assertEqual(act["act"], "reject")
        self.assertEqual(act["proposal"], pid)
        self.assertEqual(act["binding"], "op-1")
        self.assertEqual(act["rule"], "OC-001(b)")
        self.assertEqual(act["digest"], digest)
        self.assertEqual(operator.review_list(self.S), {"proposals": []})
        self.assertNotIn(pid, self.store.read_json(lifecycle.AUTH)["proposals"])

    def test_rejecting_an_approved_proposal_withdraws_the_approval(self):
        lifecycle.start(self.S)
        pid = proposals.propose(self.S, PERSONA)["proposal"]
        operator.approve(self.S, pid)
        operator.reject(self.S, pid)
        auth = self.store.read_json(lifecycle.AUTH)
        self.assertNotIn(pid, auth["approvals"])
        with self.assertRaises(Refused) as cm:
            proposals.commit(self.S, pid)
        self.assertEqual(cm.exception.check, "proposal-unknown")

    def test_rejecting_an_unknown_proposal_is_refused(self):
        with self.assertRaises(Refused) as cm:
            operator.reject(self.S, "P-0000000000000000")
        self.assertEqual(cm.exception.check, "proposal-unknown")
        self.assertEqual(cm.exception.rule, "OC-001(b)")
        self.assertTrue(cm.exception.log_records)

    def test_rejecting_works_without_a_session(self):
        lifecycle.start(self.S)
        pid = proposals.propose(self.S, PERSONA)["proposal"]
        lifecycle.stop(self.S)
        operator.reject(self.S, pid)
        self.assertEqual(operator.review_list(self.S), {"proposals": []})

    def test_rejecting_over_unreadable_authorization_is_refused(self):
        lifecycle.start(self.S)
        proposals.propose(self.S, PERSONA)
        self.store.replace_json(INTEGRITY, lifecycle.AUTH, [], writer=sil.WRITER)
        before = len(self.log("operator-act"))
        with self.assertRaises(Refused) as cm:
            operator.reject(self.S, "P-0000000000000000")
        self.assertEqual(cm.exception.check, "authorization-state")
        self.assertEqual(cm.exception.rule, "OC-001(b)")
        self.assertEqual(self.log("refusal")[-1]["check"], "authorization-state")
        self.assertEqual(len(self.log("operator-act")), before)

    def test_the_default_cap_is_ten(self):
        self.assertEqual(config.value(self.store, "pending_cap"), 10)
        entry = [s.as_dict() for s in config.SETTINGS if s.name == "pending_cap"][0]
        self.assertEqual(entry["default"], 10)
        self.assertEqual(entry["range"], [1, 100])

    def test_the_cap_refuses_a_new_proposal(self):
        sil.set_operational(self.store, "pending_cap", 2)
        lifecycle.start(self.S)
        proposals.propose(self.S, PERSONA)
        proposals.propose(self.S, SKILL)
        with self.assertRaises(Refused) as cm:
            proposals.propose(self.S, PERSONA)
        self.assertEqual(cm.exception.check, "pending-cap")
        self.assertEqual(cm.exception.rule, "OC-001(b)")
        self.assertTrue(cm.exception.log_records)
        last = self.log("refusal")[-1]
        self.assertEqual(last["check"], "pending-cap")
        self.assertTrue(last["session"])
        self.assertEqual(len(operator.review_list(self.S)["proposals"]), 2)

    def test_an_approved_proposal_counts_against_the_cap(self):
        sil.set_operational(self.store, "pending_cap", 1)
        lifecycle.start(self.S)
        pid = proposals.propose(self.S, PERSONA)["proposal"]
        operator.approve(self.S, pid)
        with self.assertRaises(Refused) as cm:
            proposals.propose(self.S, SKILL)
        self.assertEqual(cm.exception.check, "pending-cap")

    def test_a_rejected_proposal_frees_its_place(self):
        sil.set_operational(self.store, "pending_cap", 1)
        lifecycle.start(self.S)
        p1 = proposals.propose(self.S, PERSONA)["proposal"]
        with self.assertRaises(Refused) as cm:
            proposals.propose(self.S, SKILL)
        self.assertEqual(cm.exception.check, "pending-cap")
        operator.reject(self.S, p1)
        proposals.propose(self.S, SKILL)
        self.assertEqual(len(operator.review_list(self.S)["proposals"]), 1)
