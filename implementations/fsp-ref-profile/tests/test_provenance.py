# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Provenance carried by the dispatch: every record an intent causes names its
cycle, and each inference its model (D90)."""

from __future__ import annotations

import http.server
import json
import os
import threading

from helpers import TempDirTest

from fsp import cycle, ledger, lifecycle, mil, model, operator, proposals, sil
from fsp.store import Store


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send(self, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        self._send(
            {
                "model": body["model"],
                "message": {"role": "assistant", "content": "pong"},
                "prompt_eval_count": 7,
            }
        )

    def do_GET(self):
        self._send({"models": [{"name": "gemma-test", "digest": "sha256:abc"}]})


class ProvenanceTests(TempDirTest):
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
        super().tearDownClass()

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

    def respond(self, text, *completions, root=None):
        self.fake = model.FakeModel(list(completions))
        return cycle.respond(root or self.S, text, channel=self.fake, date="2026-10-14")

    def reply(self, text="done"):
        return self.out({"op": "reply", "text": text})

    def log(self, kind, root=None):
        return lifecycle.observe_log(root or self.S, kind=kind)["records"]

    def test_an_execution_names_its_cycle(self):
        with open(os.path.join(self.W, "a.txt"), "w") as f:
            f.write("hello")
        self.respond("go", self.out({"op": "file_read", "path": "a.txt"}), self.reply())
        executions = self.log("execution")
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0]["cycle"], "s-1/c-1")

    def test_a_refusal_names_its_cycle(self):
        self.respond(
            "go", self.out({"op": "file_read", "path": "../outside"}), self.reply()
        )
        refusals = self.log("refusal")
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["cycle"], "s-1/c-1")

    def test_an_episodic_record_names_its_cycle(self):
        self.respond(
            "go", self.out({"op": "mnemonic-save", "content": "note"}), self.reply()
        )
        records = mil._episodic(self.store)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["cycle"], "s-1/c-1")

    def test_a_recall_names_its_cycle(self):
        self.respond(
            "go", self.out({"op": "mnemonic-recall", "query": "note"}), self.reply()
        )
        recalls = self.log("recall")
        self.assertEqual(len(recalls), 1)
        self.assertEqual(recalls[0]["cycle"], "s-1/c-1")

    def test_a_proposal_names_its_cycle(self):
        self.respond(
            "go",
            self.out(
                {"op": "propose", "ops": [{"op": "set-persona", "content": "calm"}]}
            ),
            self.reply(),
        )
        originations = self.log("proposal")
        self.assertEqual(len(originations), 1)
        self.assertEqual(originations[0]["cycle"], "s-1/c-1")
        kept = proposals.read_auth(self.store)["proposals"]
        self.assertEqual(list(kept), [originations[0]["proposal"]])
        self.assertEqual(kept[originations[0]["proposal"]]["cycle"], "s-1/c-1")

    def test_a_ledger_entry_names_its_cycle(self):
        self.respond(
            "go",
            self.out({"op": "file_write", "path": "b.txt", "content": "x"}),
            self.reply(),
        )
        entries = self.store.read_jsonl(ledger.LEDGER)[0]
        opened = [e for e in entries if e["kind"] == "open"]
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0]["cycle"], "s-1/c-1")

    def test_records_outside_a_cycle_name_none(self):
        mil.save(self.S, caller="cpe", destination="episodic", content="direct")
        operator.set_workspace(self.S, self.W)
        records = mil._episodic(self.store)
        self.assertEqual(len(records), 1)
        self.assertNotIn("cycle", records[0])
        acts = self.log("operator-act")
        self.assertTrue(acts)
        for act in acts:
            self.assertNotIn("cycle", act)

    def test_the_cycle_does_not_leak_past_a_failed_dispatch(self):
        got = self.respond("go", self.out({"op": "mnemonic-save"}), self.reply())
        self.assertEqual(got["cycles"], ["s-1/c-1", "s-1/c-2"])
        results = [
            r for r in mil.session_records(self.store, "s-1") if r["kind"] == "results"
        ]
        self.assertIn("invalid", results[0]["text"])
        mil.save(self.S, caller="cpe", destination="episodic", content="direct")
        records = mil._episodic(self.store)
        self.assertEqual([r["content"] for r in records], ["direct"])
        self.assertNotIn("cycle", records[0])
        self.assertIsNone(sil.current_cycle())

    def test_the_inference_names_the_fingerprint_at_start(self):
        path = self.p("M")
        sil.first_activation(path, "op-1", model="fake-name")
        lifecycle.start(path)
        self.respond("go", self.reply(), root=path)
        fingerprints = self.log("model-fingerprint", root=path)
        self.assertEqual(len(fingerprints), 1)
        inferences = self.log("inference", root=path)
        self.assertEqual(len(inferences), 1)
        self.assertEqual(inferences[0]["fingerprint"], fingerprints[0]["id"])

    def test_set_model_in_a_session_names_the_new_fingerprint(self):
        done = operator.set_model(
            self.S,
            "gemma-test",
            endpoint="http://127.0.0.1:%d" % self.port,
            num_ctx=4096,
        )
        fp = done["log_records"][1]
        self.respond("go", self.reply())
        inferences = self.log("inference")
        self.assertEqual(len(inferences), 1)
        self.assertEqual(inferences[0]["fingerprint"], fp)

    def test_without_a_fingerprint_the_inference_names_none(self):
        self.respond("go", self.reply())
        inferences = self.log("inference")
        self.assertEqual(len(inferences), 1)
        self.assertIn("fingerprint", inferences[0])
        self.assertIsNone(inferences[0]["fingerprint"])
