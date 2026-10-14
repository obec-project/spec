# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The session store: each session's records, the conversation they chain into,
and its transcript (D10, D24, D78)."""

from __future__ import annotations

import os

from helpers import TempDirTest

from fsp import lifecycle, mil, operator, sil
from fsp.sil import Refused
from fsp.store import Store


class SessionStoreTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def stimulus(self, session, text):
        with self.store.write_lock():
            return mil.save_session(self.store, session, "stimulus", text=text)

    def records(self, session):
        return mil.session_records(self.store, session)

    def texts(self, records):
        return [r["text"] for r in records if r["kind"] == "stimulus"]

    def test_the_first_start_opens_a_conversation(self):
        lifecycle.start(self.S)
        first = self.records("s-1")[0]
        self.assertEqual(first["kind"], "session-open")
        self.assertTrue(first["id"].startswith("R-"))
        self.assertEqual(first["session"], "s-1")
        self.assertTrue(first["conversation"].startswith("C-"))
        self.assertIsNone(first["continues"])

    def test_a_later_start_continues_the_conversation(self):
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        first = self.records("s-1")[0]
        second = self.records("s-2")[0]
        self.assertEqual(second["conversation"], first["conversation"])
        self.assertEqual(second["continues"], "s-1")

    def test_a_left_conversation_is_not_continued(self):
        lifecycle.start(self.S)
        with self.store.write_lock():
            mil.save_session(self.store, "s-1", "conversation-left")
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        first = self.records("s-1")[0]
        second = self.records("s-2")[0]
        self.assertNotEqual(second["conversation"], first["conversation"])
        self.assertIsNone(second["continues"])

    def test_a_session_without_its_open_record_is_skipped(self):
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        os.remove(self.p("S", mil.session_path("s-2")))
        lifecycle.start(self.S)
        first = self.records("s-1")[0]
        third = self.records("s-3")[0]
        self.assertEqual(third["conversation"], first["conversation"])
        self.assertEqual(third["continues"], "s-1")

    def test_the_transcript_crosses_sessions(self):
        lifecycle.start(self.S)
        self.stimulus("s-1", "a")
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        self.stimulus("s-2", "b")
        records = mil.transcript(self.store, "s-2")
        self.assertEqual(self.texts(records), ["a", "b"])

    def test_clear_cuts_the_transcript(self):
        lifecycle.start(self.S)
        self.stimulus("s-1", "a")
        operator.clear_transcript(self.S)
        self.stimulus("s-1", "b")
        records = mil.transcript(self.store, "s-1")
        self.assertEqual(self.texts(records), ["b"])
        acts = lifecycle.observe_log(self.S, kind="operator-act")["records"]
        self.assertEqual(acts[-1]["act"], "clear-transcript")

    def test_clear_needs_a_live_session(self):
        with self.assertRaises(Refused) as ctx:
            operator.clear_transcript(self.S)
        self.assertEqual(ctx.exception.check, "no-session")

    def test_an_unknown_kind_is_refused(self):
        lifecycle.start(self.S)
        with self.store.write_lock():
            with self.assertRaises(ValueError):
                mil.save_session(self.store, "s-1", "turn")

    def test_a_damaged_line_is_skipped(self):
        lifecycle.start(self.S)
        self.stimulus("s-1", "a")
        with open(self.p("S", mil.session_path("s-1")), "ab") as f:
            f.write(b"junk\n")
        self.stimulus("s-1", "b")
        self.assertEqual(self.texts(self.records("s-1")), ["a", "b"])
