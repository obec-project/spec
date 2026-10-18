# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Context assembly: what always goes in, the rest by priority within a budget,
and a truncation recorded once per change (D88)."""

from __future__ import annotations

from helpers import TempDirTest

from fsp import chain, config, context, lifecycle, mil, model, operator, sil
from fsp.sil import Refused
from fsp.store import Store

RESERVE = 256


class ContextTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def stim(self, text):
        return mil.stimulate(self.S, text)["record"]

    def _session_record(self, kind, text):
        with self.store.write_lock():
            return mil.save_session(
                self.store, lifecycle.live_session(self.S), kind, text=text, cycle="c"
            )

    def reply(self, text):
        return self._session_record("reply", text)

    def results(self, text):
        return self._session_record("results", text)

    def learn(self, slug, category, content):
        session = lifecycle.live_session(self.S)
        with self.store.write_lock():
            pid = mil.request_promotion(
                self.store, session, slug=slug, category=category, content=content
            )
        operator.approve_promotion(self.S, pid)
        with self.store.write_lock():
            return mil.promote(self.store, session, pid)

    def asm(self, num_ctx, **kw):
        return context.assemble(
            self.store,
            lifecycle.live_session(self.S),
            num_ctx=num_ctx,
            date="2026-10-14",
            **kw,
        )

    def system(self, out):
        return out["messages"][0]["content"]

    def truncations(self):
        found = mil.session_records(self.store, lifecycle.live_session(self.S))
        return [r for r in found if r["kind"] == "context-truncated"]

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    # The cost model of D88, as the tests use it to choose a num_ctx.

    def section(self, title, lines):
        """The cost of a section holding ``lines``: its header and each line."""
        header = context.tokens("# " + title) + 1
        return header + sum(context.tokens(line) + 1 for line in lines)

    def fixed(self):
        """The cost of the Persona and Session sections."""
        head = sil.read_head(self.store)["entry"]
        path = chain.gen_relpath(head) + "/persona.md"
        persona = self.store.read_bytes(path).decode("utf-8").rstrip()
        chosen = model.setting(self.store)
        session = lifecycle.live_session(self.S)
        meta = [
            "session: %s" % session,
            "conversation: %s" % mil.conversation_of(self.store, session),
            "model: %s" % (chosen["name"] if chosen else "none"),
            "date: 2026-10-14",
        ]
        return self.section("Persona", [persona]) + self.section("Session", meta)

    def num_ctx(self, tokens_in_budget):
        """The num_ctx whose budget is ``tokens_in_budget``, with the smallest
        answer reserve."""
        with self.store.write_lock():
            sil.set_operational(self.store, "answer_reserve", RESERVE)
        return RESERVE + tokens_in_budget

    def always_line(self, category, slug, content, sid):
        return "- [%s] %s: %s (%s)" % (category, slug, content, sid)

    def test_turns_group_a_stimulus_with_its_reply_and_results(self):
        records = [
            {"kind": "session-open"},
            {"kind": "stimulus", "text": "a"},
            {"kind": "reply", "text": "b"},
            {"kind": "results", "text": "c"},
            {"kind": "stimulus", "text": "d"},
        ]
        first, second = context.turns(records)
        self.assertEqual(first, records[1:4])
        self.assertEqual(second, records[4:])

    def test_a_short_history_goes_in_whole(self):
        self.stim("a")
        self.reply("b")
        self.stim("c")
        out = self.asm(8192)
        self.assertEqual(
            out["messages"][1:],
            [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"},
            ],
        )
        system = self.system(out)
        self.assertIn("# Persona", system)
        self.assertIn("# Session", system)
        self.assertIn("session: s-1", system)
        self.assertIn("date: 2026-10-14", system)
        self.assertEqual(out["dropped"]["turns"], [])

    def test_the_estimate_is_characters_over_three_and_a_half(self):
        self.assertEqual(context.tokens("abcdefg"), 2)
        self.assertEqual(context.tokens("a" * 8), 3)

    def test_when_what_always_goes_in_does_not_fit_nothing_is_called(self):
        self.stim("x" * 7000)
        with self.assertRaises(Refused) as caught:
            self.asm(1024 + 50)
        self.assertEqual(caught.exception.check, "context-budget")
        self.assertEqual(caught.exception.rule, "OC-007")
        self.assertEqual(
            [r["check"] for r in self.log("refusal")],
            ["context-budget"],
        )

    def test_old_turns_leave_first_and_whole(self):
        stims = []
        for letter in "abcdef":
            stims.append(self.stim(letter * 700))
            self.reply(letter.upper() * 700)
        turn = context.tokens("a" * 700) + context.tokens("A" * 700)
        # The first and the last turn, and room for two of the four between.
        out = self.asm(self.num_ctx(self.fixed() + 4 * turn))
        self.assertEqual(out["dropped"]["turns"], [stims[1], stims[2]])
        contents = [m["content"][:1] for m in out["messages"][1:]]
        self.assertEqual(contents, list("aAdDeEfF"))
        self.assertTrue(all(len(m["content"]) == 700 for m in out["messages"][1:]))

    def test_always_loaded_go_in_whole_in_their_order(self):
        self.learn("who", "operator", "The operator is Jonas.")
        self.learn("how", "guidance", "Be brief.")
        self.learn("never", "rule", "Never delete.")
        self.stim("hi")
        system = self.system(self.asm(8192))
        places = [system.index(s) for s in ("[rule]", "[guidance]", "[operator]")]
        self.assertEqual(places, sorted(places))
        self.assertIn("# Always loaded", system)

    def test_always_loaded_leave_operator_first_oldest_first(self):
        bulk = "x" * 700
        o1 = self.learn("o1", "operator", bulk)
        o2 = self.learn("o2", "operator", bulk)
        rule = self.learn("rule", "rule", bulk)
        self.stim("hi")
        kept = [
            self.always_line("rule", "rule", bulk, rule),
            self.always_line("operator", "o2", bulk, o2),
        ]
        budget = self.fixed() + context.tokens("hi")
        budget += self.section("Always loaded", kept)
        out = self.asm(self.num_ctx(budget))
        self.assertEqual(out["dropped"]["always_loaded"], [o1])
        system = self.system(out)
        self.assertIn(rule, system)
        self.assertIn(o2, system)
        self.assertNotIn(o1, system)

    def test_the_working_set_goes_before_the_turns(self):
        episodic = mil.save(
            self.S,
            caller="cpe",
            destination="episodic",
            content="m" * 700,
            supersedes=None,
        )["record"]
        payload = {
            "consolidation": "We planned the release.",
            "working_set": [episodic],
            "message": "Next: tag it.",
            "promotions": [],
        }
        operator.exit_conversation(self.S, payload)
        lifecycle.start(self.S)
        stims = []
        for letter in "abcde":
            stims.append(self.stim(letter * 700))
            self.reply(letter.upper() * 700)
        turn = context.tokens("a" * 700) + context.tokens("A" * 700)
        kept = ["- (%s) %s" % (episodic, "m" * 700)]
        # The first and the last turn, the working set, one turn of three.
        budget = self.fixed() + 2 * turn + self.section("Working set", kept) + turn
        out = self.asm(self.num_ctx(budget))
        self.assertIn("# Working set\n" + kept[0], self.system(out))
        self.assertEqual(out["dropped"]["turns"], stims[1:3])
        self.assertEqual(out["dropped"]["working_set"], [])

    def test_the_conversation_s_memory_goes_in_as_an_index(self):
        saved = mil.save(
            self.S,
            caller="cpe",
            destination="episodic",
            content="line one\nline two",
            supersedes=None,
        )["record"]
        self.stim("hi")
        system = self.system(self.asm(8192))
        self.assertIn("(%s) line one" % saved, system)
        self.assertNotIn("line two", system)

    def test_the_semantic_index_comes_last(self):
        knowledge = self.learn("fact", "knowledge", "Water is wet.")
        rule = self.learn("never", "rule", "Never delete.")
        self.stim("hi")
        kept = [self.always_line("rule", "never", "Never delete.", rule)]
        budget = self.fixed() + context.tokens("hi")
        budget += self.section("Always loaded", kept)
        out = self.asm(self.num_ctx(budget))
        self.assertEqual(out["dropped"]["index"], [knowledge])
        self.assertEqual(out["dropped"]["always_loaded"], [])
        self.assertNotIn("# Semantic index", self.system(out))

    def test_assembly_is_deterministic(self):
        self.learn("fact", "knowledge", "Water is wet.")
        for letter in "abc":
            self.stim(letter * 700)
            self.reply(letter.upper() * 700)
        num_ctx = self.num_ctx(self.fixed() + 900)
        self.assertEqual(self.asm(num_ctx), self.asm(num_ctx))

    def test_a_truncation_is_recorded_once_per_change(self):
        stims = []
        for letter in "abc":
            stims.append(self.stim(letter * 700))
            self.reply(letter.upper() * 700)
        turn = context.tokens("a" * 700) + context.tokens("A" * 700)
        num_ctx = self.num_ctx(self.fixed() + 2 * turn)
        out = self.asm(num_ctx)
        self.assertEqual(out["dropped"]["turns"], [stims[1]])
        with self.store.write_lock():
            first = context.record_truncation(self.store, "s-1", out)
            again = context.record_truncation(self.store, "s-1", out)
        self.assertIsNotNone(first)
        self.assertIsNone(again)
        stims.append(self.stim("d" * 700))
        self.reply("D" * 700)
        out = self.asm(num_ctx)
        self.assertEqual(out["dropped"]["turns"], stims[1:3])
        with self.store.write_lock():
            context.record_truncation(self.store, "s-1", out)
        found = self.truncations()
        self.assertEqual(len(found), 2)
        self.assertEqual(found[1]["dropped_from"], stims[1])
        self.assertEqual(found[1]["dropped_to"], stims[2])
        self.assertEqual(found[1]["budget"], out["budget"])

    def test_the_operator_is_told_when_an_always_loaded_record_leaves(self):
        bulk = "x" * 700
        o1 = self.learn("o1", "operator", bulk)
        o2 = self.learn("o2", "operator", bulk)
        self.stim("hi")
        kept = [self.always_line("operator", "o2", bulk, o2)]
        budget = self.fixed() + context.tokens("hi")
        budget += self.section("Always loaded", kept)
        out = self.asm(self.num_ctx(budget))
        self.assertEqual(out["dropped"]["always_loaded"], [o1])
        with self.store.write_lock():
            context.record_truncation(self.store, "s-1", out)
            context.record_truncation(self.store, "s-1", out)
        (notice,) = self.log("operator-notification")
        self.assertEqual(notice["condition"], "context-dropped")
        self.assertEqual(notice["detail"], [o1])
        self.assertEqual(len(self.truncations()), 1)

    def test_answer_reserve_is_declared(self):
        declared = {s.name: s.as_dict() for s in config.SETTINGS}["answer_reserve"]
        self.assertEqual(declared["default"], 1024)
        self.assertEqual(declared["range"], [256, 32768])
