# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""An attempted write runs the class guard and writes nothing (D68)."""

from __future__ import annotations

import os

from helpers import TempDirTest
from fsp import mil, proposals, sil
from fsp.sil import Refused
from fsp.store import CLASSES, GuardError, Store


def names(pairs):
    return [(d.name, rel) for d, rel in pairs]


class AttemptTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def snapshot(self):
        """Every file under the store, except the integrity log."""
        files = {}
        for dirpath, _dirs, filenames in os.walk(self.S):
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self.S).replace(os.sep, "/")
                if rel != "integrity/log.jsonl":
                    with open(full, "rb") as f:
                        files[rel] = f.read()
        return files

    def test_resolve_takes_a_name_a_path_an_absolute_path_and_a_selector(self):
        resolve = self.store.resolve
        self.assertEqual(
            names(resolve("authorization-state")), [("authorization-state", None)]
        )
        self.assertEqual(
            names(resolve("integrity/auth.json")),
            [("authorization-state", "integrity/auth.json")],
        )
        self.assertEqual(
            names(resolve(self.store.path("integrity/auth.json"))),
            [("authorization-state", "integrity/auth.json")],
        )
        self.assertEqual(
            [d.name for d, _ in resolve("class:mnemonic")],
            [
                "session-store",
                "episodic-memory",
                "semantic-memory",
                "pending-promotions",
                "resumption-record",
                "pointer-map",
            ],
        )
        self.assertEqual(
            names(resolve("memory/session/s-1.jsonl")),
            [("session-store", "memory/session/s-1.jsonl")],
        )

    def test_resolve_finds_nothing_for_what_names_no_datum(self):
        for x in (
            "integrity-datum",
            "integrity-baseline",
            os.path.join(self.S, "integrity", "log"),
            "/etc/passwd",
            "class:nowhere",
            "../x",
            "",
            None,
        ):
            self.assertEqual(self.store.resolve(x), [], x)

    def test_attempt_checks_the_writer_before_the_target(self):
        with self.assertRaises(GuardError) as cm:
            self.store.attempt("integrity", "integrity-datum", writer="mil")
        self.assertEqual(cm.exception.check, "sole-writer")

    def test_attempt_refuses_what_resolves_to_nothing_or_to_another_class(self):
        with self.assertRaises(GuardError) as cm:
            self.store.attempt("structural", "integrity-datum", writer="sil.commit")
        self.assertEqual(cm.exception.check, "target-unknown")
        with self.assertRaises(GuardError) as cm:
            self.store.attempt("structural", "authorization-state", writer="sil.commit")
        self.assertEqual(cm.exception.check, "content-class")
        with self.assertRaises(GuardError) as cm:
            self.store.attempt("nowhere", "authorization-state", writer="sil.commit")
        self.assertEqual(cm.exception.check, "content-class")

    def test_an_admitted_attempt_writes_nothing(self):
        before = self.snapshot()
        self.assertTrue(
            sil.attempt_integrity_write(self.store, "integrity", "class:integrity")
        )
        self.assertTrue(
            sil.attempt_commit(self.store, "structural", "structural/gen/0/persona.md")
        )
        self.assertTrue(mil.attempt_save(self.store, "mnemonic", "episodic-memory"))
        self.assertEqual(self.snapshot(), before)

    def test_commit_admits_only_declared_structural_data(self):
        self.assertTrue(
            sil.attempt_commit(self.store, "structural", "structural-content")
        )
        self.assertTrue(
            sil.attempt_commit(self.store, "structural", "structural/gen/0/persona.md")
        )
        with self.assertRaises(Refused) as cm:
            sil.attempt_commit(
                self.store, "structural", "structural/gen/0/integrity/auth.json"
            )
        self.assertEqual(cm.exception.check, "content-class")
        self.assertEqual(cm.exception.rule, "OC-003(c)")
        self.assertTrue(cm.exception.log_records)
        with self.assertRaises(Refused) as cm:
            sil.attempt_commit(self.store, "integrity", "authorization-state")
        self.assertEqual(cm.exception.check, "sole-writer")

    def test_integrity_write_admits_only_integrity(self):
        self.assertTrue(
            sil.attempt_integrity_write(self.store, "integrity", "authorization-state")
        )
        self.assertTrue(
            sil.attempt_integrity_write(self.store, "integrity", "class:integrity")
        )
        with self.assertRaises(Refused) as cm:
            sil.attempt_integrity_write(self.store, "mnemonic", "episodic-memory")
        self.assertEqual(cm.exception.check, "sole-writer")
        with self.assertRaises(Refused) as cm:
            sil.attempt_integrity_write(self.store, "integrity", "episodic-memory")
        self.assertEqual(cm.exception.check, "content-class")

    def test_mnemonic_save_admits_only_the_cpe_s_destination(self):
        self.assertTrue(mil.attempt_save(self.store, "mnemonic", "episodic-memory"))
        self.assertTrue(mil.attempt_save(self.store, "mnemonic", mil.EPISODIC))
        for target in ("memory/session/s-1.jsonl", "semantic-memory", "class:mnemonic"):
            with self.assertRaises(Refused) as cm:
                mil.attempt_save(self.store, "mnemonic", target)
            self.assertEqual(cm.exception.check, "mnemonic-destination", target)
        with self.assertRaises(Refused) as cm:
            mil.attempt_save(self.store, "integrity", "authorization-state")
        self.assertEqual(cm.exception.check, "sole-writer")
        with self.assertRaises(Refused) as cm:
            mil.attempt_save(self.store, "mnemonic", "authorization-state")
        self.assertEqual(cm.exception.check, "content-class")

    def test_propose_refuses_every_class_and_logs_it(self):
        for cls in CLASSES:
            with self.assertRaises(Refused) as cm:
                proposals.attempt_propose(self.store, cls, "class:" + cls)
            self.assertEqual(cm.exception.check, "sole-writer")
            self.assertTrue(cm.exception.log_records)
            (rid,) = cm.exception.log_records
            records = self.store.read_jsonl("integrity/log.jsonl")[0]
            (rec,) = [r for r in records if r["id"] == rid]
            self.assertEqual(rec["via"], "propose")
            self.assertEqual(rec["content_class"], cls)
