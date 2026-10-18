# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Closure Payload emitted by cognition in a call of its own (D91)."""

from __future__ import annotations

import json

from helpers import TempDirTest

from fsp import cycle, lifecycle, mil, model, operator, sil
from fsp.sil import Refused
from fsp.store import Store


class ClosureEmissionTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)
        mil.stimulate(self.S, "let us plan")

    def payload(self, **kw):
        return {
            "consolidation": "We planned the release.",
            "working_set": [],
            "message": "Next: tag it.",
            "promotions": [],
            **kw,
        }

    def exit(self, *completions):
        self.fake = model.FakeModel(list(completions))
        return operator.exit_with_closure(self.S, channel=self.fake, date="2026-10-14")

    def records(self, kind):
        return [r for r in mil.session_records(self.store, "s-1") if r["kind"] == kind]

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def save(self, content):
        return mil.save(self.S, caller="cpe", destination="episodic", content=content)[
            "record"
        ]

    def test_exit_with_an_emitted_payload_ends_the_conversation(self):
        m = self.save("release notes")
        emitted = self.payload(working_set=[m])
        out = self.exit(json.dumps(emitted))
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        (record,) = self.records("closure-payload")
        self.assertEqual(record["payload"], emitted)
        self.assertEqual(
            len([r for r in mil._episodic(self.store) if r.get("closure")]), 1
        )
        self.assertEqual(out["cycle"], "s-1/c-1")

    def test_the_emission_is_logged_as_an_inference(self):
        self.exit(json.dumps(self.payload()))
        (inference,) = self.log("inference")
        self.assertIs(inference["closure"], True)
        self.assertEqual(inference["cycle"], "s-1/c-1")
        (recorded,) = self.records("cycle")
        self.assertIs(recorded["closure"], True)
        self.assertEqual(recorded["cycle"], "s-1/c-1")

    def test_the_call_carries_the_closure_instructions(self):
        self.exit(json.dumps(self.payload()))
        (messages,) = self.fake.calls
        system = messages[0]["content"]
        self.assertIn("# Instructions\n" + cycle.CLOSURE_INSTRUCTIONS, system)

    def test_a_completion_that_is_not_a_payload_refuses_the_exit(self):
        for completion in ("not json", json.dumps({"consolidation": "x"})):
            with self.assertRaises(Refused) as caught:
                self.exit(completion)
            self.assertEqual(caught.exception.check, "closure-emission")
        self.assertEqual(len(self.log("cycle-aborted")), 2)
        self.assertEqual(lifecycle.live_session(self.S), "s-1")

    def test_a_payload_the_checks_refuse_leaves_the_session_live(self):
        with self.assertRaises(Refused) as caught:
            self.exit(json.dumps(self.payload(working_set=["M-0000"])))
        self.assertEqual(caught.exception.check, "recall-scope")
        self.assertEqual(lifecycle.live_session(self.S), "s-1")
        self.assertEqual(self.records("closure-payload"), [])

    def test_a_model_failure_refuses_the_exit(self):
        with self.assertRaises(Refused) as caught:
            self.exit()
        self.assertEqual(caught.exception.check, "closure-emission")
        self.assertTrue(caught.exception.detail.startswith("model:"))
        self.assertEqual(lifecycle.live_session(self.S), "s-1")

    def test_without_a_model_nothing_runs(self):
        with self.assertRaises(Refused) as caught:
            operator.exit_with_closure(self.S)
        self.assertEqual(caught.exception.check, "model")
