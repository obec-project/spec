# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Compaction: ``cycle.compact``, the cut, the summary in context and
``/compact`` (D101)."""

from __future__ import annotations

import json
import os

import test_ui
from helpers import TempDirTest

from fsp import config, context, cycle, lifecycle, mil, model, operator, probes, sil
from fsp.sil import Refused
from fsp.store import Store

DATE = "2026-10-16"
FLAGGED = probes.REFERENCE_TEXTS[0]


def _reply(text="noted"):
    return json.dumps({"intents": [{"op": "reply", "text": text}]})


def _compaction(saves, summary="S1"):
    return json.dumps({"saves": saves, "summary": summary})


class CompactionTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        self.W = self.p("W")
        os.makedirs(self.W)
        sil.first_activation(self.S, "op-1")
        operator.set_workspace(self.S, self.W)
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def respond(self, text):
        fake = model.FakeModel([_reply()])
        cycle.respond(self.S, text, channel=fake, date=DATE)
        return fake

    def two_turns(self):
        self.respond("first question")
        self.respond("second question")

    def compact(self, completions, **kwargs):
        self.fake = model.FakeModel(list(completions))
        kwargs.setdefault("reason", "operator")
        return cycle.compact(self.S, channel=self.fake, date=DATE, **kwargs)

    def records(self, kind, session="s-1"):
        return [
            r for r in mil.session_records(self.store, session) if r["kind"] == kind
        ]

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def episodic(self):
        return self.store.read_jsonl(mil.EPISODIC)[0]

    def transcript(self, session="s-1"):
        return mil.transcript(self.store, session)

    def turns(self):
        return context.turns(self.transcript())

    def assert_refused_and_uncut(self, completion):
        before = self.turns()
        cycles = len(self.records("cycle"))
        aborted = len(self.log("cycle-aborted"))
        with self.assertRaises(Refused) as ctx:
            self.compact([completion])
        self.assertEqual(ctx.exception.check, "compaction")
        self.assertEqual(len(self.log("cycle-aborted")), aborted + 1)
        self.assertEqual(len(self.records("cycle")), cycles + 1)
        self.assertEqual(self.records("compaction"), [])
        self.assertEqual(self.turns(), before)

    def test_compact_after_two_turns_saves_and_cuts(self):
        self.two_turns()
        out = self.compact([_compaction([{"content": "keep this"}])])
        self.assertEqual(out["summary"], "S1")
        self.assertEqual(out["cycle"], "s-1/c-3")
        (cut,) = self.records("compaction")
        self.assertEqual(out["record"], cut["id"])
        self.assertEqual(out["saves"][0]["op"], "mnemonic-save")
        self.assertEqual(out["saves"][0]["outcome"], "done")
        inferences = [r for r in self.log("inference") if r.get("compaction")]
        self.assertEqual(len(inferences), 1)
        self.assertEqual(inferences[0]["cycle"], out["cycle"])
        last = self.records("cycle")[-1]
        self.assertEqual(last["cycle"], out["cycle"])
        self.assertTrue(last["compaction"])
        self.assertEqual(last["intents"], ["mnemonic-save"])
        self.assertEqual(last["inference"], inferences[0]["id"])
        (saved,) = self.episodic()
        self.assertEqual(saved["content"], "keep this")
        self.assertEqual(saved["cycle"], out["cycle"])
        self.assertEqual(cut["summary"], "S1")
        self.assertEqual(cut["reason"], "operator")
        self.assertIsNone(cut["keep_from"])
        self.assertEqual(cut["cycle"], out["cycle"])
        self.assertEqual(len(self.records("cycle")), 3)
        self.assertEqual([r for r in self.transcript() if r["kind"] == "stimulus"], [])
        self.assertEqual(mil.compaction_summary(self.store, "s-1"), "S1")

    def test_the_next_call_sees_the_summary_and_not_the_turns_before(self):
        self.two_turns()
        self.compact([_compaction([{"content": "keep this"}])])
        fake = self.respond("a new question")
        (messages,) = fake.calls
        self.assertIn("# Earlier in this conversation\nS1", messages[0]["content"])
        contents = [m["content"] for m in messages]
        self.assertIn("a new question", contents)
        for text in ("first question", "second question"):
            self.assertFalse(any(text in c for c in contents))

    def test_keep_from_keeps_the_turn_it_names(self):
        self.two_turns()
        second = self.records("stimulus")[1]
        reply = self.records("reply")[1]
        self.compact([_compaction([])], keep_from=second["id"])
        turns = context.turns(self.transcript())
        self.assertEqual(
            [[r["id"] for r in t] for t in turns], [[second["id"], reply["id"]]]
        )
        (cut,) = self.records("compaction")
        self.assertEqual(cut["keep_from"], second["id"])
        self.assertEqual(mil.compaction_summary(self.store, "s-1"), "S1")

    def test_a_keep_from_that_names_no_record_keeps_nothing(self):
        self.two_turns()
        self.compact([_compaction([])], keep_from="R-0000000000000000")
        self.assertEqual(context.turns(self.transcript()), [])

    def test_a_completion_that_is_not_json_is_refused_and_cuts_nothing(self):
        self.two_turns()
        self.assert_refused_and_uncut("not json")

    def test_a_completion_without_a_summary_is_refused_and_cuts_nothing(self):
        self.two_turns()
        self.assert_refused_and_uncut(json.dumps({"saves": []}))

    def test_a_blank_summary_is_refused_and_cuts_nothing(self):
        self.two_turns()
        self.assert_refused_and_uncut(_compaction([], "  "))

    def test_a_summary_the_probes_flag_is_refused_and_nothing_is_saved(self):
        self.two_turns()
        before = self.turns()
        with self.assertRaises(Refused) as ctx:
            self.compact([_compaction([{"content": "keep this"}], FLAGGED)])
        self.assertEqual(ctx.exception.check, "compaction")
        self.assertIn("probe", ctx.exception.detail)
        self.assertFalse(self.store.exists(mil.EPISODIC))
        self.assertEqual(self.records("compaction"), [])
        self.assertEqual(len(self.log("cycle-aborted")), 1)
        self.assertEqual(self.turns(), before)

    def test_a_save_the_probes_flag_is_skipped(self):
        self.two_turns()
        out = self.compact([_compaction([{"content": FLAGGED}, {"content": "fine"}])])
        self.assertEqual([o["outcome"] for o in out["saves"]], ["refused", "done"])
        checks = [r["check"] for r in self.log("refusal")]
        self.assertIn("self-representation", checks)
        (saved,) = self.episodic()
        self.assertEqual(saved["content"], "fine")
        self.assertEqual(self.records("cycle")[-1]["intents"], ["mnemonic-save"] * 2)
        self.assertEqual(len(self.records("compaction")), 1)

    def test_a_save_that_is_not_an_object_is_invalid(self):
        self.two_turns()
        out = self.compact([_compaction(["text", {"content": "fine"}])])
        self.assertEqual(
            out["saves"][0],
            {
                "op": "mnemonic-save",
                "outcome": "invalid",
                "detail": "a save is an object",
            },
        )
        self.assertEqual(out["saves"][1]["outcome"], "done")
        self.assertEqual(len(self.episodic()), 1)

    def test_nothing_to_compact_without_a_stimulus(self):
        cycles = len(self.records("cycle"))
        with self.assertRaises(Refused) as ctx:
            self.compact([_compaction([])])
        self.assertEqual(ctx.exception.check, "compaction")
        self.assertEqual(ctx.exception.rule, "OP-009(c)")
        self.assertEqual(ctx.exception.detail, "nothing to compact since the last cut")
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(len(self.records("cycle")), cycles)
        self.assertEqual(self.log("cycle-aborted"), [])
        refusal = self.log("refusal")[-1]
        self.assertEqual(refusal["check"], "compaction")
        self.assertEqual(refusal["session"], "s-1")

    def test_nothing_to_compact_right_after_a_compaction(self):
        self.two_turns()
        self.compact([_compaction([])])
        cycles = len(self.records("cycle"))
        with self.assertRaises(Refused) as ctx:
            self.compact([_compaction([])])
        self.assertEqual(ctx.exception.check, "compaction")
        self.assertEqual(ctx.exception.detail, "nothing to compact since the last cut")
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(len(self.records("cycle")), cycles)
        self.assertEqual(len(self.records("compaction")), 1)

    def test_clear_drops_the_summary(self):
        self.two_turns()
        self.compact([_compaction([])])
        operator.clear_transcript(self.S)
        self.assertIsNone(mil.compaction_summary(self.store, "s-1"))
        assembled = context.assemble(
            self.store, "s-1", num_ctx=8192, date=DATE, answering=False
        )
        self.assertNotIn(
            "Earlier in this conversation", assembled["messages"][0]["content"]
        )

    def test_the_cut_crosses_sessions(self):
        self.respond("first question")
        self.compact([_compaction([])])
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        mil.stimulate(self.S, "later")
        records = mil.transcript(self.store, "s-2")
        self.assertEqual(
            [r["text"] for r in records if r["kind"] == "stimulus"], ["later"]
        )
        self.assertTrue(all(r["session"] == "s-2" for r in records))
        self.assertEqual(mil.compaction_summary(self.store, "s-2"), "S1")

    def test_the_summary_is_always_in(self):
        self.two_turns()
        reserve = config.value(self.store, "answer_reserve")
        big = context.assemble(
            self.store, "s-1", num_ctx=100000, date=DATE, answering=False
        )
        num_ctx = big["estimate"] + reserve + 300
        context.assemble(self.store, "s-1", num_ctx=num_ctx, date=DATE, answering=False)
        summary = "x" * int(context.CHARS_PER_TOKEN * (big["estimate"] + 500))
        self.compact([_compaction([], summary)])
        with self.assertRaises(Refused) as ctx:
            context.assemble(
                self.store, "s-1", num_ctx=num_ctx, date=DATE, answering=False
            )
        self.assertEqual(ctx.exception.check, "context-budget")

    def test_compaction_is_a_session_kind(self):
        self.assertIn("compaction", mil.SESSION_KINDS)


class _Harness(test_ui.UiTest):
    """The harness of test_ui without its tests."""


for _name in [n for n in dir(test_ui.UiTest) if n.startswith("test_")]:
    setattr(_Harness, _name, None)


class UiCompactTests(_Harness):
    def test_compact_between_lines_saves_and_cuts(self):
        code, out, err = self.run_fsp(
            "hi\n/compact\n",
            _reply(),
            _compaction([{"content": "keep this"}], "S"),
        )
        self.assertEqual(code, 0, err)
        self.assertIn("System: compacted: 1 saved, 0 refused", out)
        (cut,) = self.session_records("s-1", "compaction")
        self.assertEqual(cut["reason"], "operator")
        self.assertEqual(cut["summary"], "S")
        self.assertIsNone(cut["keep_from"])

    def test_compact_with_nothing_to_compact_is_refused(self):
        code, out, err = self.run_fsp("/compact\n")
        self.assertEqual(code, 0, err)
        self.assertIn(
            "System: refused (compaction): nothing to compact since the last cut", out
        )
        self.assertEqual(self.session_records("s-1", "compaction"), [])

    def test_compact_with_an_argument_prints_its_usage(self):
        code, out, err = self.run_fsp("/compact now\n")
        self.assertEqual(code, 0, err)
        self.assertIn("System: usage: /compact", out)
        self.assertEqual(self.session_records("s-1", "compaction"), [])
