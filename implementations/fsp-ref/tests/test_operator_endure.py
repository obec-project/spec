# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Operator's /allow and /deny as an Endure, and set-parameter (D96)."""

from __future__ import annotations

import json
import os

from helpers import TempDirTest

from fsp import chain, cycle, lifecycle, mil, model, operator, proposals, sil
from fsp.sil import Refused
from fsp.store import Store
from fsp_testing import fixture


class Base(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def auth(self):
        return proposals.read_auth(self.store)

    def head_json(self, name):
        entry = sil.read_head(self.store)["entry"]
        return self.store.read_json(chain.gen_relpath(entry) + "/" + name)

    def cap(self, value):
        sil.set_operational(self.store, "pending_cap", value)


class OperatorRuleTests(Base):
    def act(self, verb, kind, target):
        out = getattr(operator, verb)(self.S, kind, target)
        pid = out["proposal"]
        (rec,) = [r for r in self.log("proposal") if r["proposal"] == pid]
        self.assertEqual(rec["origin"], "operator")
        self.assertEqual(rec["binding"], "op-1")
        self.assertNotIn("session", rec)
        (act,) = [r for r in self.log("operator-act") if r.get("proposal") == pid]
        self.assertEqual(act["act"], "approve")
        self.assertEqual(act["digest"], rec["digest"])
        self.assertEqual(out["log_records"], [rec["id"], act["id"]])
        entry = self.auth()["proposals"][pid]
        self.assertEqual(entry["origin"], "operator")
        self.assertIsNone(entry["session"])
        self.assertEqual(entry["binding"], "op-1")
        self.assertEqual(self.auth()["approvals"][pid]["digest"], rec["digest"])
        self.assertEqual(proposals.waiting(self.store), [pid])
        return pid

    def test_allow_domain_is_committed_by_the_next_endure(self):
        pid = self.act("allow", "domain", "example.com")
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        self.assertNotIn(pid, self.auth()["proposals"])
        (complete,) = self.log("closure-complete")
        self.assertIn("endure", complete["phases"])
        self.assertEqual(len(self.log("endure-complete")), 1)
        domains = self.head_json("rules.json")["domains"]
        self.assertEqual(domains["example.com"], {"rule": "allow"})

    def test_deny_domain_is_committed_by_the_next_endure(self):
        self.act("deny", "domain", "example.com")
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        domains = self.head_json("rules.json")["domains"]
        self.assertEqual(domains["example.com"], {"rule": "deny"})

    def test_a_domain_not_in_its_form_is_refused(self):
        before = self.auth()
        with self.assertRaises(Refused) as cm:
            operator.allow(self.S, "domain", "Example.COM")
        self.assertEqual(cm.exception.check, "ops")
        self.assertEqual(cm.exception.rule, "OC-001(b)")
        self.assertEqual(self.auth(), before)
        self.assertEqual(self.log("refusal")[-1]["check"], "ops")
        self.assertEqual(self.log("proposal"), [])

    def test_a_kind_that_is_neither_is_refused(self):
        with self.assertRaises(Refused) as cm:
            operator.deny(self.S, "persona", "x")
        self.assertEqual(cm.exception.check, "ops")
        self.assertEqual(self.auth()["proposals"], {})

    def test_allowing_a_skill_the_head_lacks_is_refused(self):
        with self.assertRaises(Refused) as cm:
            operator.allow(self.S, "skill", "nope")
        self.assertEqual(cm.exception.check, "skill-unknown")
        self.assertEqual(cm.exception.rule, "OC-008(c)")
        last = self.log("refusal")[-1]
        self.assertEqual(last["check"], "skill-unknown")
        self.assertEqual(last["binding"], "op-1")
        self.assertEqual(self.auth()["proposals"], {})

    def test_allow_skill_carries_the_head_digest(self):
        lifecycle.start(self.S)
        files = fixture.skill_files("example")
        pid = proposals.propose(
            self.S, [{"op": "install-skill", "name": "example", "files": files}]
        )["proposal"]
        operator.approve(self.S, pid)
        proposals.commit(self.S, pid)
        lifecycle.stop(self.S)
        digest = proposals.head_skill_digest(self.store, "example")
        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}\Z")
        self.assertIsNone(proposals.head_skill_digest(self.store, "nope"))

        pid = self.act("allow", "skill", "example")
        (op,) = self.auth()["proposals"][pid]["ops"]
        self.assertEqual(op, {"op": "allow-skill", "name": "example", "digest": digest})
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        skills = self.head_json("rules.json")["skills"]
        self.assertEqual(skills["example"], {"rule": "allow", "digest": digest})

    def test_deny_skill_needs_no_installed_skill(self):
        self.act("deny", "skill", "nope")
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        skills = self.head_json("rules.json")["skills"]
        self.assertEqual(skills["nope"], {"rule": "deny"})


class CapTests(Base):
    def test_an_operator_proposal_does_not_count_against_the_cap(self):
        self.cap(1)
        operator.allow(self.S, "domain", "example.com")
        lifecycle.start(self.S)
        proposals.propose(self.S, [{"op": "set-persona", "content": "One."}])
        with self.assertRaises(Refused) as cm:
            proposals.propose(self.S, [{"op": "set-persona", "content": "Two."}])
        self.assertEqual(cm.exception.check, "pending-cap")
        self.assertEqual(cm.exception.rule, "OC-001(b)")
        self.assertEqual(len(self.auth()["proposals"]), 2)

    def test_the_entity_is_told_past_the_cap(self):
        workspace = self.p("W")
        os.makedirs(workspace)
        operator.set_workspace(self.S, workspace)
        self.cap(1)
        lifecycle.start(self.S)
        proposals.propose(self.S, [{"op": "set-persona", "content": "One."}])
        ops = [{"op": "set-persona", "content": "Two."}]
        completions = [
            json.dumps({"intents": [{"op": "propose", "ops": ops}]}),
            json.dumps({"intents": [{"op": "reply", "text": "ok"}]}),
        ]
        fake = model.FakeModel(completions)
        cycle.respond(self.S, "hello", channel=fake, date="2026-10-14")
        results = [
            r for r in mil.session_records(self.store, "s-1") if r["kind"] == "results"
        ]
        self.assertIn("pending-cap", results[0]["text"])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("pending-cap", json.dumps(fake.calls[1]))


class SetParameterTests(Base):
    def set_always_loaded(self, value):
        return [{"op": "set-parameter", "name": "always_loaded", "value": value}]

    def test_set_parameter_writes_always_loaded(self):
        before = self.head_json("config.json")
        lifecycle.start(self.S)
        pid = proposals.propose(self.S, self.set_always_loaded(["rule"]))["proposal"]
        operator.approve(self.S, pid)
        lifecycle.stop(self.S)
        self.assertNotIn(pid, self.auth()["proposals"])
        after = self.head_json("config.json")
        self.assertEqual(after, dict(before, always_loaded=["rule"]))
        self.assertEqual(mil.always_loaded_categories(self.store), ["rule"])

    def test_two_set_parameter_ops_apply_in_order(self):
        lifecycle.start(self.S)
        ops = self.set_always_loaded(["rule"]) + self.set_always_loaded(["project"])
        pid = proposals.propose(self.S, ops)["proposal"]
        operator.approve(self.S, pid)
        lifecycle.stop(self.S)
        self.assertEqual(self.head_json("config.json")["always_loaded"], ["project"])

    def test_malformed_set_parameter_is_refused(self):
        lifecycle.start(self.S)
        cases = [
            {"op": "set-parameter", "name": "pending_cap", "value": ["rule"]},
            {"op": "set-parameter", "value": ["rule"]},
            {"op": "set-parameter", "name": "always_loaded"},
            {"op": "set-parameter", "name": "always_loaded", "value": []},
            {"op": "set-parameter", "name": "always_loaded", "value": ["rule"] * 2},
            {"op": "set-parameter", "name": "always_loaded", "value": ["episodic"]},
            {"op": "set-parameter", "name": "always_loaded", "value": [1]},
            {"op": "set-parameter", "name": "always_loaded", "value": "rule"},
            {"op": "set-parameter", "name": "always_loaded", "value": {"rule": 1}},
        ]
        for op in cases:
            with self.subTest(op=op):
                with self.assertRaises(Refused) as cm:
                    proposals.propose(self.S, [op])
                self.assertEqual(cm.exception.check, "ops")
                self.assertEqual(cm.exception.rule, "OC-001(b)")
        self.assertEqual(self.auth()["proposals"], {})

    def test_a_window_on_parameters_covers_set_parameter(self):
        operator.grant(self.S, expiry="+1h", budget=2, scope="parameters")
        lifecycle.start(self.S)
        pid = proposals.propose(self.S, self.set_always_loaded(["rule"]))["proposal"]
        self.assertNotIn(pid, self.auth()["approvals"])
        lifecycle.stop(self.S)
        self.assertNotIn(pid, self.auth()["proposals"])
        self.assertEqual(self.head_json("config.json")["always_loaded"], ["rule"])
        (window,) = self.auth()["grants"]
        self.assertEqual(window["used"], 1)
        notes = [
            r
            for r in self.log("operator-notification")
            if r["condition"] == "window-commit"
        ]
        self.assertEqual(len(notes), 1)
