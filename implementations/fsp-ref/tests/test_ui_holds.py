# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""``fsp run``: a hold of the execution path drawn as a menu, the answer
logged and applied, the act dispatched again (D99, D66, D97)."""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading

import test_ui
from helpers import ROOT, run_adapter

from fsp import chain, operator, sil
from fsp import manifest as skill_manifest
from fsp.digest import canonical
from fsp_testing import fixture

BIN = test_ui.BIN
TIMEOUT = test_ui.TIMEOUT
REPLY = test_ui.REPLY
SECRET = b"the secret content"

# bin/fsp with the resolver and the connection of a fetch replaced, so that a
# fetch of a name reaches the test's server (the seams of tests/test_fetch.py).
LAUNCHER = """\
import os, socket, sys
sys.path.insert(0, %r)
from fsp import exec as execution
execution._resolve = lambda host, port: ["93.184.216.34"]
execution._connect = lambda address, port, host, tls, timeout: (
    socket.create_connection(("127.0.0.1", int(os.environ["FSP_TEST_PORT"])))
)
from fsp.ui import main
sys.exit(main(sys.argv[1:]))
""" % (ROOT,)


class _Page(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        body = b"hello"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Harness(test_ui.UiTest):
    """The harness of test_ui without its tests."""


for _name in [n for n in dir(test_ui.UiTest) if n.startswith("test_")]:
    setattr(Harness, _name, None)


def call(op, **fields):
    return json.dumps({"intents": [dict(op=op, **fields)]})


class UiHoldTests(Harness):
    def setUp(self):
        super().setUp()
        self.command = [sys.executable, BIN]
        self.env = {}
        outside = os.path.join(os.path.realpath(self.tmp), "outside")
        os.mkdir(outside)
        self.secret = os.path.join(outside, "secret.txt")
        with open(self.secret, "wb") as f:
            f.write(SECRET)

    def launch(self, *, cwd=None, stdin=subprocess.PIPE):
        proc = subprocess.Popen(
            self.command + ["run", "--store", self.S],
            cwd=cwd or self.ws,
            env=dict(os.environ, HOME=self.tmp, **self.env),
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

    def results(self, session="s-1"):
        return [r["text"] for r in self.session_records(session, "results")]

    def head_rules(self):
        head = sil.read_head(self.store)["entry"]
        return self.store.read_json(chain.gen_relpath(head) + "/rules.json")

    def answers(self):
        return [
            (r["answer"], r["target"])
            for r in self.log("operator-act")
            if r["act"] == "hold-answer"
        ]

    def test_a_read_outside_allowed_once_is_done(self):
        code, out, err = self.run_fsp(
            "read it\n1\n", call("file_read", path=self.secret), REPLY
        )
        self.assertEqual(code, 0, err)
        self.assertIn("System: hold L-", out)
        self.assertIn("target: " + self.secret, out)
        self.assertIn("asked by: file_read", out)
        self.assertIn("1) Allow once", out)
        self.assertNotIn("Add to the allowlist", out)
        self.assertIn(SECRET.decode(), self.results()[0])
        held = self.log("hold")
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["resolved"], self.secret)
        self.assertEqual(self.answers(), [("once", self.secret)])
        act = [r for r in self.log("operator-act") if r["act"] == "hold-answer"][0]
        self.assertEqual(act["hold"], held[0]["id"])
        self.assertEqual(act["rule"], "OC-001(c)")
        self.assertIn("hello there", out)

    def test_a_read_outside_denied_returns_the_refusal_to_the_model(self):
        code, out, err = self.run_fsp(
            "read it\n3\n", call("file_read", path=self.secret), REPLY
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn(SECRET.decode(), self.results()[0])
        self.assertIn("denied", self.results()[0])
        self.assertEqual(self.log("refusal")[-1]["reason"], "denied")
        self.assertEqual(self.answers(), [("deny", self.secret)])
        self.assertEqual(self.log("execution"), [])

    def test_a_domain_added_to_the_allowlist_is_fetched_and_committed(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Page)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.command = [sys.executable, "-c", LAUNCHER]
        self.env = {"FSP_TEST_PORT": str(server.server_address[1])}
        code, out, err = self.run_fsp(
            "fetch it\n3\n", call("http_fetch", url="https://example.com/ok"), REPLY
        )
        self.assertEqual(code, 0, err)
        self.assertIn("4) Deny", out)
        self.assertIn("3) Add to the allowlist", out)
        done = [r for r in self.log("execution") if r["op"] == "http_fetch"]
        self.assertEqual([r["outcome"] for r in done], ["done"])
        self.assertEqual(self.answers()[0][0], "allowlist")
        self.assertIn("rollover", [r["mode"] for r in self.log("session-close")])
        self.assertEqual(self.head_rules()["domains"]["example.com"]["rule"], "allow")

    def test_allowed_for_the_chat_survives_a_rollover(self):
        code, out, err = self.run_fsp(
            "read it\n2\n/allow domain example.com\nread again\n",
            call("file_read", path=self.secret),
            REPLY,
            call("file_read", path=self.secret),
            REPLY,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("rollover", [r["mode"] for r in self.log("session-close")])
        self.assertEqual(out.count("System: hold L-"), 1)
        self.assertEqual(len(self.log("hold")), 1)
        self.assertEqual(self.answers(), [("chat", self.secret)])
        self.assertIn(SECRET.decode(), self.results("s-1")[0])
        self.assertIn(SECRET.decode(), self.results("s-2")[0])

    def test_a_chat_allowance_ends_with_the_conversation(self):
        code, out, err = self.run_fsp(
            "read it\n2\n/new\nread again\n3\n",
            call("file_read", path=self.secret),
            REPLY,
            call("file_read", path=self.secret),
            REPLY,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("System: hold L-"), 2)
        self.assertEqual(
            [a for a, _ in self.answers()],
            ["chat", "deny"],
        )

    def test_a_skill_path_says_the_skill_may_read_or_write_there(self):
        files = fixture.skill_files("example")
        doc = json.loads(files["manifest.json"])
        doc.update(argv=["sh", "{skill}/run.sh", "{args.out}"])
        doc.update(args={"out": {"type": "path"}})
        files["manifest.json"] = canonical(doc).decode("utf-8")
        files["run.sh"] = 'printf "%s\\n" "$@"\n'
        sil.commit_generation(
            self.store,
            changes={
                "skills/example/%s" % k: v.encode("utf-8") for k, v in files.items()
            },
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )
        document = self.store.read_json(
            chain.document_relpath(sil.read_head(self.store)["entry"])
        )
        digest = skill_manifest.skill_digest(
            [e for e in document if e["path"].startswith("skills/example/")]
        )
        rules = {"default": "hold", "domains": {}, "skills": {}}
        rules["skills"]["example"] = {"rule": "allow", "digest": digest}
        sil.commit_generation(
            self.store,
            changes={"rules.json": canonical(rules)},
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )
        code, out, err = self.run_fsp(
            "go\n1\n",
            call("invoke-skill", skill="example", args={"out": {"path": self.secret}}),
            REPLY,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("asked by: skill example (%s)" % digest, out)
        self.assertIn("its code may read or write there", out)
        self.assertNotIn("Add to the allowlist", out)
        self.assertIn(self.secret, self.results()[0])
        self.assertEqual(self.log("hold")[0]["hold_kind"], "skill-path")

    def test_without_the_ui_a_read_outside_is_refused_as_today(self):
        operator.set_workspace(self.S, self.ws)
        code, _started = run_adapter("lifecycle", "start", "--store", self.S)
        self.assertEqual(code, 0)
        code, out = run_adapter(
            "entity",
            "actuate",
            "--store",
            self.S,
            "--op",
            "read",
            "--target",
            self.secret,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["refusal"]["check"], "workspace-boundary")
        self.assertEqual(out["refusal"]["rule"], "OC-008(a)")
        self.assertEqual(self.log("hold"), [])
        self.assertNotIn("reason", self.log("refusal")[-1])
