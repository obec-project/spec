# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""A conversation's pointer map: seeded from a verified Resumption Record,
extended by /inject, and kept by /resume (D85)."""

from __future__ import annotations

from helpers import TempDirTest

from fsp import lifecycle, mil, operator, sil
from fsp.sil import Refused
from fsp.store import MNEMONIC, Store


class ConversationTests(TempDirTest):
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

    def payload(self, **kw):
        return {
            "consolidation": "We planned the release.",
            "working_set": [],
            "message": "Next: tag it.",
            "promotions": [],
            **kw,
        }

    def conv(self, session):
        return mil.conversation_of(self.store, session)

    def opened(self, session):
        return mil.session_records(self.store, session)[0]

    def recalled(self, query):
        return [r["id"] for r in mil.recall(self.S, query=query)["records"]]

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def entries(self, session):
        return mil.pointer_map(self.store, self.conv(session))["entries"]

    def refusal(self, call, *args):
        with self.assertRaises(Refused) as caught:
            call(self.S, *args)
        return caught.exception.check

    def test_exit_seeds_the_next_conversation(self):
        m = self.save("alpha notes")
        operator.exit_conversation(self.S, self.payload(working_set=[m]))
        lifecycle.start(self.S)
        self.assertEqual(self.opened("s-2")["seeded_by"], self.conv("s-1"))
        self.assertEqual(
            self.entries("s-2"),
            [{"id": m, "from": self.conv("s-1"), "via": "resumption", "act": None}],
        )
        self.assertIn(m, self.recalled("alpha"))

    def test_a_changed_resumption_record_is_discarded(self):
        m = self.save("alpha notes")
        operator.exit_conversation(self.S, self.payload(working_set=[m]))
        path = mil.resumption_path(self.conv("s-1"))
        changed = self.store.read_json(path)
        changed["message"] = "Next: something else."
        self.store.replace_json(MNEMONIC, path, changed, writer=mil.WRITER)
        lifecycle.start(self.S)
        self.assertEqual(len(self.log("resumption-discarded")), 1)
        self.assertEqual(self.entries("s-2"), [])
        self.assertNotIn("seeded_by", self.opened("s-2"))
        self.assertNotIn(m, self.recalled("alpha"))

    def test_new_seeds_nothing(self):
        self.save("alpha notes")
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        self.assertEqual(self.entries("s-2"), [])
        self.assertEqual(self.log("resumption-discarded"), [])

    def test_a_restart_keeps_the_conversation_unseeded(self):
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        self.assertEqual(self.conv("s-2"), self.conv("s-1"))
        self.assertNotIn("seeded_by", self.opened("s-2"))

    def test_inject_adds_a_past_conversation_s_records(self):
        m = self.save("beta fact")
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        out = operator.inject_records(self.S, self.conv("s-1"))
        self.assertEqual(out["added"], [m])
        (entry,) = self.entries("s-2")
        self.assertEqual(entry["via"], "inject")
        self.assertEqual(entry["act"], out["log_records"][0])
        self.assertIn(m, self.recalled("beta"))

    def test_inject_takes_the_records_named(self):
        a = self.save("gamma one")
        self.save("gamma two")
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        operator.inject_records(self.S, self.conv("s-1"), [a])
        self.assertEqual(self.recalled("gamma"), [a])

    def test_inject_refusals(self):
        self.save("zeta")
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        checks = [
            self.refusal(operator.inject_records, self.conv("s-2")),
            self.refusal(operator.inject_records, "C-0000"),
            self.refusal(operator.inject_records, self.conv("s-1"), ["M-0000"]),
        ]
        self.assertEqual(
            checks, ["conversation-current", "conversation-unknown", "recall-scope"]
        )

    def test_inject_skips_what_is_in_scope(self):
        m = self.save("eta fact")
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        first = operator.inject_records(self.S, self.conv("s-1"))
        second = operator.inject_records(self.S, self.conv("s-1"))
        self.assertEqual(first["added"], [m])
        self.assertEqual(second["added"], [])

    def test_resume_brings_a_past_conversation_back(self):
        mil.stimulate(self.S, "hello first")
        a = self.save("delta one")
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        self.save("delta two")
        operator.resume_conversation(self.S, self.conv("s-1"))
        lifecycle.start(self.S)
        self.assertEqual(self.conv("s-3"), self.conv("s-1"))
        texts = [r.get("text") for r in mil.transcript(self.store, "s-3")]
        self.assertIn("hello first", texts)
        self.assertEqual(self.recalled("delta"), [a])

    def test_resume_continues_the_conversation_s_last_session(self):
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        operator.resume_conversation(self.S, self.conv("s-1"))
        lifecycle.start(self.S)
        self.assertEqual(self.opened("s-4")["continues"], "s-2")

    def test_resume_refusals(self):
        checks = [
            self.refusal(operator.resume_conversation, self.conv("s-1")),
            self.refusal(operator.resume_conversation, "C-0000"),
        ]
        self.assertEqual(checks, ["conversation-current", "conversation-unknown"])
        self.assertEqual(lifecycle.live_session(self.S), "s-1")

    def test_a_resumed_conversation_keeps_its_pointer_map(self):
        m = self.save("epsilon")
        operator.exit_conversation(self.S, self.payload(working_set=[m]))
        lifecycle.start(self.S)
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        operator.resume_conversation(self.S, self.conv("s-2"))
        lifecycle.start(self.S)
        self.assertEqual(self.conv("s-4"), self.conv("s-2"))
        self.assertIn(m, self.recalled("epsilon"))
