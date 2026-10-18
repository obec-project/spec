# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The cognitive cycle: one call, the joint dispatch of its intents, the chain,
and describe boundaries (D89)."""

from __future__ import annotations

import json
import os

from helpers import TempDirTest, run_adapter

from fsp import config, cycle, lifecycle, mil, model, operator, sil
from fsp.sil import Refused
from fsp.store import Store


class CycleTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        self.W = self.p("W")
        os.makedirs(self.W)
        sil.first_activation(self.S, "op-1")
        operator.set_workspace(self.S, self.W)
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def out(self, *intents):
        return json.dumps({"intents": list(intents)})

    def respond(self, text, *completions):
        self.fake = model.FakeModel(list(completions))
        return cycle.respond(self.S, text, channel=self.fake, date="2026-10-14")

    def records(self, kind):
        return [r for r in mil.session_records(self.store, "s-1") if r["kind"] == kind]

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def lines(self):
        return self.records("results")[-1]["text"].split("\n")

    def reply(self, text="done"):
        return self.out({"op": "reply", "text": text})

    def test_a_reply_ends_the_chain(self):
        got = self.respond("hello", self.reply("hi"))
        self.assertEqual(got["replies"], ["hi"])
        self.assertEqual(got["cycles"], ["s-1/c-1"])
        self.assertIsNone(got["aborted"])
        self.assertEqual([r["text"] for r in self.records("reply")], ["hi"])
        self.assertEqual(len(self.log("inference")), 1)

    def test_results_continue_the_chain(self):
        got = self.respond(
            "hello",
            self.out({"op": "mnemonic-save", "content": "note"}),
            self.reply(),
        )
        self.assertEqual(got["cycles"], ["s-1/c-1", "s-1/c-2"])
        self.assertEqual(len(self.records("results")), 1)
        self.assertTrue(self.lines()[0].startswith("[0] mnemonic-save"))
        self.assertTrue(self.fake.calls[1][-1]["content"].startswith("Results:"))

    def test_every_intent_is_attempted(self):
        self.respond(
            "hello",
            self.out(
                {"op": "file_read", "path": "../outside"},
                {"op": "mnemonic-save", "content": "kept"},
            ),
            self.reply(),
        )
        lines = self.lines()
        self.assertIn("refused", lines[0])
        self.assertIn("done", lines[1])
        self.assertEqual([r["content"] for r in mil._episodic(self.store)], ["kept"])

    def test_a_completion_that_does_not_parse_aborts(self):
        got = self.respond("hello", "not json")
        self.assertIsNotNone(got["aborted"])
        self.assertEqual(len(self.log("cycle-aborted")), 1)
        self.assertEqual(self.records("reply"), [])
        self.assertEqual(self.records("results"), [])
        cycles = self.records("cycle")
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0]["aborted"], got["aborted"])

    def test_an_unknown_operation_aborts(self):
        got = self.respond("hello", self.out({"op": "shell", "cmd": "ls"}))
        self.assertIsNotNone(got["aborted"])
        self.assertEqual(len(self.log("cycle-aborted")), 1)
        self.assertEqual(self.records("results"), [])
        self.assertEqual(self.log("execution"), [])
        self.assertEqual(self.records("cycle")[0]["intents"], [])

    def test_a_malformed_intent_fails_alone(self):
        self.respond(
            "hello",
            self.out({"op": "mnemonic-save"}, {"op": "reply", "text": "ok"}),
            self.reply(),
        )
        self.assertIn("invalid", self.lines()[0])
        self.assertEqual(self.records("reply")[0]["text"], "ok")

    def test_the_chain_limit_ends_the_chain(self):
        sil.set_operational(self.store, "chain_limit", 2)
        recall = self.out({"op": "mnemonic-recall", "query": "anything"})
        got = self.respond("hello", recall, recall, recall)
        self.assertEqual(len(got["cycles"]), 2)
        self.assertEqual(len(self.log("chain-limit")), 1)

    def test_cycles_are_numbered_in_the_session(self):
        recall = self.out({"op": "mnemonic-recall", "query": "anything"})
        first = self.respond("one", recall, self.reply())
        second = self.respond("two", self.reply())
        self.assertEqual(first["cycles"], ["s-1/c-1", "s-1/c-2"])
        self.assertEqual(second["cycles"], ["s-1/c-3"])

    def test_the_inference_is_logged(self):
        self.respond("hello", self.reply())
        (inference,) = self.log("inference")
        self.assertEqual(inference["cycle"], "s-1/c-1")
        self.assertEqual(inference["model"], "fake")
        self.assertIsInstance(inference["estimate"], int)

    def test_a_model_failure_aborts(self):
        got = self.respond("x")
        self.assertTrue(got["aborted"].startswith("model:"))
        self.assertEqual(len(self.log("cycle-aborted")), 1)

    def test_without_a_model_nothing_runs(self):
        with self.assertRaises(Refused) as ctx:
            cycle.respond(self.S, "x")
        self.assertEqual(ctx.exception.check, "model")

    def test_results_are_capped(self):
        with open(os.path.join(self.W, "big.txt"), "w") as f:
            f.write("y" * 20000)
        self.respond(
            "hello", self.out({"op": "file_read", "path": "big.txt"}), self.reply()
        )
        (line,) = self.lines()
        self.assertTrue(line.endswith("[truncated]"))
        self.assertLessEqual(len(line), cycle.RESULT_CAP + len(" [truncated]"))

    def test_a_proposal_goes_through_the_proposals(self):
        ops = [{"op": "set-persona", "content": "You are helpful."}]
        self.respond("hello", self.out({"op": "propose", "ops": ops}), self.reply())
        line = self.lines()[0]
        self.assertIn("done", line)
        self.assertIn("proposal", line)

    def test_one_call_per_cycle(self):
        recall = self.out({"op": "mnemonic-recall", "query": "anything"})
        self.respond("hello", recall, self.reply())
        self.assertEqual(len(self.fake.calls), 2)

    def test_describe_boundaries(self):
        code, out = run_adapter("describe", "boundaries")
        self.assertEqual(code, 0)
        detail = out["detail"]
        self.assertEqual(
            [b["name"] for b in detail["boundaries"]],
            [
                "cognition-integrity",
                "cognition-model",
                "cognition-knowledge",
                "cognition-host",
            ],
        )
        self.assertTrue(all(b["loggable"] is True for b in detail["boundaries"]))
        self.assertTrue(detail["evidence"])

    def test_chain_limit_is_declared(self):
        (setting,) = [s for s in config.SETTINGS if s.name == "chain_limit"]
        self.assertEqual(setting.as_dict()["default"], 8)
        self.assertEqual(setting.as_dict()["range"], [1, 64])
