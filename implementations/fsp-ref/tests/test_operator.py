# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
import os
import unittest
from unittest import mock

from helpers import TempDirTest, run_adapter

from fsp import config, lifecycle, operator, sil
from fsp.digest import canonical
from fsp.sil import Refused
from fsp.store import INTEGRITY, Store
from fsp.verify import verify


class Base(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]


class OperatorActs(Base):
    def test_new_store_binding_list(self):
        out = operator.binding_list(self.S)
        self.assertEqual(out, {"bindings": [{"id": "op-1"}], "owner": "op-1"})

    def test_remove_sole_binding_refused(self):
        with self.assertRaises(Refused) as ctx:
            operator.binding_remove(self.S, "op-1")
        self.assertEqual(ctx.exception.check, "last-binding")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)
        bl = operator.binding_list(self.S)
        self.assertEqual(bl["bindings"], [{"id": "op-1"}])
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        self.assertTrue(res.credential_issued)

    def test_add_binding_success(self):
        out = operator.binding_add(self.S, "op-2")
        self.assertEqual(out["entry"], 1)
        self.assertEqual(len(out["log_records"]), 2)
        bl = operator.binding_list(self.S)
        self.assertEqual(bl["bindings"], [{"id": "op-1"}, {"id": "op-2"}])
        self.assertEqual(bl["owner"], "op-1")
        rep = verify(self.S)
        self.assertFalse(rep.findings)
        self.assertEqual(rep.entry_count, 2)

    def test_add_binding_checks(self):
        operator.binding_add(self.S, "op-2")

        # adding op-2 again -> binding-exists
        with self.assertRaises(Refused) as ctx:
            operator.binding_add(self.S, "op-2")
        self.assertEqual(ctx.exception.check, "binding-exists")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")

        # invalid id -> binding-id
        with self.assertRaises(Refused) as ctx:
            operator.binding_add(self.S, "bad id!")
        self.assertEqual(ctx.exception.check, "binding-id")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")

        # non-owner cannot add -> owner-only
        with self.assertRaises(Refused) as ctx:
            operator.binding_add(self.S, "op-3", binding="op-2")
        self.assertEqual(ctx.exception.check, "owner-only")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")

    def test_remove_binding_checks(self):
        operator.binding_add(self.S, "op-2")

        # target not in active -> binding-unknown
        with self.assertRaises(Refused) as ctx:
            operator.binding_remove(self.S, "op-9")
        self.assertEqual(ctx.exception.check, "binding-unknown")

        # with op-2 present, op-1 tries to remove op-1 (owner) -> owner-stays
        with self.assertRaises(Refused) as ctx:
            operator.binding_remove(self.S, "op-1")
        self.assertEqual(ctx.exception.check, "owner-stays")

        # add op-3
        operator.binding_add(self.S, "op-3")

        # non-owner op-2 tries to remove op-3 -> owner-only
        with self.assertRaises(Refused) as ctx:
            operator.binding_remove(self.S, "op-3", binding="op-2")
        self.assertEqual(ctx.exception.check, "owner-only")

        # op-2 removes op-2 -> accepted
        out = operator.binding_remove(self.S, "op-2", binding="op-2")
        self.assertEqual(out["entry"], 3)
        bl = operator.binding_list(self.S)
        self.assertEqual(bl["bindings"], [{"id": "op-1"}, {"id": "op-3"}])

    def test_binding_change_live_session(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            operator.binding_add(self.S, "op-2")
        self.assertEqual(ctx.exception.check, "session-live")
        self.assertEqual(
            ctx.exception.detail,
            "bindings change only outside a session; stop or revoke it first",
        )
        lifecycle.stop(self.S)
        out = operator.binding_add(self.S, "op-2")
        self.assertEqual(out["entry"], 1)

    def test_binding_add_decommissioned(self):
        lifecycle.decommission(self.S, "archive")
        with self.assertRaises(Refused) as ctx:
            operator.binding_add(self.S, "op-2")
        self.assertEqual(ctx.exception.check, "decommissioned")
        self.assertEqual(ctx.exception.rule, "OC-002(c)")

    def test_binding_gate_owner_not_in_active_set(self):
        act = sil.operator_act(self.store, "tamper-bindings", binding="op-1")
        tampered = {"bindings": [{"id": "op-2"}], "owner": "op-1"}
        sil.commit_generation(
            self.store,
            changes={"bindings.json": canonical(tampered)},
            authorization=act,
        )
        res = lifecycle.start(self.S, binding="op-2")
        self.assertEqual(res.outcome, "aborted")
        gates = {g["gate"]: g["outcome"] for g in res.gates}
        self.assertEqual(gates["binding-verification"], "fail")
        aborted_records = self.log("start-aborted")
        self.assertTrue(aborted_records)
        self.assertEqual(
            aborted_records[-1]["reason"],
            "the owner 'op-1' is not an active binding",
        )

    def test_set_workspace_sibling(self):
        ws_path = self.p("sibling_ws")
        self.store.replace_json(
            INTEGRITY, config.OPERATIONAL, {"pre_existing": True}, writer=sil.WRITER
        )
        out = operator.set_workspace(self.S, ws_path)
        real_ws = os.path.realpath(os.path.abspath(ws_path))
        self.assertEqual(out["workspace"], real_ws)
        self.assertEqual(len(out["log_records"]), 1)

        data = self.store.read_json(config.OPERATIONAL)
        self.assertEqual(data["workspace"], real_ws)
        self.assertTrue(data.get("pre_existing"))

        rep = verify(self.S)
        self.assertEqual(rep.entry_count, 1)

        acts = self.log("operator-act")
        self.assertEqual(acts[-1]["act"], "set-workspace")
        self.assertEqual(acts[-1]["binding"], "op-1")
        self.assertEqual(acts[-1]["workspace"], real_ws)

    def test_set_workspace_store_boundaries(self):
        # store itself
        with self.assertRaises(Refused) as ctx:
            operator.set_workspace(self.S, self.S)
        self.assertEqual(ctx.exception.check, "workspace-boundary")
        self.assertEqual(ctx.exception.rule, "OC-008(b)")

        # path inside store
        with self.assertRaises(Refused) as ctx:
            operator.set_workspace(self.S, os.path.join(self.S, "sub"))
        self.assertEqual(ctx.exception.check, "workspace-boundary")

        # directory containing store
        with self.assertRaises(Refused) as ctx:
            operator.set_workspace(self.S, os.path.dirname(self.S))
        self.assertEqual(ctx.exception.check, "workspace-boundary")

    def test_set_workspace_home_boundaries(self):
        fake_home = self.p("fake_home")
        with mock.patch.dict(os.environ, {"HOME": fake_home}):
            # set-workspace in $HOME
            with self.assertRaises(Refused) as ctx:
                operator.set_workspace(self.S, fake_home)
            self.assertEqual(ctx.exception.check, "workspace-boundary")
            self.assertEqual(ctx.exception.rule, "OC-008(b)")

            # set-workspace in $HOME/.fsp/x
            with self.assertRaises(Refused) as ctx:
                operator.set_workspace(self.S, os.path.join(fake_home, ".fsp", "x"))
            self.assertEqual(ctx.exception.check, "workspace-boundary")
            self.assertEqual(ctx.exception.rule, "OC-008(b)")

    def test_boundary_not_prefix_containment(self):
        self.assertFalse(operator._crosses_boundary("/a/bc", "/a/b"))
        self.assertTrue(operator._crosses_boundary("/a/b/c", "/a/b"))
        self.assertTrue(operator._crosses_boundary("/a", "/a/b"))
        self.assertTrue(operator._crosses_boundary("/", "/a/b"))

        s_other = self.S + "_other"
        out = operator.set_workspace(self.S, s_other)
        self.assertEqual(out["workspace"], os.path.realpath(os.path.abspath(s_other)))

    def test_adapter_operator_commands(self):
        # binding-list
        code, out = run_adapter("operator", "binding-list", "--store", self.S)
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(out["detail"]["bindings"], [{"id": "op-1"}])
        self.assertEqual(out["detail"]["owner"], "op-1")

        # binding-remove of last binding (refused, exit 0)
        code, out = run_adapter("operator", "binding-remove", "--store", self.S, "--id", "op-1")
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["refusal"]["check"], "last-binding")
        self.assertEqual(out["refusal"]["rule"], "OC-001(a)")

        # set-workspace (accepted)
        ws = self.p("ws")
        code, out = run_adapter("operator", "set-workspace", "--store", self.S, "--path", ws)
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(out["detail"]["workspace"], os.path.realpath(os.path.abspath(ws)))

        # binding-add without --id -> exit 1
        code, out = run_adapter("operator", "binding-add", "--store", self.S)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
