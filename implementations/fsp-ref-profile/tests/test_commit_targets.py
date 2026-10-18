# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

import os

from helpers import TempDirTest

from fsp import lifecycle, sil
from fsp.digest import canonical
from fsp.sil import Refused
from fsp.store import STRUCTURAL_FILES, Store, structural_target


class CommitTargetsTest(TempDirTest):
    """The commit admits only the structural data the store declares (D68)."""

    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def approval(self):
        return sil.operator_act_located(
            self.store, "approve", binding="op-1", rule="OC-001(b)"
        )

    def refusals(self):
        return lifecycle.observe_log(self.S, kind="refusal")["records"]

    def test_structural_target_admits_only_the_declared_data(self):
        for rel in STRUCTURAL_FILES:
            self.assertTrue(structural_target(rel), rel)
        for rel in ("skills/example/manifest.json", "skills/example/bin/run"):
            self.assertTrue(structural_target(rel), rel)
        for rel in (
            "integrity/auth.json",
            "HEAD",
            "notes.txt",
            "skills/example",
            "skills/Bad/run",
            "skills/example/../run",
            "skills//run",
            "",
            None,
        ):
            self.assertFalse(structural_target(rel), repr(rel))

    def test_a_commit_of_an_undeclared_path_is_refused_before_any_write(self):
        head_before = sil.read_head(self.store)
        with self.assertRaises(Refused) as cm:
            sil.commit_generation(
                self.store,
                changes={"integrity/auth.json": b"{}"},
                authorization=self.approval(),
            )
        self.assertEqual(cm.exception.check, "content-class")
        self.assertEqual(cm.exception.rule, "OC-003(c)")
        self.assertTrue(cm.exception.log_records)
        self.assertEqual(sil.read_head(self.store), head_before)
        self.assertFalse(os.path.exists(self.store.path("structural/gen/1")))
        self.assertEqual(self.refusals()[-1]["check"], "content-class")

    def test_one_undeclared_path_refuses_the_whole_commit(self):
        head_before = sil.read_head(self.store)
        with self.assertRaises(Refused) as cm:
            sil.commit_generation(
                self.store,
                changes={
                    "persona.md": b"You are a helpful assistant.",
                    "notes.txt": b"x",
                },
                authorization=self.approval(),
            )
        self.assertEqual(cm.exception.check, "content-class")
        self.assertEqual(sil.read_head(self.store), head_before)

    def test_the_authorization_is_checked_before_the_paths(self):
        with self.assertRaises(Refused) as cm:
            sil.commit_generation(
                self.store,
                changes={"integrity/auth.json": b"{}"},
                authorization={
                    "id": "L-999999",
                    "sha256": "sha256:" + "0" * 64,
                    "offset": 0,
                },
            )
        self.assertEqual(cm.exception.check, "authorization")

    def test_the_declared_data_still_commits(self):
        out = sil.commit_generation(
            self.store,
            changes={
                "rules.json": canonical(
                    {"default": "hold", "domains": {}, "skills": {}}
                ),
                "skills/example/manifest.json": canonical({"name": "example"}),
            },
            authorization=self.approval(),
        )
        self.assertEqual(out["entry"], 1)
