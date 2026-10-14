# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Leaving a conversation: the Closure Payload checked before anything is
written, the Sleep's consolidation written once, /new, and the garbage
collection that keeps everything (D84)."""

from __future__ import annotations

from unittest import mock

from helpers import TempDirTest

from fsp import config, lifecycle, mil, operator, probes, sil
from fsp.digest import sha256
from fsp.sil import Refused
from fsp.store import Store


class ClosureTests(TempDirTest):
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

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def sessions(self):
        return self.store.read_json(lifecycle.SESSIONS)

    def records(self, session="s-1", kind=None):
        found = mil.session_records(self.store, session)
        return [r for r in found if kind is None or r["kind"] == kind]

    def refused(self, payload, check):
        with self.assertRaises(Refused) as caught:
            operator.exit_conversation(self.S, payload)
        self.assertEqual(caught.exception.check, check)
        self.assertTrue(self.store.exists(lifecycle.CREDENTIAL))
        self.assertEqual(lifecycle.live_session(self.S), "s-1")
        self.assertEqual(self.records(kind="closure-payload"), [])

    def test_exit_consolidates_and_ends_the_conversation(self):
        m = self.save("release notes")
        out = operator.exit_conversation(self.S, self.payload(working_set=[m]))
        lifecycle.start(self.S)
        conversation = mil.conversation_of(self.store, "s-1")
        (episodic,) = [r for r in mil._episodic(self.store) if r.get("closure")]
        self.assertEqual(episodic["closure"], out["closure"])
        self.assertEqual(episodic["content"], "We planned the release.")
        self.assertEqual(episodic["conversation"], conversation)
        resumption = self.store.read_json(mil.resumption_path(conversation))
        self.assertEqual(resumption["working_set"], [m])
        self.assertEqual(resumption["message"], "Next: tag it.")
        self.assertEqual(resumption["consolidation"], episodic["id"])
        self.assertEqual(self.records()[-1]["kind"], "conversation-left")
        self.assertNotEqual(mil.conversation_of(self.store, "s-2"), conversation)

    def test_sleep_complete_names_the_resumption_digest(self):
        out = operator.exit_conversation(self.S, self.payload())
        conversation = mil.conversation_of(self.store, "s-1")
        data = self.store.read_bytes(mil.resumption_path(conversation))
        (complete,) = self.log("sleep-complete")
        self.assertEqual(complete["closure"], out["closure"])
        self.assertEqual(complete["resumption"]["sha256"], sha256(data))

    def test_the_payload_s_promotions_become_pending_requests(self):
        promotion = {"slug": "tags", "category": "guidance", "content": "Tag releases."}
        out = operator.exit_conversation(self.S, self.payload(promotions=[promotion]))
        (request,) = mil.pending_promotions(self.store)
        self.assertEqual(request["closure"], out["closure"])
        self.assertEqual(request["index"], 0)

    def test_a_refused_promotion_is_skipped(self):
        promotion = {"slug": "x", "category": "self", "content": "y"}
        operator.exit_conversation(self.S, self.payload(promotions=[promotion]))
        self.assertEqual(mil.pending_promotions(self.store), [])
        checks = [r["check"] for r in self.log("refusal")]
        self.assertIn("category", checks)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_a_malformed_payload_is_refused_and_nothing_closes(self):
        self.refused({"consolidation": "x"}, "closure-payload")

    def test_the_working_set_names_the_latest_in_scope(self):
        a = self.save("v1")
        self.save("v2", supersedes=a)
        self.refused(self.payload(working_set=[a]), "recall-scope")

    def test_the_working_set_has_a_limit(self):
        sil.set_operational(self.store, "pointer_map_limit", 1)
        a = self.save("first")
        b = self.save("second")
        self.refused(self.payload(working_set=[a, b]), "pointer-map-limit")

    def test_the_probes_run_on_the_consolidation(self):
        with mock.patch.object(probes, "scan", return_value=[{"id": "p-test"}]):
            self.refused(self.payload(), "self-representation")

    def test_a_crash_in_the_sleep_consolidates_once(self):
        promotion = {"slug": "tags", "category": "guidance", "content": "Tag releases."}
        m = self.save("release notes")
        payload = self.payload(working_set=[m], promotions=[promotion])
        with mock.patch.object(mil, "promote", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                operator.exit_conversation(self.S, payload)
        lifecycle.start(self.S)
        conversation = mil.conversation_of(self.store, "s-1")
        (closure,) = self.records(kind="closure-payload")
        consolidations = [
            r for r in mil._episodic(self.store) if r.get("closure") == closure["id"]
        ]
        self.assertEqual(len(consolidations), 1)
        requests = [
            r
            for r in mil.pending_promotions(self.store)
            if r.get("closure") == closure["id"]
        ]
        self.assertEqual(len(requests), 1)
        self.assertTrue(self.store.exists(mil.resumption_path(conversation)))
        self.assertEqual(len(self.records(kind="conversation-left")), 1)
        self.assertNotEqual(mil.conversation_of(self.store, "s-2"), conversation)

    def test_new_leaves_without_a_payload(self):
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        (left,) = self.records(kind="conversation-left")
        self.assertIn("act", left)
        self.assertEqual(self.store.listdir("memory/resumption"), [])
        self.assertEqual(len(self.log("gc")), 1)
        self.assertNotEqual(
            mil.conversation_of(self.store, "s-2"),
            mil.conversation_of(self.store, "s-1"),
        )

    def test_gc_keeps_everything(self):
        m = self.save("kept")
        operator.exit_conversation(self.S, self.payload())
        (gc,) = self.log("gc")
        self.assertEqual(gc["retention"], "keep-all")
        self.assertEqual(gc["expired"], [])
        self.assertIn(m, [r["id"] for r in mil._episodic(self.store)])

    def test_a_plain_stop_neither_consolidates_nor_collects(self):
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        self.assertEqual(self.log("gc"), [])
        (complete,) = self.log("sleep-complete")
        self.assertIsNone(complete["closure"])
        self.assertIsNone(complete["resumption"])
        self.assertEqual(
            mil.conversation_of(self.store, "s-2"),
            mil.conversation_of(self.store, "s-1"),
        )

    def test_pointer_map_limit_is_declared(self):
        (setting,) = [s for s in config.SETTINGS if s.name == "pointer_map_limit"]
        self.assertEqual(setting.as_dict()["default"], 20)
        self.assertEqual(setting.as_dict()["range"], [0, 200])
