# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Operator input preempts a chain at the cycle boundary, and the Operator keeps
or discards its results (D100, OP-002(a)(c))."""

from __future__ import annotations

import http.server
import io
import json
import os
import threading
import time
from unittest import mock

import test_ui
from helpers import TempDirTest

from fsp import context, cycle, lifecycle, mil, model, operator, sil, ui
from fsp.store import Store

TIMEOUT = test_ui.TIMEOUT
LISTING = json.dumps({"intents": [{"op": "file_list", "path": "."}]})
NOTED = json.dumps({"intents": [{"op": "reply", "text": "noted"}]})
MARKER = "marker.txt"
HOLD = 1.0


def _reply(text="done"):
    return json.dumps({"intents": [{"op": "reply", "text": text}]})


class CycleSideTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        self.W = self.p("W")
        os.makedirs(self.W)
        with open(os.path.join(self.W, MARKER), "w") as f:
            f.write("x")
        sil.first_activation(self.S, "op-1")
        operator.set_workspace(self.S, self.W)
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def respond(self, completions, **kwargs):
        self.fake = model.FakeModel(list(completions))
        return cycle.respond(
            self.S, "hello", channel=self.fake, date="2026-10-14", **kwargs
        )

    def records(self, kind):
        return [r for r in mil.session_records(self.store, "s-1") if r["kind"] == kind]

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def test_an_interrupt_stops_the_chain_after_the_first_cycle(self):
        calls = []

        def interrupt():
            calls.append(1)
            return True

        got = self.respond([LISTING, NOTED], interrupt=interrupt)
        (results,) = self.records("results")
        self.assertEqual(got["cycles"], ["s-1/c-1"])
        self.assertEqual(
            got["interrupted"], {"cycle": "s-1/c-1", "results": results["id"]}
        )
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(len(calls), 1)
        (logged,) = self.log("chain-interrupted")
        self.assertEqual(logged["rule"], "OP-002(a)")
        self.assertEqual(logged["session"], "s-1")
        self.assertEqual(logged["cycle"], "s-1/c-1")
        self.assertEqual(logged["results"], results["id"])
        self.assertEqual(self.log("chain-limit"), [])
        self.assertEqual(self.records("reply"), [])

    def test_interrupt_is_asked_only_at_the_boundaries(self):
        asked = []

        def interrupt():
            asked.append(len(self.fake.calls))
            return False

        got = self.respond([LISTING, LISTING, _reply()], interrupt=interrupt)
        self.assertEqual(got["cycles"], ["s-1/c-1", "s-1/c-2", "s-1/c-3"])
        self.assertEqual(asked, [1, 2])
        self.assertIsNone(got["interrupted"])
        self.assertEqual(self.log("chain-interrupted"), [])

    def test_interrupt_is_asked_after_each_dispatching_cycle(self):
        asked = []

        def interrupt():
            asked.append(len(self.fake.calls))
            return False

        self.respond([LISTING, LISTING, LISTING, _reply()], interrupt=interrupt)
        self.assertEqual(asked, [1, 2, 3])

    def test_interrupt_is_not_asked_before_the_first_cycle_or_after_an_abort(self):
        asked = []
        got = self.respond(["not json"], interrupt=lambda: asked.append(1))
        self.assertIsNotNone(got["aborted"])
        self.assertEqual(asked, [])
        self.assertIsNone(got["interrupted"])

    def test_interrupt_is_not_asked_after_a_reply_only_cycle(self):
        asked = []
        got = self.respond([_reply()], interrupt=lambda: asked.append(1))
        self.assertEqual(asked, [])
        self.assertIsNone(got["interrupted"])

    def test_interrupt_is_not_asked_at_the_chain_limit(self):
        sil.set_operational(self.store, "chain_limit", 2)
        asked = []
        got = self.respond(
            [LISTING, LISTING, LISTING], interrupt=lambda: asked.append(1) or False
        )
        self.assertEqual(len(got["cycles"]), 2)
        self.assertEqual(len(asked), 1)
        self.assertEqual(len(self.log("chain-limit")), 1)
        self.assertIsNone(got["interrupted"])

    def test_without_interrupt_the_chain_runs_as_before(self):
        got = self.respond([LISTING, _reply("hi")])
        self.assertEqual(got["cycles"], ["s-1/c-1", "s-1/c-2"])
        self.assertEqual(got["replies"], ["hi"])
        self.assertIsNone(got["aborted"])
        self.assertIsNone(got["interrupted"])
        self.assertEqual(len(self.records("results")), 1)
        self.assertEqual(self.log("chain-interrupted"), [])
        self.assertEqual(len(self.fake.calls), 2)

    def test_discarding_takes_the_results_out_of_the_context(self):
        self.respond([LISTING, _reply()], interrupt=lambda: True)
        (results,) = self.records("results")
        got = cycle.discard_results(self.S, "s-1/c-1", results["id"])
        (discarded,) = self.records("results-discarded")
        self.assertEqual(discarded["record"], results["id"])
        (logged,) = self.log("chain-discarded")
        self.assertEqual(logged["rule"], "OP-002(c)")
        self.assertEqual(logged["session"], "s-1")
        self.assertEqual(logged["cycle"], "s-1/c-1")
        self.assertEqual(logged["results"], results["id"])
        self.assertEqual(got, {"record": discarded["id"], "log": logged["id"]})

        records = mil.session_records(self.store, "s-1")
        for turn in context.turns(records):
            self.assertNotIn(results["id"], [r["id"] for r in turn])
        self.assertEqual(len(context.turns(records)), 1)
        with self.store.write_lock():
            assembled = context.assemble(
                self.store,
                "s-1",
                num_ctx=model.NUM_CTX_DEFAULT,
                date="2026-10-14",
                instructions=cycle.INSTRUCTIONS,
            )
        text = "\n".join(m["content"] for m in assembled["messages"])
        self.assertNotIn(MARKER, text)
        self.assertIn("hello", text)

    def test_kept_results_stay_in_the_context(self):
        self.respond([LISTING, _reply()], interrupt=lambda: True)
        with self.store.write_lock():
            assembled = context.assemble(
                self.store,
                "s-1",
                num_ctx=model.NUM_CTX_DEFAULT,
                date="2026-10-14",
                instructions=cycle.INSTRUCTIONS,
            )
        text = "\n".join(m["content"] for m in assembled["messages"])
        self.assertIn(MARKER, text)

    def test_the_discard_kind_is_a_session_kind(self):
        self.assertIn("results-discarded", mil.SESSION_KINDS)


class _Recording(test_ui._Fake):
    """The fake Ollama of test_ui, keeping the messages of every call."""

    calls = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8"))
        messages = body.get("messages", [])
        if not (len(messages) == 1 and messages[0]["content"] == "ping"):
            _Recording.calls.append(messages)
        self.rfile = io.BytesIO(raw)
        super().do_POST()


class Harness(test_ui.UiTest):
    """The harness of test_ui, against a fake that keeps the messages, without
    its tests."""

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Recording)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()


for _name in [n for n in dir(test_ui.UiTest) if n.startswith("test_")]:
    setattr(Harness, _name, None)


class PreemptionTest(Harness):
    def setUp(self):
        super().setUp()
        _Recording.calls = []
        with open(os.path.join(self.ws, MARKER), "w") as f:
            f.write("x")

    def run_typed(self, first, typed, *completions):
        """Launch the UI, type ``first``, and while the first completion is
        held type ``typed``; the completion is released ``HOLD`` seconds after
        it arrived, so the UI has read the line. Returns ``(code, out, err)``."""
        _Fake = test_ui._Fake
        _Fake.completions = list(completions)
        proc = self.launch()
        self.wait_for_holder(proc)
        self.wait_for_workspace()
        _Fake.proceed.clear()
        proc.stdin.write(first)
        proc.stdin.flush()
        self.assertTrue(_Fake.arrived.wait(TIMEOUT))
        proc.stdin.write(typed)
        proc.stdin.flush()
        time.sleep(HOLD)
        _Fake.proceed.set()
        out, err = proc.communicate(timeout=TIMEOUT)
        return proc.returncode, out, err

    def conversation(self):
        kinds = ("stimulus", "results", "reply", "results-discarded")
        return [
            (r["kind"], r.get("text", r.get("record")))
            for r in mil.session_records(self.store, "s-1")
            if r["kind"] in kinds
        ]

    def results_text(self):
        (rec,) = self.session_records("s-1", "results")
        return rec["text"]

    def joined(self, messages):
        return "\n".join(m["content"] for m in messages)

    def test_keep_resumes_the_chain_with_the_line_in_it(self):
        code, out, err = self.run_typed("hi\n", "stop\n1\n", LISTING, NOTED)
        self.assertEqual(code, 0, err)
        self.assertIn("System: the chain stopped at s-1/c-1", out)
        self.assertIn("The interrupted chain's results", out)
        self.assertEqual(len(self.log("chain-interrupted")), 1)
        self.assertEqual(self.log("chain-discarded"), [])
        self.assertEqual(self.session_records("s-1", "results-discarded"), [])
        self.assertEqual(
            [kind for kind, _ in self.conversation()],
            ["stimulus", "results", "stimulus", "reply"],
        )
        texts = [text for _, text in self.conversation()]
        self.assertEqual((texts[0], texts[2], texts[3]), ("hi", "stop", "noted"))
        self.assertEqual(len(_Recording.calls), 2)
        self.assertIn(self.results_text(), self.joined(_Recording.calls[1]))
        self.assertIn(MARKER, self.joined(_Recording.calls[1]))
        self.assertIn("noted", out)

    def test_discard_takes_the_results_out_of_the_next_call(self):
        code, out, err = self.run_typed("hi\n", "stop\n2\n", LISTING, NOTED)
        self.assertEqual(code, 0, err)
        self.assertIn("System: the chain stopped at s-1/c-1", out)
        self.assertIn("System: results discarded", out)
        (interrupted,) = self.log("chain-interrupted")
        (discarded,) = self.log("chain-discarded")
        self.assertEqual(discarded["cycle"], "s-1/c-1")
        self.assertEqual(discarded["results"], interrupted["results"])
        (marker,) = self.session_records("s-1", "results-discarded")
        self.assertEqual(marker["record"], interrupted["results"])
        self.assertEqual(len(_Recording.calls), 2)
        self.assertNotIn(MARKER, self.joined(_Recording.calls[1]))
        self.assertIn("stop", self.joined(_Recording.calls[1]))
        self.assertEqual(self.session_records("s-1", "reply")[0]["text"], "noted")

    def test_a_command_preempts_and_runs_after_the_menu(self):
        code, out, err = self.run_typed("hi\n", "/notifications\n1\n", LISTING)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.log("chain-interrupted")), 1)
        self.assertEqual(len(_Recording.calls), 1)
        self.assertEqual(
            [kind for kind, _ in self.conversation()], ["stimulus", "results"]
        )
        stopped = out.index("System: the chain stopped at s-1/c-1")
        menu = out.index("Keep them in view")
        notices = out.index("System: 0 pending notices", menu)
        self.assertTrue(stopped < menu < notices)

    def test_without_a_line_the_chain_runs_to_its_end(self):
        code, out, err = self.run_typed("hi\n", "", LISTING, NOTED)
        self.assertEqual(code, 0, err)
        self.assertNotIn("the chain stopped", out)
        self.assertNotIn("Keep them in view", out)
        self.assertEqual(self.log("chain-interrupted"), [])
        self.assertEqual(len(_Recording.calls), 2)
        self.assertIn("noted", out)
        self.assertEqual(
            [kind for kind, _ in self.conversation()], ["stimulus", "results", "reply"]
        )

    def test_the_end_of_input_at_the_menu_discards_and_suspends(self):
        code, out, err = self.run_typed("hi\n", "stop\n", LISTING, NOTED)
        self.assertEqual(code, 0, err)
        self.assertIn("Keep them in view", out)
        (interrupted,) = self.log("chain-interrupted")
        (marker,) = self.session_records("s-1", "results-discarded")
        self.assertEqual(marker["record"], interrupted["results"])
        (discarded,) = self.log("chain-discarded")
        self.assertEqual(discarded["results"], interrupted["results"])
        (close,) = self.log("session-close")
        self.assertEqual(close["mode"], "suspend")
        self.assertIsNone(close["signal"])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertEqual(len(_Recording.calls), 1)

    def test_a_reply_only_chain_is_never_asked_about(self):
        code, out, err = self.run_typed("hi\n", "", _reply("one"))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.log("chain-interrupted"), [])
        self.assertIn("one", out)

    def test_type_ahead_does_not_preempt(self):
        code, out, err = self.run_fsp("hi\nstop\n", LISTING, NOTED, NOTED)
        self.assertEqual(code, 0, err)
        self.assertNotIn("the chain stopped", out)
        self.assertEqual(self.log("chain-interrupted"), [])
        conversation = self.conversation()
        self.assertEqual(
            [kind for kind, _ in conversation],
            ["stimulus", "results", "reply", "stimulus", "reply"],
        )
        self.assertEqual((conversation[0][1], conversation[3][1]), ("hi", "stop"))


class DrainTest(TempDirTest):
    def pipe(self):
        read, write = os.pipe()
        ends = {"write": write}

        def close_write():
            if ends["write"] is not None:
                os.close(ends["write"])
                ends["write"] = None

        self.addCleanup(os.close, read)
        self.addCleanup(close_write)
        return read, write, close_write

    def test_drain_reads_what_is_held_without_waiting(self):
        read, write, close_write = self.pipe()
        reader = ui._LineReader(read)
        os.write(write, b"a\nb\n")
        started = time.monotonic()
        reader.drain()
        self.assertLess(time.monotonic() - started, 0.1)
        self.assertEqual(reader.buffer, b"a\nb\n")
        self.assertFalse(reader.eof)
        close_write()
        reader.drain()
        self.assertTrue(reader.eof)
        self.assertEqual(reader.buffer, b"a\nb\n")

    def test_input_on_a_terminal_reads_a_waiting_line_first(self):
        reader = ui._LineReader(-1)
        reader.buffer = b"queued\n"

        def refuse(prompt=""):
            raise AssertionError("input() called")

        out = io.StringIO()
        with mock.patch.object(ui, "_on_terminal", return_value=True):
            with mock.patch.object(ui, "_stdin", reader):
                with mock.patch("builtins.input", refuse):
                    with mock.patch.object(ui.sys, "stdout", out):
                        self.assertEqual(ui._input("> "), "queued")
        self.assertEqual(out.getvalue(), "> ")
        self.assertEqual(reader.buffer, b"")

    def test_watching_is_false_while_a_read_line_waits(self):
        reader = ui._LineReader(-1)
        window = ui._Ui(self.p("S"), None)
        window.responding.set()
        with mock.patch.object(ui, "_stdin", reader):
            self.assertTrue(window.watching())
            reader.buffer = b"x\n"
            self.assertFalse(window.watching())

    def test_hold_line_holds_a_line_read_after_the_chain_ended(self):
        read, write, _ = self.pipe()
        os.write(write, b"late\n")
        window = ui._Ui(self.p("S"), None)
        self.assertFalse(window.responding.is_set())
        with mock.patch.object(ui, "_stdin", ui._LineReader(read)):
            window.hold_line()
        self.assertEqual(window.pending_line, "late")


class InterruptedMenuTests(CycleSideTests):
    def test_the_discard_is_written_once_and_the_marker_cleared(self):
        out = self.respond([LISTING, NOTED], interrupt=lambda: True)
        (results,) = self.records("results")
        self.assertEqual(out["interrupted"]["results"], results["id"])
        window = ui._Ui(self.S, None)
        with mock.patch.object(window, "ask", return_value=1):
            with mock.patch.object(ui, "_say"):
                window._interrupted(out["interrupted"])
        (marker,) = self.records("results-discarded")
        self.assertEqual(marker["record"], results["id"])
        self.assertEqual(len(self.log("chain-discarded")), 1)
        self.assertIsNone(window.interrupted)


for _name in [n for n in dir(CycleSideTests) if n.startswith("test_")]:
    setattr(InterruptedMenuTests, _name, None)
