# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
import json
import os
import unittest

from helpers import TempDirTest, run_adapter

from fsp import chain, lifecycle, operator, proposals, sil
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


class ProposalsTests(Base):
    def test_propose_with_live_session_success(self):
        lifecycle.start(self.S)
        ops = [{"op": "set-persona", "content": "You are a helpful assistant."}]
        out = proposals.propose(self.S, ops)
        pid = out["proposal"]
        self.assertTrue(pid.startswith("P-"))
        self.assertEqual(len(out["log_records"]), 1)

        auth = self.store.read_json(lifecycle.AUTH)
        self.assertIn(pid, auth["proposals"])
        self.assertTrue(auth["proposals"][pid]["digest"])

        props = self.log("proposal")
        self.assertEqual(props[-1]["proposal"], pid)
        self.assertEqual(props[-1]["ops"], ops)

    def test_propose_without_live_session_refused(self):
        ops = [{"op": "set-persona", "content": "Hello"}]
        with self.assertRaises(Refused) as ctx:
            proposals.propose(self.S, ops)
        self.assertEqual(ctx.exception.check, "no-session")
        self.assertEqual(ctx.exception.rule, "OC-002(b)")

    def test_propose_targeting_binding_set_refused(self):
        # Without session
        with self.assertRaises(Refused) as ctx:
            proposals.propose(self.S, [{"op": "add-binding", "id": "op-2"}])
        self.assertEqual(ctx.exception.check, "binding-set")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")

        # With session, combined with valid set-persona
        lifecycle.start(self.S)
        bad_ops = [
            {"op": "set-persona", "content": "Good"},
            {"op": "remove-binding", "id": "op-1"},
        ]
        with self.assertRaises(Refused) as ctx:
            proposals.propose(self.S, bad_ops)
        self.assertEqual(ctx.exception.check, "binding-set")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")

    def test_propose_invalid_ops(self):
        lifecycle.start(self.S)

        # op-unknown
        with self.assertRaises(Refused) as ctx:
            proposals.propose(self.S, [{"op": "unknown-op"}])
        self.assertEqual(ctx.exception.check, "op-unknown")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

        # ops: empty list
        with self.assertRaises(Refused) as ctx:
            proposals.propose(self.S, [])
        self.assertEqual(ctx.exception.check, "ops")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

        # ops: set-persona without content
        with self.assertRaises(Refused) as ctx:
            proposals.propose(self.S, [{"op": "set-persona"}])
        self.assertEqual(ctx.exception.check, "ops")

        # ops: install-skill with bad name
        with self.assertRaises(Refused) as ctx:
            proposals.propose(
                self.S, [{"op": "install-skill", "name": "Bad Name", "files": {"f": "c"}}]
            )
        self.assertEqual(ctx.exception.check, "ops")

        # ops: install-skill with path "../x"
        with self.assertRaises(Refused) as ctx:
            proposals.propose(
                self.S, [{"op": "install-skill", "name": "good", "files": {"../x": "c"}}]
            )
        self.assertEqual(ctx.exception.check, "ops")

        # ops: install-skill with path "/x"
        with self.assertRaises(Refused) as ctx:
            proposals.propose(
                self.S, [{"op": "install-skill", "name": "good", "files": {"/x": "c"}}]
            )
        self.assertEqual(ctx.exception.check, "ops")

        # ops: two set-persona in same proposal
        with self.assertRaises(Refused) as ctx:
            proposals.propose(
                self.S,
                [
                    {"op": "set-persona", "content": "1"},
                    {"op": "set-persona", "content": "2"},
                ],
            )
        self.assertEqual(ctx.exception.check, "ops")

    def test_commit_without_approval_refused(self):
        lifecycle.start(self.S)
        out = proposals.propose(self.S, [{"op": "set-persona", "content": "Neutral persona"}])
        pid = out["proposal"]
        head_before = sil.read_head(self.store)

        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")
        self.assertEqual(sil.read_head(self.store), head_before)

    def test_approve_unknown_proposal_refused(self):
        with self.assertRaises(Refused) as ctx:
            operator.approve(self.S, "P-nonexistent")
        self.assertEqual(ctx.exception.check, "proposal-unknown")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

    def test_approve_and_commit_neutral_persona_success(self):
        lifecycle.start(self.S)
        head_before = sil.read_head(self.store)
        content = "You are a helpful software assistant."
        out_p = proposals.propose(self.S, [{"op": "set-persona", "content": content}])
        pid = out_p["proposal"]

        out_a = operator.approve(self.S, pid)
        appr_rec = out_a["log_records"][0]

        out_c = proposals.commit(self.S, pid)
        self.assertEqual(out_c["authorization"], appr_rec)
        self.assertEqual(out_c["entry"], head_before["entry"] + 1)

        head_after = sil.read_head(self.store)
        self.assertEqual(head_after["entry"], head_before["entry"] + 1)
        gen_rel = chain.gen_relpath(head_after["entry"])
        self.assertEqual(
            self.store.read_bytes(gen_rel + "/persona.md"), content.encode("utf-8")
        )

        chain_entry = self.store.read_json(chain.entry_relpath(head_after["entry"]))
        self.assertEqual(chain_entry["authorization"], appr_rec)

        auth = self.store.read_json(lifecycle.AUTH)
        self.assertNotIn(pid, auth.get("proposals", {}))
        self.assertNotIn(pid, auth.get("approvals", {}))

        commit_logs = self.log("commit")
        self.assertEqual(commit_logs[-1]["authorization"], appr_rec)

    def test_approve_and_commit_subjective_persona_refused(self):
        lifecycle.start(self.S)
        head_before = sil.read_head(self.store)
        out_p = proposals.propose(
            self.S, [{"op": "set-persona", "content": "You are a conscious being."}]
        )
        pid = out_p["proposal"]
        operator.approve(self.S, pid)

        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "self-representation")
        self.assertEqual(ctx.exception.rule, "OC-002(d)")
        self.assertEqual(sil.read_head(self.store), head_before)

        auth = self.store.read_json(lifecycle.AUTH)
        self.assertIn(pid, auth.get("proposals", {}))

    def test_commit_with_tampered_approval_digest_refused(self):
        lifecycle.start(self.S)
        out_p = proposals.propose(self.S, [{"op": "set-persona", "content": "Valid content"}])
        pid = out_p["proposal"]

        proposals.record_approval(self.store, pid, "sha256:tampered_digest", "fake-rec", "op-1")
        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

    def test_install_skill_flow(self):
        lifecycle.start(self.S)
        files = fixture.skill_files("example")
        out_p = proposals.propose(
            self.S, [{"op": "install-skill", "name": "example", "files": files}]
        )
        pid = out_p["proposal"]
        operator.approve(self.S, pid)
        out_c = proposals.commit(self.S, pid)
        self.assertEqual(out_c["entry"], 1)

        lifecycle.stop(self.S)
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        idx = self.store.read_json(lifecycle.INDEX)
        self.assertIn("example", [s["name"] for s in idx["skills"]])

        # Second install of same skill
        out_p2 = proposals.propose(
            self.S, [{"op": "install-skill", "name": "example", "files": files}]
        )
        pid2 = out_p2["proposal"]
        operator.approve(self.S, pid2)
        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid2)
        self.assertEqual(ctx.exception.check, "skill-exists")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

    def test_commit_no_session_and_double_commit(self):
        lifecycle.start(self.S)
        out_p = proposals.propose(self.S, [{"op": "set-persona", "content": "Helpful"}])
        pid = out_p["proposal"]
        operator.approve(self.S, pid)
        lifecycle.stop(self.S)

        # Commit without session
        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "no-session")

        # Commit with session
        lifecycle.start(self.S)
        proposals.commit(self.S, pid)

        # Commit second time -> proposal-unknown
        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "proposal-unknown")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

    def test_adapter_proposals_commands(self):
        run_adapter("lifecycle", "start", "--store", self.S)
        ops_file = self.p("ops.json")
        with open(ops_file, "w", encoding="utf-8") as f:
            json.dump([{"op": "install-skill", "name": "example"}], f)

        # Propose without files (fixture auto-supplies files)
        code, out = run_adapter("entity", "propose", "--store", self.S, "--ops", ops_file)
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        pid = out["detail"]["proposal"]

        # Operator approve
        code, out = run_adapter("operator", "approve", "--store", self.S, "--proposal", pid)
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")

        # Entity commit
        code, out = run_adapter("entity", "commit", "--store", self.S, "--proposal", pid)
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertTrue(out["detail"]["authorization"])

        # Entity propose without --ops -> exit 1
        code, out = run_adapter("entity", "propose", "--store", self.S)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
