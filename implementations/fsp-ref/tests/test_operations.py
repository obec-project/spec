# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

import os
import re
import unittest

from helpers import ROOT, TempDirTest, run_adapter

from fsp import describe, operations, sil
from fsp.store import CLASSES, OWNER


def defines(text, symbol):
    """Whether ``text`` defines every part of ``symbol``, a name or a dotted
    ``Class.member``: a ``def`` or ``class`` of that name, or an assignment
    to it, at the start of a line."""
    for part in symbol.split("."):
        pattern = r"^\s*(?:def|class)\s+%s\b|^\s*%s\s*=" % (
            re.escape(part),
            re.escape(part),
        )
        if not re.search(pattern, text, re.MULTILINE):
            return False
    return True


class OperationsTable(unittest.TestCase):
    def test_describe_lists_the_operations_the_code_has(self):
        ops = describe.operations_table()["operations"]
        self.assertEqual(
            [o["name"] for o in ops],
            [
                "propose",
                "commit",
                "integrity-write",
                "mnemonic-save",
                "file_read",
                "file_write",
                "file_list",
                "http_fetch",
                "invoke-skill",
            ],
        )
        for o in ops:
            self.assertEqual(
                set(o),
                {
                    "name",
                    "reachable_from_cognition",
                    "writes_classes",
                    "host_access",
                    "irreversible",
                },
            )
        self.assertEqual(
            [o["writes_classes"] for o in ops],
            [[], ["structural"], ["integrity"], ["mnemonic"], [], [], [], [], []],
        )

    def test_each_class_has_exactly_one_write_path_and_it_is_the_guard_s(self):
        ops = describe.operations_table()["operations"]
        for cls in CLASSES:
            writers = [o for o in ops if cls in o["writes_classes"]]
            self.assertEqual(len(writers), 1, cls)
            self.assertEqual(writers[0]["name"], OWNER[cls][1])

    def test_no_cognition_reachable_operation_writes_integrity(self):
        ops = describe.operations_table()["operations"]
        reachable = [o for o in ops if o["reachable_from_cognition"]]
        self.assertTrue(reachable)
        for o in reachable:
            self.assertNotIn("integrity", o["writes_classes"])

    def test_every_describe_points_at_a_definition(self):
        commands = [
            ("state", ["describe", "state", "--store", os.path.join(ROOT, "no-store")]),
            ("config", ["describe", "config"]),
            ("operations", ["describe", "operations"]),
        ]
        for name, args in commands:
            with self.subTest(command=name):
                code, out = run_adapter(*args)
                self.assertEqual(code, 0)
                evidence = out["detail"]["evidence"]
                self.assertTrue(evidence)
                for e in evidence:
                    with self.subTest(path=e["path"], symbol=e["symbol"]):
                        self.assertTrue(e["path"].startswith(describe.REPO_PREFIX))
                        path = os.path.join(
                            ROOT, e["path"][len(describe.REPO_PREFIX) :]
                        )
                        self.assertTrue(os.path.exists(path), path)
                        with open(path, encoding="utf-8") as f:
                            self.assertTrue(defines(f.read(), e["symbol"]))

    def test_defines_takes_a_definition_and_not_a_mention(self):
        self.assertTrue(defines("def propose(ops):\n", "propose"))
        self.assertTrue(defines("OPERATIONS = (\n", "OPERATIONS"))
        self.assertTrue(
            defines("class Store:\n    def _guard(self):\n", "Store._guard")
        )
        self.assertFalse(defines("out = propose(ops)\n", "propose"))
        self.assertFalse(defines("def proposed(x):\n", "propose"))
        self.assertFalse(defines("# propose is the SIL's\n", "propose"))
        self.assertFalse(defines("class Store:\n", "Store._guard"))


class AttemptWrite(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")

    def test_an_admitted_attempt_names_what_it_would_write(self):
        self.assertEqual(
            operations.attempt_write(
                self.S, "integrity", "integrity-write", "authorization-state"
            ),
            {
                "operation": "integrity-write",
                "content_class": "integrity",
                "would_write": [
                    {"datum": "authorization-state", "path": "integrity/auth.json"}
                ],
            },
        )

    def test_an_unknown_operation_is_a_key_error(self):
        with self.assertRaises(KeyError):
            operations.attempt_write(
                self.S, "integrity", "nowhere", "authorization-state"
            )

    def test_adapter_describe_operations(self):
        code, out = run_adapter("describe", "operations")
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(len(out["detail"]["operations"]), 9)
        self.assertTrue(out["detail"]["evidence"])

    def test_adapter_refuses_an_integrity_write_from_cognition_with_the_triple(self):
        for via in ("propose", "mnemonic-save"):
            with self.subTest(via=via):
                code, out = run_adapter(
                    "entity",
                    "attempt-write",
                    "--store",
                    self.S,
                    "--class",
                    "integrity",
                    "--via",
                    via,
                    "--target",
                    "authorization-state",
                )
                self.assertEqual(code, 0)
                self.assertEqual(out["outcome"], "refused")
                refusal = out["refusal"]
                self.assertEqual(refusal["check"], "sole-writer")
                self.assertEqual(refusal["rule"], "OC-003(c)")
                self.assertTrue(out["log_records"])
                _, log = run_adapter("observe", "log", "--store", self.S)
                logged = {r.get("id") for r in log["detail"]["records"]}
                for rec_id in out["log_records"]:
                    self.assertIn(rec_id, logged)

    def test_adapter_admits_the_cpe_s_destination_and_logs_nothing(self):
        code, out = run_adapter(
            "entity",
            "attempt-write",
            "--store",
            self.S,
            "--class",
            "mnemonic",
            "--via",
            "mnemonic-save",
            "--target",
            "episodic-memory",
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(
            out["detail"]["would_write"],
            [{"datum": "episodic-memory", "path": "memory/episodic/records.jsonl"}],
        )
        self.assertEqual(out["log_records"], [])

    def test_host_operations_refuse_every_class(self):
        for via in ("file_read", "file_write", "file_list", "invoke-skill"):
            for cls in CLASSES:
                with self.subTest(via=via, cls=cls):
                    with self.assertRaises(sil.Refused) as ctx:
                        operations.attempt_write(self.S, cls, via, "class:" + cls)
                    self.assertEqual(ctx.exception.check, "sole-writer")

    def test_adapter_cannot_attempt_without_an_operation_a_target_or_a_store(self):
        base = ["entity", "attempt-write", "--store", self.S, "--class", "integrity"]
        cases = [
            base + ["--via", "nowhere", "--target", "authorization-state"],
            base + ["--via", "integrity-write"],
            [
                "entity",
                "attempt-write",
                "--store",
                self.p("absent"),
                "--class",
                "integrity",
                "--via",
                "integrity-write",
                "--target",
                "authorization-state",
            ],
        ]
        for args in cases:
            with self.subTest(args=args):
                code, _ = run_adapter(*args)
                self.assertEqual(code, 1)
