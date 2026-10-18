# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Episodic records of a conversation and recall v0: by words, by lineage, within
the conversation's scope (D11, D79)."""

from __future__ import annotations

from unittest import mock

from helpers import TempDirTest

from fsp import lifecycle, mil, operations, sil
from fsp.sil import Refused
from fsp.store import Store


class RecallTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def save(self, content, supersedes=None):
        return mil.save(
            self.S,
            caller="cpe",
            destination="episodic",
            content=content,
            supersedes=supersedes,
        )["record"]

    def new_conversation(self):
        session = lifecycle.live_session(self.S)
        with self.store.write_lock():
            mil.save_session(self.store, session, "conversation-left")
        lifecycle.stop(self.S)
        lifecycle.start(self.S)

    def ids(self, out):
        return [r["id"] for r in out["records"]]

    def test_an_episodic_record_names_its_conversation(self):
        rid = self.save("a")
        record = [r for r in mil._episodic(self.store) if r["id"] == rid][0]
        self.assertIsNotNone(record["conversation"])
        self.assertEqual(record["conversation"], mil.conversation_of(self.store, "s-1"))

    def test_recall_finds_by_every_word(self):
        first = self.save("the deadline is friday")
        second = self.save("lunch on friday")
        self.assertEqual(self.ids(mil.recall(self.S, query="friday deadline")), [first])
        self.assertEqual(self.ids(mil.recall(self.S, query="FRIDAY")), [first, second])

    def test_recall_returns_the_latest_of_a_lineage(self):
        a = self.save("plan v1 alpha")
        b = self.save("plan v2 alpha", supersedes=a)
        self.assertEqual(self.ids(mil.recall(self.S, query="alpha")), [b])

    def test_superseding_outside_the_scope_is_refused(self):
        a = self.save("x")
        self.new_conversation()
        with self.assertRaises(Refused) as cm:
            self.save("y", supersedes=a)
        self.assertEqual(cm.exception.check, "recall-scope")

    def test_superseding_a_superseded_record_is_refused(self):
        a = self.save("x")
        self.save("y", supersedes=a)
        with self.assertRaises(Refused) as cm:
            self.save("z", supersedes=a)
        self.assertEqual(cm.exception.check, "lineage")

    def test_recall_does_not_reach_another_conversation(self):
        self.save("secret plan")
        self.new_conversation()
        self.assertEqual(mil.recall(self.S, query="secret")["records"], [])

    def test_a_lineage_returns_its_records_in_scope(self):
        a = self.save("x")
        b = self.save("y", supersedes=a)
        out = mil.recall(self.S, lineage=a)
        self.assertEqual(self.ids(out), [a, b])
        self.assertEqual(out["outside"], [])

    def test_a_lineage_outside_the_scope_is_refused(self):
        a = self.save("x")
        self.new_conversation()
        with self.assertRaises(Refused) as cm:
            mil.recall(self.S, lineage=a)
        self.assertEqual(cm.exception.check, "recall-scope")

    def test_a_lineage_names_what_is_outside(self):
        a = self.save("x")
        b = self.save("y", supersedes=a)
        self.new_conversation()
        with mock.patch.object(mil, "_pointer_ids", return_value={b}):
            out = mil.recall(self.S, lineage=b)
        self.assertEqual(self.ids(out), [b])
        self.assertEqual(out["outside"], [a])

    def test_every_recall_is_logged(self):
        rid = self.save("k")
        mil.recall(self.S, query="k")
        logged = lifecycle.observe_log(self.S, kind="recall")["records"]
        self.assertEqual(logged[-1]["returned"], [rid])

    def test_recall_needs_a_live_session(self):
        lifecycle.stop(self.S)
        with self.assertRaises(Refused) as cm:
            mil.recall(self.S, query="x")
        self.assertEqual(cm.exception.check, "no-session")

    def test_attempt_write_via_mnemonic_recall_is_refused(self):
        with self.assertRaises(Refused) as cm:
            operations.attempt_write(
                self.S, "mnemonic", "mnemonic-recall", "episodic-memory"
            )
        self.assertEqual(cm.exception.check, "sole-writer")
