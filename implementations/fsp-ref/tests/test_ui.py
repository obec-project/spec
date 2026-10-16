# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""``fsp run``: the line REPL, launched as ``bin/fsp`` in a subprocess against
a fake Ollama (D92, D93)."""

from __future__ import annotations

import http.server
import json
import os
import signal
import subprocess
import sys
import threading
import time

from helpers import ROOT, TempDirTest

from fsp import lifecycle, mil, operator, sil
from fsp.store import Store

BIN = os.path.join(ROOT, "bin", "fsp")
TIMEOUT = 30
REPLY = '{"intents":[{"op":"reply","text":"hello there"}]}'
CLOSURE = '{"consolidation":"c","working_set":[],"message":"m","promotions":[]}'


class _Fake(http.server.BaseHTTPRequestHandler):
    completions = []
    lock = threading.Lock()
    # set when a call other than the ping arrives; the answer waits for proceed
    arrived = threading.Event()
    proceed = threading.Event()

    def log_message(self, format, *args):
        pass

    def _send(self, status, body):
        data = json.dumps(body).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(
                200, {"models": [{"name": "gemma-test", "digest": "sha256:abc"}]}
            )
        else:
            self._send(404, {})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.path != "/api/chat":
            self._send(404, {})
            return
        messages = body["messages"]
        if len(messages) == 1 and messages[0]["content"] == "ping":
            content = "pong"
        else:
            _Fake.arrived.set()
            _Fake.proceed.wait(10)
            with _Fake.lock:
                if not _Fake.completions:
                    self._send(500, {"error": "no completion scripted"})
                    return
                content = _Fake.completions.pop(0)
        self._send(
            200,
            {
                "model": body["model"],
                "message": {"role": "assistant", "content": content},
                "prompt_eval_count": 7,
            },
        )


class UiTest(TempDirTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        super().setUp()
        _Fake.completions = []
        _Fake.arrived.clear()
        _Fake.proceed.set()
        self.addCleanup(_Fake.proceed.set)
        self.S = self.p("S")
        self.ws = self.p("ws")
        os.mkdir(self.ws)
        os.mkdir(self.p(".fsp"))
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        operator.set_model(
            self.S, "gemma-test", endpoint="http://127.0.0.1:%d" % self.port
        )

    # -- helpers ---------------------------------------------------------

    def launch(self, *, cwd=None, stdin=subprocess.PIPE):
        proc = subprocess.Popen(
            [sys.executable, BIN, "run", "--store", self.S],
            cwd=cwd or self.ws,
            env=dict(os.environ, HOME=self.tmp),
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def cleanup():
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            for f in (proc.stdin, proc.stdout, proc.stderr):
                if f is not None and not f.closed:
                    f.close()

        self.addCleanup(cleanup)
        return proc

    def run_fsp(self, text, *completions, cwd=None):
        _Fake.completions = list(completions)
        proc = self.launch(cwd=cwd)
        out, err = proc.communicate(input=text, timeout=TIMEOUT)
        return proc.returncode, out, err

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def log_bytes(self):
        with open(self.store.path(sil.LOG), "rb") as f:
            return f.read()

    def session_records(self, session, kind):
        return [
            r for r in mil.session_records(self.store, session) if r["kind"] == kind
        ]

    def wait_for_holder(self, proc):
        """The credential names ``proc`` as its holder."""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                cred = self.store.read_json(lifecycle.CREDENTIAL)
                if cred.get("holder", {}).get("pid") == proc.pid:
                    return
            except (OSError, ValueError):
                pass
            if proc.poll() is not None:
                self.fail("the process ended: %r" % (proc.communicate(),))
            time.sleep(0.05)
        self.fail("the process never held the credential")

    def wait_for_workspace(self):
        """The open declared the workspace: the session is fully open."""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            acts = [r for r in self.log("operator-act") if r["act"] == "set-workspace"]
            if acts:
                return
            time.sleep(0.05)
        self.fail("the open never declared the workspace")

    # -- the tests -------------------------------------------------------

    def test_a_folder_that_contains_dot_fsp_is_refused_before_the_start(self):
        before = self.log_bytes()
        code, out, err = self.run_fsp("", cwd=self.tmp)
        self.assertEqual(code, 1, err)
        self.assertIn("D30", out)
        self.assertEqual(self.log_bytes(), before)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_empty_input_opens_and_suspends(self):
        code, out, err = self.run_fsp("")
        self.assertEqual(code, 0, err)
        kinds = [r["kind"] for r in self.log()]
        opened = kinds.index("session-open")
        acts = [
            i
            for i, r in enumerate(self.log())
            if r["kind"] == "operator-act" and r["act"] == "set-workspace"
        ]
        self.assertEqual(len(acts), 1)
        closed = kinds.index("session-close")
        self.assertTrue(opened < acts[0] < closed)
        self.assertEqual(self.log()[acts[0]]["workspace"], os.path.realpath(self.ws))
        close = self.log("session-close")[0]
        self.assertEqual(close["mode"], "suspend")
        self.assertIsNone(close["signal"])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertIn("System: session s-1, conversation ", out)
        self.assertIn("model gemma-test (num_ctx 8192)", out)
        self.assertIn("System: 0 pending notices", out)
        self.assertIn("System: suspended", out)

    def test_a_line_is_a_stimulus_and_its_reply_is_printed(self):
        code, out, err = self.run_fsp("hi\n", REPLY)
        self.assertEqual(code, 0, err)
        self.assertIn("hello there", out)
        stimuli = self.session_records("s-1", "stimulus")
        self.assertEqual([r["text"] for r in stimuli], ["hi"])

    def test_a_double_slash_is_a_stimulus_and_commands_are_not(self):
        code, out, err = self.run_fsp("//x\n/foo\n/agenda\n", '{"intents":[]}')
        self.assertEqual(code, 0, err)
        stimuli = self.session_records("s-1", "stimulus")
        self.assertEqual([r["text"] for r in stimuli], ["/x"])
        self.assertIn("unknown command /foo", out)
        self.assertIn("/agenda is not available yet", out)

    def test_a_known_command_with_wrong_arguments_prints_its_usage(self):
        acts = [r["act"] for r in self.log("operator-act")]
        code, out, err = self.run_fsp("/work\n/model\n/grant a\n/resume\n")
        self.assertEqual(code, 0, err)
        for usage in ("/work set PATH", "/model NAME", "/grant SCOPE", "/resume ID"):
            self.assertIn("System: usage: " + usage, out)
        after = [r["act"] for r in self.log("operator-act")]
        self.assertEqual(after, acts + ["set-workspace"])
        self.assertEqual(self.log("refusal"), [])

    def test_clear_records_the_cut(self):
        code, out, err = self.run_fsp("/clear\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.session_records("s-1", "transcript-cleared")), 1)
        self.assertIn("System: transcript cleared", out)

    def test_new_closes_the_session_and_opens_another_in_one_process(self):
        code, out, err = self.run_fsp("/new\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.log("session-open")), 2)
        closes = self.log("session-close")
        self.assertEqual([c["mode"] for c in closes], ["normal", "suspend"])
        self.assertEqual([c["session"] for c in closes], ["s-1", "s-2"])
        self.assertEqual(out.count("System: session s-"), 3)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_exit_closes_normally_with_a_sleep(self):
        code, out, err = self.run_fsp("hi\n/exit\n", REPLY, CLOSURE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.log("session-close")[0]["mode"], "normal")
        self.assertEqual(len(self.log("sleep-complete")), 1)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertNotIn("System: suspended", out)

    def test_a_refused_exit_leaves_the_session_live(self):
        code, out, err = self.run_fsp("hi\n/exit\n", REPLY, "not a payload")
        self.assertEqual(code, 0, err)
        self.assertIn("System: refused (", out)
        closes = self.log("session-close")
        self.assertEqual([c["mode"] for c in closes], ["suspend"])

    def test_a_signal_suspends_and_exits_with_128_plus_the_signal(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig.name):
                proc = self.launch()
                self.wait_for_holder(proc)
                proc.send_signal(sig)
                proc.wait(timeout=TIMEOUT)
                proc.communicate(timeout=TIMEOUT)
                self.assertEqual(proc.returncode, 128 + sig.value)
                close = self.log("session-close")[-1]
                self.assertEqual(close["mode"], "suspend")
                self.assertEqual(close["signal"], sig.name)
                self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_a_signal_during_a_model_call_abandons_it_and_records_the_chain(self):
        _Fake.completions = [REPLY]
        proc = self.launch()
        self.wait_for_holder(proc)
        self.wait_for_workspace()
        _Fake.proceed.clear()
        proc.stdin.write("hi\n")
        proc.stdin.flush()
        self.assertTrue(_Fake.arrived.wait(TIMEOUT))
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=TIMEOUT)
        proc.communicate(timeout=TIMEOUT)
        self.assertEqual(proc.returncode, 128 + signal.SIGTERM.value)
        close = self.log("session-close")[-1]
        self.assertEqual((close["mode"], close["signal"]), ("suspend", "SIGTERM"))
        self.assertIs(close["chain"], True)
        self.assertEqual(self.session_records("s-1", "reply"), [])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_a_second_start_is_refused_while_the_process_holds(self):
        proc = self.launch()
        self.wait_for_holder(proc)
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "refused")
        self.assertEqual(res.gates[-1]["gate"], "crash-recovery")
        self.assertEqual(res.gates[-1]["outcome"], "conflict")
        proc.communicate(timeout=TIMEOUT)
        self.assertEqual(proc.returncode, 0)

    def test_a_killed_process_is_recovered_by_the_next_start(self):
        proc = self.launch()
        self.wait_for_holder(proc)
        proc.kill()
        proc.wait(timeout=TIMEOUT)
        proc.communicate(timeout=TIMEOUT)
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        self.assertEqual(res.gates[1]["outcome"], "recovered")

    def test_a_session_revoked_from_outside_ends_the_process(self):
        proc = self.launch()
        self.wait_for_holder(proc)
        self.wait_for_workspace()
        lifecycle.revoke_credential(self.S)
        out, err = proc.communicate(input="hi\n", timeout=TIMEOUT)
        self.assertEqual(proc.returncode, 1, err)
        self.assertIn("the session ended", out)
        self.assertEqual(self.log("session-close"), [])

    def test_the_last_turns_are_replayed_at_open(self):
        code, out, err = self.run_fsp("hi\n", REPLY)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_fsp("")
        self.assertEqual(code, 0, err)
        self.assertIn("> hi", out)
        self.assertIn("hello there", out)
        self.assertLess(out.index("> hi"), out.index("System: suspended"))
        self.assertLess(out.index("hello there"), out.index("System: suspended"))
