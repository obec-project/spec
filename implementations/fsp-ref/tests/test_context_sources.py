# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""describe context-sources, entity stimulate and observe memory
(D78, OC-003(e), OC-007)."""

from __future__ import annotations

import json

from helpers import TempDirTest, run_adapter

from fsp import lifecycle, mil, sil
from fsp.context import CONTEXT_SOURCES
from fsp.store import Store


class ContextSourcesTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def start(self):
        lifecycle.start(self.S)

    def stimulate(self, text):
        return run_adapter("entity", "stimulate", "--store", self.S, "--text", text)

    def observe(self, *extra):
        return run_adapter("observe", "memory", "--store", self.S, *extra)

    def test_describe_context_sources_reports_the_table(self):
        code, out = run_adapter("describe", "context-sources")
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        detail = out["detail"]
        self.assertEqual(detail["sources"], [dict(s) for s in CONTEXT_SOURCES])
        persona = [s for s in detail["sources"] if s["name"] == "persona"][0]
        self.assertEqual(persona["class"], "structural")
        for s in detail["sources"]:
            if s["persisted"]:
                self.assertIn(s["class"], ("structural", "mnemonic"))
            if s["class"] == "mnemonic":
                self.assertEqual(s["route"], "recall")
        self.assertTrue(detail["evidence"])

    def test_stimulate_needs_a_live_session(self):
        code, out = self.stimulate("hi")
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["refusal"]["check"], "no-session")

    def test_a_stimulus_is_a_session_record(self):
        self.start()
        code, out = self.stimulate("hello")
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(out["detail"]["session"], "s-1")
        stimuli = [
            r for r in mil.session_records(self.store, "s-1") if r["kind"] == "stimulus"
        ]
        self.assertEqual(len(stimuli), 1)
        self.assertEqual(stimuli[0]["text"], "hello")
        self.assertEqual(stimuli[0]["session"], "s-1")
        self.assertEqual(stimuli[0]["id"], out["detail"]["record"])

    def test_observe_memory_leaves_session_records_out_unless_asked(self):
        self.start()
        self.stimulate("marker-x")
        code, out = self.observe("--sample", "50")
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertNotIn("marker-x", json.dumps(out))

        code, out = self.observe("--sample", "50", "--include-session")
        self.assertIn("marker-x", json.dumps(out))
        for record in out["detail"]["records"]:
            self.assertIn("id", record)
            self.assertIn("session", record)

    def test_observe_memory_reports_episodic_records(self):
        self.start()
        mil.save(
            self.S,
            caller="cpe",
            destination="episodic",
            content="a fact worth keeping",
        )
        code, out = self.observe("--sample", "50")
        self.assertEqual(code, 0)
        found = [
            r
            for r in out["detail"]["records"]
            if r.get("content") == "a fact worth keeping"
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["session"], "s-1")

    def test_observe_memory_takes_at_most_the_sample(self):
        self.start()
        for text in ("one", "two", "three"):
            self.stimulate(text)
        code, out = self.observe("--sample", "2", "--include-session")
        self.assertEqual(code, 0)
        self.assertEqual(len(out["detail"]["records"]), 2)
