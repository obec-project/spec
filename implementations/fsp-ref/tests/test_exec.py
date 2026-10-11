# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

import os

from helpers import TempDirTest, run_adapter

from fsp import exec as execution
from fsp import ledger, lifecycle, operator, sil
from fsp.sil import Refused
from fsp.store import Store


class ExecTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        self.W = self.p("W")
        os.makedirs(self.W)
        sil.first_activation(self.S, "op-1")
        operator.set_workspace(self.S, self.W)
        self.store = Store(self.S)
        self.inside = os.path.join(self.W, "inside.txt")
        with open(self.inside, "wb") as f:
            f.write(b"hello")

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def test_read_returns_the_content_and_logs_it(self):
        lifecycle.start(self.S)
        out = execution.file_read(self.S, self.inside)
        self.assertEqual(out["data"], b"hello")
        self.assertEqual(out["size"], 5)
        self.assertEqual(out["target"], "inside.txt")
        last = self.log("execution")[-1]
        self.assertEqual(last["op"], "file_read")
        self.assertEqual(last["target"], "inside.txt")
        self.assertEqual(last["outcome"], "done")

    def test_write_goes_through_the_ledger(self):
        lifecycle.start(self.S)
        out = execution.file_write(self.S, "notes/a.txt", b"x", intent="test")
        with open(os.path.join(self.W, "notes", "a.txt"), "rb") as f:
            self.assertEqual(f.read(), b"x")
        records = self.store.read_jsonl(ledger.LEDGER)[0]
        self.assertEqual(records[0]["kind"], "open")
        self.assertEqual(records[0]["id"], out["ledger"])
        self.assertEqual(records[0]["target"], "notes/a.txt")
        self.assertEqual(records[1]["kind"], "resolve")
        self.assertEqual(records[1]["entry"], out["ledger"])
        self.assertEqual(records[1]["outcome"], "done")
        self.assertEqual(self.log("execution")[-1]["ledger"], out["ledger"])

    def test_list_names_the_entries(self):
        lifecycle.start(self.S)
        with open(os.path.join(self.W, "b.txt"), "wb") as f:
            f.write(b"")
        self.assertEqual(
            execution.file_list(self.S, self.W)["entries"], ["b.txt", "inside.txt"]
        )

    def test_outside_and_traversal_are_refused(self):
        lifecycle.start(self.S)
        for target in (
            self.p("outside.txt"),
            os.path.join(self.W, "..", "outside.txt"),
        ):
            with self.subTest(target=target):
                with self.assertRaises(Refused) as ctx:
                    execution.file_read(self.S, target)
                self.assertEqual(ctx.exception.check, "workspace-boundary")
                self.assertEqual(ctx.exception.rule, "OC-008(a)")
                self.assertTrue(ctx.exception.log_records)

    def test_a_symlink_leaving_the_workspace_is_refused(self):
        lifecycle.start(self.S)
        with open(self.p("outside.txt"), "wb") as f:
            f.write(b"secret")
        os.symlink(self.p("outside.txt"), os.path.join(self.W, "link"))
        with self.assertRaises(Refused) as ctx:
            execution.file_read(self.S, os.path.join(self.W, "link"))
        self.assertEqual(ctx.exception.check, "workspace-boundary")

    def test_a_path_inside_the_store_is_refused(self):
        lifecycle.start(self.S)
        target = os.path.join(self.S, "anything")
        with self.assertRaises(Refused) as ctx:
            execution.file_write(self.S, target, b"", intent="t")
        self.assertEqual(ctx.exception.check, "workspace-boundary")
        self.assertEqual(ctx.exception.rule, "OC-008(b)")
        self.assertFalse(os.path.exists(os.path.join(self.S, "anything")))

    def test_no_workspace_refuses(self):
        S2 = self.p("S2")
        sil.first_activation(S2, "op-2")
        lifecycle.start(S2)
        with self.assertRaises(Refused) as ctx:
            execution.file_list(S2, "x")
        self.assertEqual(ctx.exception.check, "workspace-boundary")

    def test_the_boundary_comes_before_the_session(self):
        with self.assertRaises(Refused) as ctx:
            execution.file_read(self.S, self.p("outside.txt"))
        self.assertEqual(ctx.exception.check, "workspace-boundary")
        with self.assertRaises(Refused) as ctx:
            execution.file_read(self.S, self.inside)
        self.assertEqual(ctx.exception.check, "no-session")

    def test_adapter_actuate(self):
        run_adapter("lifecycle", "start", "--store", self.S)

        code, out = run_adapter(
            "entity",
            "actuate",
            "--store",
            self.S,
            "--op",
            "read",
            "--target",
            self.inside,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(out["detail"]["size"], 5)
        self.assertIn("sha256", out["detail"])
        self.assertNotIn("data", out["detail"])

        target = os.path.join(self.W, "empty.txt")
        code, out = run_adapter(
            "entity",
            "actuate",
            "--store",
            self.S,
            "--op",
            "write",
            "--target",
            target,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(os.path.getsize(target), 0)

        code, out = run_adapter(
            "entity",
            "actuate",
            "--store",
            self.S,
            "--op",
            "read",
            "--target",
            self.p("outside.txt"),
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["refusal"]["check"], "workspace-boundary")
        self.assertTrue(out["log_records"])

        code, _ = run_adapter(
            "entity",
            "actuate",
            "--store",
            self.S,
            "--op",
            "execute",
            "--target",
            self.inside,
        )
        self.assertEqual(code, 1)

    def test_a_revoked_session_refuses_inside_the_workspace(self):
        lifecycle.start(self.S)
        lifecycle.revoke_credential(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.file_read(self.S, self.inside)
        self.assertEqual(ctx.exception.check, "no-session")
