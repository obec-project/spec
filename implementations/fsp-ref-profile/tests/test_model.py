# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The inference channel: the fake and the Ollama backends, the model setting
and its fingerprint, and describe inference-channel (D87)."""

from __future__ import annotations

import http.server
import json
import socket
import threading

from helpers import TempDirTest, run_adapter

from fsp import config, lifecycle, model, operator, sil
from fsp.sil import Refused
from fsp.store import Store


class _Handler(http.server.BaseHTTPRequestHandler):
    # (method, path, decoded body) of every request the server received
    requests = []
    mode = "ok"

    def log_message(self, format, *args):
        pass

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else None

    def _send(self, status, body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self._body()
        _Handler.requests.append(("POST", self.path, body))
        if self.path != "/api/chat":
            self._send(404, {})
        elif _Handler.mode == "error":
            self._send(500, {"error": "boom"})
        elif _Handler.mode == "garbage":
            self._send(200, b"not json")
        else:
            self._send(
                200,
                {
                    "model": body["model"],
                    "message": {"role": "assistant", "content": "pong"},
                    "prompt_eval_count": 7,
                },
            )

    def do_GET(self):
        _Handler.requests.append(("GET", self.path, None))
        if self.path == "/api/tags":
            self._send(
                200, {"models": [{"name": "gemma-test", "digest": "sha256:abc"}]}
            )
        else:
            self._send(404, {})


class ModelTests(TempDirTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        super().setUp()
        _Handler.requests = []
        _Handler.mode = "ok"
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        self.endpoint = "http://127.0.0.1:%d" % self.port

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def test_the_fake_returns_its_script_in_order(self):
        fake = model.FakeModel(["a", "b"])
        msgs = [{"role": "user", "content": "hi"}]
        self.assertEqual(fake.complete(msgs)["text"], "a")
        self.assertEqual(fake.complete(msgs)["text"], "b")
        with self.assertRaises(model.ModelError):
            fake.complete(msgs)
        self.assertEqual(fake.calls, [msgs, msgs, msgs])

    def test_the_ollama_call_carries_the_context_only(self):
        m = model.OllamaModel("gemma-test", self.endpoint, 4096, 5)
        msgs = [{"role": "user", "content": "hi"}]
        out = m.complete(msgs, schema={"type": "object"})
        self.assertEqual(len(_Handler.requests), 1)
        method, path, body = _Handler.requests[0]
        self.assertEqual((method, path), ("POST", "/api/chat"))
        self.assertEqual(body["model"], "gemma-test")
        self.assertEqual(body["messages"], msgs)
        self.assertIs(body["stream"], False)
        self.assertEqual(body["format"], {"type": "object"})
        self.assertEqual(body["options"], {"num_ctx": 4096})
        self.assertNotIn("tools", body)
        self.assertNotIn("context", body)
        self.assertEqual(
            out, {"text": "pong", "model": "gemma-test", "prompt_eval_count": 7}
        )

    def test_channel_failures_are_model_errors(self):
        msgs = [{"role": "user", "content": "hi"}]
        for mode in ("error", "garbage"):
            _Handler.mode = mode
            m = model.OllamaModel("gemma-test", self.endpoint, 4096, 5)
            with self.assertRaises(model.ModelError):
                m.complete(msgs)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            closed = s.getsockname()[1]
        m = model.OllamaModel("gemma-test", "http://127.0.0.1:%d" % closed, 4096, 5)
        with self.assertRaises(model.ModelError):
            m.complete(msgs)

    def test_the_digest_comes_from_the_tags(self):
        known = model.OllamaModel("gemma-test", self.endpoint, 4096, 5)
        other = model.OllamaModel("other", self.endpoint, 4096, 5)
        self.assertEqual(known.digest(), "sha256:abc")
        self.assertIsNone(other.digest())

    def test_set_model_records_the_setting_and_its_fingerprint(self):
        operator.set_model(self.S, "gemma-test", endpoint=self.endpoint, num_ctx=4096)
        want = {
            "backend": "ollama",
            "name": "gemma-test",
            "endpoint": self.endpoint,
            "num_ctx": 4096,
            "digest": "sha256:abc",
        }
        self.assertEqual(model.setting(self.store), want)
        acts = [r for r in self.log("operator-act") if r["act"] == "set-model"]
        self.assertEqual(len(acts), 1)
        fingerprints = self.log("model-fingerprint")
        self.assertEqual(len(fingerprints), 1)
        self.assertEqual(fingerprints[0]["digest"], "sha256:abc")
        self.assertEqual(fingerprints[0]["act"], acts[0]["id"])

    def test_a_model_that_does_not_answer_leaves_the_setting(self):
        _Handler.mode = "error"
        with self.assertRaises(Refused) as ctx:
            operator.set_model(
                self.S, "gemma-test", endpoint=self.endpoint, num_ctx=4096
            )
        self.assertEqual(ctx.exception.check, "model")
        self.assertIsNone(model.setting(self.store))

    def test_an_endpoint_off_the_local_host_is_refused(self):
        with self.assertRaises(Refused) as ctx:
            operator.set_model(self.S, "gemma-test", endpoint="https://ollama.com")
        self.assertEqual(ctx.exception.check, "model-endpoint")
        self.assertEqual(_Handler.requests, [])

    def test_num_ctx_has_its_range(self):
        with self.assertRaises(Refused) as ctx:
            operator.set_model(
                self.S, "gemma-test", endpoint=self.endpoint, num_ctx=1024
            )
        self.assertEqual(ctx.exception.check, "model-setting")
        self.assertEqual(_Handler.requests, [])

    def test_the_start_logs_the_fingerprint_without_calling_the_server(self):
        operator.set_model(self.S, "gemma-test", endpoint=self.endpoint, num_ctx=4096)
        _Handler.requests = []
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        started = [r for r in self.log("model-fingerprint") if "session" in r]
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0]["session"], "s-1")
        self.assertEqual(started[0]["digest"], "sha256:abc")
        self.assertEqual(_Handler.requests, [])

    def test_the_name_chosen_at_activation_is_the_default(self):
        path = self.p("M")
        sil.first_activation(path, "op-1", model="gemma-test")
        got = model.setting(Store(path))
        self.assertEqual(got["name"], "gemma-test")
        self.assertEqual(got["endpoint"], model.DEFAULT_ENDPOINT)
        self.assertEqual(got["num_ctx"], 8192)
        self.assertIsNone(got["digest"])

    def test_no_model_no_fingerprint(self):
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        self.assertEqual(self.log("model-fingerprint"), [])

    def test_describe_inference_channel(self):
        code, out = run_adapter("describe", "inference-channel")
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        detail = out["detail"]
        self.assertIs(detail["third_party"], False)
        for key in ("channel", "payload", "completion_path"):
            self.assertTrue(detail[key])
        self.assertTrue(detail["evidence"])

    def test_model_timeout_is_declared(self):
        declared = {s.name: s for s in config.SETTINGS}["model_timeout_s"]
        self.assertEqual(declared.default, 120)
        self.assertEqual(list(declared.range), [5, 900])
