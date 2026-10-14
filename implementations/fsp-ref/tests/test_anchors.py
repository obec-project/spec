# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

import os

from helpers import TempDirTest

from fsp import digest, lifecycle, operator, proposals, sil
from fsp.sil import Refused
from fsp.store import INTEGRITY, GuardError, Store
from fsp_testing import fixture


class TrailingNewlineTests(TempDirTest):
    """A name, id or path that matches a pattern but for a final newline is
    refused: every pattern is anchored at the end of the string."""

    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def test_a_skill_name_is_refused_at_propose(self):
        lifecycle.start(self.S)
        ops = [
            {"op": "install-skill", "name": "x\n", "files": fixture.skill_files("x")},
            {"op": "deny-skill", "name": "x\n"},
        ]
        for op in ops:
            with self.subTest(op=op["op"]):
                with self.assertRaises(Refused) as ctx:
                    proposals.propose(self.S, [op])
                self.assertEqual(ctx.exception.check, "ops")

    def test_a_digest_is_refused_at_propose(self):
        lifecycle.start(self.S)
        op = {"op": "allow-skill", "name": "x", "digest": "sha256:" + "0" * 64 + "\n"}
        with self.assertRaises(Refused) as ctx:
            proposals.propose(self.S, [op])
        self.assertEqual(ctx.exception.check, "ops")

    def test_a_binding_id_is_refused(self):
        with self.assertRaises(Refused) as ctx:
            operator.binding_add(self.S, "op-2\n")
        self.assertEqual(ctx.exception.check, "binding-id")
        with self.assertRaises(Refused):
            sil.first_activation(self.p("T"), "op-1\n")

    def test_an_expiry_is_refused(self):
        with self.assertRaises(ValueError):
            proposals.parse_expiry("+1h\n")

    def test_a_file_name_is_not_structural_content(self):
        gen = self.p("gen")
        os.makedirs(gen)
        with open(os.path.join(gen, "x\n"), "wb") as f:
            f.write(b"x")
        document, problems = digest.integrity_document(gen)
        self.assertEqual(document, [])
        self.assertEqual(problems, [{"path": "x\n", "problem": "bad-name"}])

    def test_a_store_path_is_no_datum(self):
        with self.assertRaises(GuardError):
            self.store.replace(
                INTEGRITY, lifecycle.AUTH + "\n", b"{}", writer=sil.WRITER
            )
        self.assertFalse(os.path.exists(self.store.path(lifecycle.AUTH + "\n")))
