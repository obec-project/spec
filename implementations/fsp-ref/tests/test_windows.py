# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Tests for authorization windows and the test clock (D17, D50, D59, OC-001(b))."""

import os
import unittest

from helpers import TempDirTest, run_adapter

from fsp import clock, lifecycle, operator, proposals, sil
from fsp.sil import Refused
from fsp.store import INTEGRITY, Store
from fsp_testing import fixture, hooks


class Base(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def tearDown(self):
        hooks.clear_clock(self.S)
        super().tearDown()

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]


class WindowsTests(Base):
    def test_grant_unbounded_checks(self):
        """grant missing each axis -> grant-unbounded naming the axis in detail."""
        for omit, kwargs in (
            ("expiry", {"budget": 5, "scope": "skills"}),
            ("budget", {"expiry": "+1h", "scope": "skills"}),
            ("scope", {"expiry": "+1h", "budget": 5}),
        ):
            with self.subTest(omit=omit):
                with self.assertRaises(Refused) as ctx:
                    operator.grant(self.S, **kwargs)
                self.assertEqual(ctx.exception.check, "grant-unbounded")
                self.assertEqual(ctx.exception.rule, "OC-001(b)")
                self.assertIn(omit, ctx.exception.detail)

    def test_grant_scope_checks(self):
        """grant with binding-set -> scope (OC-001(a)); undeclared -> scope (OC-001(b)); valid -> accepted."""
        for bad_scope, rule in (
            ("binding-set", "OC-001(a)"),
            ("bindings", "OC-001(a)"),
            ("persona", "OC-001(b)"),
            ("probes", "OC-001(b)"),
            ("configuration", "OC-001(b)"),
        ):
            with self.subTest(scope=bad_scope):
                with self.assertRaises(Refused) as ctx:
                    operator.grant(self.S, expiry="+1h", budget=5, scope=bad_scope)
                self.assertEqual(ctx.exception.check, "scope")
                self.assertEqual(ctx.exception.rule, rule)

        # valid scopes accepted
        out1 = operator.grant(self.S, expiry="+1h", budget=5, scope="skills")
        self.assertTrue(out1["grant"].startswith("L-"))
        out2 = operator.grant(self.S, expiry="+1h", budget=5, scope="skills.install")
        self.assertTrue(out2["grant"].startswith("L-"))

    def test_grant_budget_and_expiry_validation(self):
        """grant with budget 0 or 'x' -> grant-budget; expiry '1h' or '+1y' -> grant-expiry."""
        for bad_budget in (0, "0", "x", "\u00b2"):
            with self.subTest(budget=bad_budget):
                with self.assertRaises(Refused) as ctx:
                    operator.grant(self.S, expiry="+1h", budget=bad_budget, scope="skills")
                self.assertEqual(ctx.exception.check, "grant-budget")
                self.assertEqual(ctx.exception.rule, "OC-001(b)")

        for bad_expiry in ("1h", "+1y", "invalid"):
            with self.subTest(expiry=bad_expiry):
                with self.assertRaises(Refused) as ctx:
                    operator.grant(self.S, expiry=bad_expiry, budget=5, scope="skills")
                self.assertEqual(ctx.exception.check, "grant-expiry")
                self.assertEqual(ctx.exception.rule, "OC-001(b)")

    def test_grant_without_live_session_accepted(self):
        """grant without a live session is accepted, recorded in auth.json and logged."""
        out = operator.grant(self.S, expiry="+1h", budget=5, scope="skills")
        gid = out["grant"]
        auth = proposals.read_auth(self.store)
        self.assertEqual(len(auth["grants"]), 1)
        g = auth["grants"][0]
        self.assertEqual(g["id"], gid)
        self.assertEqual(g["scope"], "skills")
        self.assertEqual(g["budget"], 5)
        self.assertEqual(g["used"], 0)
        self.assertEqual(g["state"], "open")

        acts = self.log("operator-act")
        self.assertEqual(acts[-1]["id"], gid)
        self.assertEqual(acts[-1]["act"], "grant")
        self.assertEqual(acts[-1]["rule"], "OC-001(b)")

    def test_install_skill_under_covering_window(self):
        """install-skill under a skills window with budget 5 -> commit accepted, authorization is grant id, used==1."""
        lifecycle.start(self.S)
        out_g = operator.grant(self.S, expiry="+1h", budget=5, scope="skills")
        gid = out_g["grant"]

        ops = [{"op": "install-skill", "name": "example", "files": fixture.skill_files("example")}]
        prop = proposals.propose(self.S, ops)
        pid = prop["proposal"]

        res = proposals.commit(self.S, pid)
        self.assertEqual(res["authorization"], gid)

        auth = proposals.read_auth(self.store)
        g = [x for x in auth["grants"] if x["id"] == gid][0]
        self.assertEqual(g["used"], 1)
        self.assertEqual(g["state"], "open")

    def test_budget_exhaustion_closes_window(self):
        """budget 1: first commit accepted and window closes (exhausted); second commit refused with authorization."""
        lifecycle.start(self.S)
        out_g = operator.grant(self.S, expiry="+1h", budget=1, scope="skills")
        gid = out_g["grant"]

        ops1 = [{"op": "install-skill", "name": "s1", "files": {"SKILL.md": "skill 1"}}]
        p1 = proposals.propose(self.S, ops1)["proposal"]
        res1 = proposals.commit(self.S, p1)
        self.assertEqual(res1["authorization"], gid)

        auth = proposals.read_auth(self.store)
        g = [x for x in auth["grants"] if x["id"] == gid][0]
        self.assertEqual(g["used"], 1)
        self.assertEqual(g["state"], "closed")
        self.assertEqual(g["closed"], "exhausted")

        closed_logs = self.log("grant-closed")
        self.assertEqual(closed_logs[-1]["grant"], gid)
        self.assertEqual(closed_logs[-1]["reason"], "exhausted")

        ops2 = [{"op": "install-skill", "name": "s2", "files": {"SKILL.md": "skill 2"}}]
        p2 = proposals.propose(self.S, ops2)["proposal"]
        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, p2)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

    def test_expired_window_refuses_commit(self):
        """window opened with -1h -> commit refused with authorization, window marked closed/expired."""
        lifecycle.start(self.S)
        out_g = operator.grant(self.S, expiry="-1h", budget=5, scope="skills")
        gid = out_g["grant"]

        ops = [{"op": "install-skill", "name": "example", "files": fixture.skill_files("example")}]
        pid = proposals.propose(self.S, ops)["proposal"]

        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

        auth = proposals.read_auth(self.store)
        g = [x for x in auth["grants"] if x["id"] == gid][0]
        self.assertEqual(g["state"], "closed")
        self.assertEqual(g["closed"], "expired")

    def test_window_out_of_scope_refuses_commit(self):
        """window rules (out of scope for skills.install) -> authorization refusal."""
        lifecycle.start(self.S)
        operator.grant(self.S, expiry="+1h", budget=5, scope="rules")

        ops = [{"op": "install-skill", "name": "example", "files": fixture.skill_files("example")}]
        pid = proposals.propose(self.S, ops)["proposal"]

        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

    def test_persona_proposal_never_covered_by_window(self):
        """set-persona proposal with open skills window -> authorization refusal (persona only by approval)."""
        lifecycle.start(self.S)
        operator.grant(self.S, expiry="+1h", budget=5, scope="skills")

        ops = [{"op": "set-persona", "content": "You are a friendly entity."}]
        pid = proposals.propose(self.S, ops)["proposal"]

        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

    def test_approval_takes_precedence_over_window(self):
        """with approval and open window, commit uses approval and does not spend window budget."""
        lifecycle.start(self.S)
        out_g = operator.grant(self.S, expiry="+1h", budget=5, scope="skills")
        gid = out_g["grant"]

        ops = [{"op": "install-skill", "name": "example", "files": fixture.skill_files("example")}]
        pid = proposals.propose(self.S, ops)["proposal"]

        out_appr = operator.approve(self.S, pid)
        appr_id = out_appr["log_records"][0]

        res = proposals.commit(self.S, pid)
        self.assertEqual(res["authorization"], appr_id)

        auth = proposals.read_auth(self.store)
        g = [x for x in auth["grants"] if x["id"] == gid][0]
        self.assertEqual(g["used"], 0)

    def test_clock_advance_and_expiry(self):
        """window +1s, hooks.advance_clock(root, 5) -> commit refused, window expired, clock.grant_now advanced."""
        lifecycle.start(self.S)
        out_g = operator.grant(self.S, expiry="+1s", budget=5, scope="skills")
        gid = out_g["grant"]

        ops = [{"op": "install-skill", "name": "example", "files": fixture.skill_files("example")}]
        pid = proposals.propose(self.S, ops)["proposal"]

        hooks.advance_clock(self.S, 5)
        diff = (clock.grant_now(self.S) - clock.now()).total_seconds()
        self.assertAlmostEqual(diff, 5, delta=1)

        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "authorization")

        auth = proposals.read_auth(self.store)
        g = [x for x in auth["grants"] if x["id"] == gid][0]
        self.assertEqual(g["state"], "closed")
        self.assertEqual(g["closed"], "expired")

    def test_gate_5_closes_lapsed_window(self):
        """gate 5 closes expired window on start (open with -1h, lifecycle.start -> closed and grant-closed logged)."""
        out_g = operator.grant(self.S, expiry="-1h", budget=5, scope="skills")
        gid = out_g["grant"]

        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")

        auth = proposals.read_auth(self.store)
        g = [x for x in auth["grants"] if x["id"] == gid][0]
        self.assertEqual(g["state"], "closed")
        self.assertEqual(g["closed"], "expired")

        closed_logs = self.log("grant-closed")
        self.assertTrue(any(l.get("grant") == gid and l.get("reason") == "expired" for l in closed_logs))

    def test_gate_5_aborts_on_malformed_grants(self):
        """grants that is not a list -> the start aborts at authorization-state."""
        self.store.replace_json(INTEGRITY, lifecycle.AUTH, {"grants": 5}, writer=sil.WRITER)

        res = lifecycle.start(self.S)
        self.assertEqual((res.outcome, res.gates[-1]["gate"]), ("aborted", "authorization-state"))

    def test_revoke_grant(self):
        """revoke_grant closes open windows (revoked) and is accepted with none."""
        out_g1 = operator.grant(self.S, expiry="+1h", budget=5, scope="skills")
        out_g2 = operator.grant(self.S, expiry="+2h", budget=3, scope="rules")
        gids = [out_g1["grant"], out_g2["grant"]]

        rev = operator.revoke_grant(self.S)
        self.assertEqual(sorted(rev["revoked"]), sorted(gids))

        auth = proposals.read_auth(self.store)
        for g in auth["grants"]:
            self.assertEqual(g["state"], "closed")
            self.assertEqual(g["closed"], "revoked")
            self.assertEqual(g["revoked_by"], rev["log_records"][0])

        # second revoke with no open windows accepted
        rev2 = operator.revoke_grant(self.S)
        self.assertEqual(rev2["revoked"], [])

    def test_adapter_windows_commands(self):
        """adapter commands for operator grant, revoke-grant, and inject advance-clock."""
        # operator grant accepted with grant in detail
        code, out = run_adapter(
            "operator", "grant", "--store", self.S, "--expiry", "+1h", "--budget", "5", "--scope", "skills"
        )
        self.assertEqual(code, 0)
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("detail", {}).get("grant", "").startswith("L-"))

        # operator grant without --scope -> refused
        code, out = run_adapter(
            "operator", "grant", "--store", self.S, "--expiry", "+1h", "--budget", "5"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.get("outcome"), "refused")
        self.assertEqual(out.get("refusal", {}).get("check"), "grant-unbounded")

        # operator revoke-grant accepted
        code, out = run_adapter("operator", "revoke-grant", "--store", self.S)
        self.assertEqual(code, 0)
        self.assertTrue(out.get("ok"))
        self.assertIn("revoked", out.get("detail", {}))

        # inject advance-clock --seconds 5 accepted
        code, out = run_adapter("inject", "advance-clock", "--store", self.S, "--seconds", "5")
        self.assertEqual(code, 0)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("detail", {}).get("offset"), 5)

        # inject advance-clock --seconds -1 -> exit code 1
        code, _out = run_adapter("inject", "advance-clock", "--store", self.S, "--seconds", "-1")
        self.assertEqual(code, 1)
