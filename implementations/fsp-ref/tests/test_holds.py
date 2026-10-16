# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""A hold in a main session: the act stops, the registered asker answers, an
allowed act is dispatched again from its first check (D99, D74, D66)."""

from __future__ import annotations

import http.server
import json
import os
import socket
import threading
from unittest import mock

from helpers import TempDirTest

from fsp import channel, chain, cycle, lifecycle, operator, sil
from fsp import exec as execution
from fsp import manifest as skill_manifest
from fsp.digest import canonical
from fsp.sil import Refused
from fsp.store import Store
from fsp_testing import fixture

ECHO = 'printf "%s\\n" "$@"\n'


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        body = b"hello"
        if self.path == "/redirect-out":
            self.send_response(302)
            self.send_header("Location", "https://other.example/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class HoldTests(TempDirTest):
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
        self.home = self.p("home")
        self.outside = os.path.realpath(self.p("outside"))
        for d in (self.W, self.home, self.outside):
            os.makedirs(d)
        env = mock.patch.dict(os.environ, {"HOME": self.home})
        env.start()
        self.addCleanup(env.stop)
        self.secret = os.path.join(self.outside, "secret.txt")
        with open(self.secret, "wb") as f:
            f.write(b"secret")
        sil.first_activation(self.S, "op-1")
        operator.set_workspace(self.S, self.W)
        self.store = Store(self.S)
        self.holds = []
        self.script = []
        self.addCleanup(channel.clear)
        self.addCleanup(channel.unregister)
        channel.register(self.asker)

    def asker(self, hold):
        """The Operator's stand-in: records the hold, answers from the
        script and leaves the extension the UI leaves."""
        self.holds.append(hold)
        answer = self.script.pop(0)
        if answer == "chat":
            channel.allow_chat(hold["key"])
        elif answer in ("once", "allowlist"):
            channel.allow_once(hold["key"])
        return answer

    def start(self):
        lifecycle.start(self.S)

    def dispatch(self, op, **fields):
        return cycle.dispatch(self.S, "s-1/c-1", dict(op=op, **fields))

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def commit(self, changes):
        sil.commit_generation(
            self.store,
            changes=changes,
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )

    def rules(self, domains=None, skills=None):
        document = {
            "default": "hold",
            "domains": domains or {},
            "skills": skills or {},
        }
        self.commit({"rules.json": canonical(document)})

    # -- paths -----------------------------------------------------------

    def test_a_read_outside_allowed_once_is_done_and_asks_again(self):
        self.start()
        self.script = ["once", "deny"]
        out = self.dispatch("file_read", path=self.secret)
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["data"], b"secret")
        self.assertEqual(out["target"], self.secret)
        held = self.log("hold")
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["hold_kind"], "path")
        self.assertEqual(held[0]["resolved"], self.secret)
        self.assertEqual(held[0]["op"], "file_read")
        self.assertEqual(held[0]["asker"], "file_read")
        self.assertEqual(held[0]["check"], "workspace-boundary")
        self.assertEqual(self.holds[0]["id"], held[0]["id"])
        self.assertEqual(self.holds[0]["key"], ("path", self.secret))
        self.assertEqual(self.log("execution")[-1]["target"], self.secret)
        again = self.dispatch("file_read", path=self.secret)
        self.assertEqual(again["outcome"], "refused")
        self.assertEqual(len(self.holds), 2)

    def test_a_list_outside_is_held_as_file_list(self):
        self.start()
        self.script = ["once"]
        out = self.dispatch("file_list", path=self.outside)
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["entries"], ["secret.txt"])
        self.assertEqual(self.holds[0]["asker"], "file_list")
        self.assertEqual(self.holds[0]["kind"], "path")

    def test_allowed_for_the_chat_does_not_ask_again(self):
        self.start()
        self.script = ["chat"]
        for _ in range(2):
            out = self.dispatch("file_read", path=self.secret)
            self.assertEqual(out["outcome"], "done")
        self.assertEqual(len(self.holds), 1)

    def test_an_extension_matches_only_its_exact_target(self):
        other = os.path.join(self.outside, "other.txt")
        with open(other, "wb") as f:
            f.write(b"other")
        self.start()
        self.script = ["chat", "deny"]
        self.dispatch("file_read", path=self.secret)
        out = self.dispatch("file_read", path=other)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(self.holds[1]["resolved"], other)

    def test_deny_refuses_and_nothing_is_read(self):
        self.start()
        self.script = ["deny"]
        out = self.dispatch("file_read", path=self.secret)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["check"], "workspace-boundary")
        self.assertEqual(out["rule"], "OC-008(a)")
        self.assertEqual(out["detail"], "the Operator denied it")
        record = self.log("refusal")[-1]
        self.assertEqual(record["reason"], "denied")
        self.assertEqual(record["hold"], self.holds[0]["id"])
        self.assertEqual(record["op"], "file_read")
        self.assertEqual(record["cycle"], "s-1/c-1")
        self.assertEqual(self.log("execution"), [])

    def test_without_an_asker_a_read_outside_is_refused_as_today(self):
        channel.unregister()
        self.start()
        out = self.dispatch("file_read", path=self.secret)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["check"], "workspace-boundary")
        self.assertEqual(out["rule"], "OC-008(a)")
        self.assertEqual(
            out["detail"], "%r resolves outside the workspace" % self.secret
        )
        self.assertEqual(self.log("hold"), [])
        self.assertNotIn("reason", self.log("refusal")[-1])
        self.assertEqual(self.holds, [])

    def test_outside_a_dispatch_nothing_is_asked(self):
        self.start()
        with self.assertRaises(Refused) as ctx:
            execution.file_read(self.S, self.secret)
        self.assertEqual(ctx.exception.check, "workspace-boundary")
        self.assertEqual(self.log("hold"), [])
        self.assertEqual(self.holds, [])

    def test_a_target_inside_the_fsp_home_is_never_asked(self):
        home_fsp = os.path.join(self.home, ".fsp")
        os.makedirs(home_fsp)
        inside = os.path.join(home_fsp, "x.txt")
        with open(inside, "wb") as f:
            f.write(b"x")
        self.start()
        for op, path in (("file_read", inside), ("file_list", home_fsp)):
            with self.subTest(op=op):
                out = self.dispatch(op, path=path)
                self.assertEqual(out["outcome"], "refused")
                self.assertEqual(out["check"], "workspace-boundary")
        self.assertEqual(self.holds, [])
        self.assertEqual(self.log("hold"), [])

    def test_a_target_inside_the_store_is_never_asked(self):
        self.start()
        out = self.dispatch("file_read", path=os.path.join(self.S, "anything"))
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["rule"], "OC-008(b)")
        self.assertEqual(self.holds, [])

    def test_a_write_outside_is_refused_and_never_asked(self):
        self.start()
        target = os.path.join(self.outside, "new.txt")
        out = self.dispatch("file_write", path=target, content="x")
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["check"], "workspace-boundary")
        self.assertEqual(self.holds, [])
        self.assertEqual(self.log("hold"), [])
        self.assertFalse(os.path.exists(target))

    # -- domains ---------------------------------------------------------

    def fetching(self):
        self.start()
        resolve = mock.Mock(return_value=["93.184.216.34"])

        def connect(address, port, host, tls, timeout):
            return socket.create_connection(("127.0.0.1", self.port), timeout=timeout)

        for name, fake in (("_resolve", resolve), ("_connect", connect)):
            patcher = mock.patch.object(execution, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        return resolve

    def test_a_domain_outside_the_allowlist_is_fetched_when_allowed_once(self):
        self.fetching()
        self.script = ["once"]
        out = self.dispatch("http_fetch", url="https://example.com/ok")
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["data"], b"hello")
        held = self.log("hold")[0]
        self.assertEqual(held["hold_kind"], "domain")
        self.assertEqual(held["asker"], "http_fetch")
        self.assertEqual(held["resolved"], "https://example.com/ok")
        self.assertEqual(self.holds[0]["key"], ("domain", "example.com"))

    def test_a_redirect_to_a_domain_outside_ends_the_fetch_and_asks(self):
        self.rules(domains={"example.com": {"rule": "allow"}})
        self.fetching()
        self.script = ["once"]
        out = self.dispatch("http_fetch", url="https://example.com/redirect-out")
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["url"], "https://other.example/ok")
        self.assertEqual(len(self.holds), 1)
        self.assertEqual(self.holds[0]["key"], ("domain", "other.example"))
        self.assertEqual(self.holds[0]["resolved"], "https://other.example/ok")
        self.assertEqual(len(self.log("execution")), 1)

    def test_a_domain_outside_the_allowlist_is_refused_when_denied(self):
        resolve = self.fetching()
        self.script = ["deny"]
        out = self.dispatch("http_fetch", url="https://example.com/ok")
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["check"], "workspace-boundary")
        self.assertEqual(self.log("refusal")[-1]["reason"], "denied")
        resolve.assert_not_called()

    def test_without_an_asker_a_domain_is_refused_as_today(self):
        channel.unregister()
        resolve = self.fetching()
        out = self.dispatch("http_fetch", url="https://example.com/ok")
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["rule"], "OC-008(a)")
        self.assertEqual(
            out["detail"], "'example.com' is outside the declared territory"
        )
        self.assertEqual(self.log("refusal")[-1]["reason"], "hold")
        self.assertEqual(self.log("hold"), [])
        resolve.assert_not_called()

    def test_a_denied_domain_is_refused_and_never_asked(self):
        self.rules(domains={"example.com": {"rule": "deny"}})
        resolve = self.fetching()
        out = self.dispatch("http_fetch", url="https://example.com/ok")
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(self.holds, [])
        self.assertEqual(self.log("hold"), [])
        resolve.assert_not_called()

    # -- skills ----------------------------------------------------------

    def install(self, name="example", run=None, **manifest):
        files = fixture.skill_files(name)
        if manifest:
            doc = json.loads(files["manifest.json"])
            doc.update(manifest)
            files["manifest.json"] = canonical(doc).decode("utf-8")
        if run is not None:
            files["run.sh"] = run
        self.commit(
            {"skills/%s/%s" % (name, k): v.encode("utf-8") for k, v in files.items()}
        )

    def digest(self, name="example"):
        document = self.store.read_json(
            chain.document_relpath(sil.read_head(self.store)["entry"])
        )
        files = [e for e in document if e["path"].startswith("skills/%s/" % name)]
        return skill_manifest.skill_digest(files)

    def test_a_skill_the_rules_do_not_allow_runs_when_allowed_once(self):
        self.install()
        self.start()
        self.script = ["once", "deny"]
        out = self.dispatch("invoke-skill", skill="example")
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["exit"], 0)
        held = self.log("hold")[0]
        digest = self.digest()
        self.assertEqual(held["hold_kind"], "skill")
        self.assertEqual(held["check"], "operator-rule")
        self.assertEqual(held["rule"], "OC-008(c)")
        self.assertEqual(held["asker"], "skill example (%s)" % digest)
        self.assertEqual(self.holds[0]["key"], ("skill", "example", digest))
        again = self.dispatch("invoke-skill", skill="example")
        self.assertEqual(again["outcome"], "refused")
        self.assertEqual(again["check"], "operator-rule")
        self.assertEqual(len(self.holds), 2)

    def test_a_skill_allowed_for_the_chat_asks_again_when_its_digest_changes(self):
        self.install()
        self.start()
        self.script = ["chat", "chat"]
        for _ in range(2):
            out = self.dispatch("invoke-skill", skill="example")
            self.assertEqual(out["outcome"], "done")
        self.assertEqual(len(self.holds), 1)
        lifecycle.stop(self.S)
        self.install(run="exit 0\n# changed\n")
        self.start()
        out = self.dispatch("invoke-skill", skill="example")
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(len(self.holds), 2)
        self.assertNotEqual(self.holds[0]["key"], self.holds[1]["key"])
        self.assertEqual(self.holds[1]["key"][2], self.digest())

    def test_a_denied_skill_is_never_asked(self):
        self.install()
        self.rules(skills={"example": {"rule": "deny", "digest": self.digest()}})
        self.start()
        out = self.dispatch("invoke-skill", skill="example")
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(self.holds, [])

    def test_without_an_asker_a_skill_is_refused_as_today(self):
        channel.unregister()
        self.install()
        self.start()
        out = self.dispatch("invoke-skill", skill="example")
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["check"], "operator-rule")
        digest = self.digest()
        self.assertEqual(
            out["detail"],
            "'example' at %s is held: the Operator's rules do not allow it, "
            "and no one can answer" % digest,
        )
        refusal = self.log("refusal")[-1]
        self.assertEqual(refusal["reason"], "hold")
        self.assertEqual(refusal["digest"], digest)
        self.assertEqual(self.log("hold"), [])

    def test_a_marked_path_outside_is_held_with_the_skill_and_its_digest(self):
        self.install(
            run=ECHO,
            argv=["sh", "{skill}/run.sh", "{args.out}"],
            args={"out": {"type": "path"}},
        )
        digest = self.digest()
        self.rules(skills={"example": {"rule": "allow", "digest": digest}})
        self.start()
        self.script = ["once"]
        out = self.dispatch(
            "invoke-skill", skill="example", args={"out": {"path": self.secret}}
        )
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["stdout"].decode().splitlines(), [self.secret])
        held = self.log("hold")[0]
        self.assertEqual(held["hold_kind"], "skill-path")
        self.assertEqual(held["asker"], "skill example (%s)" % digest)
        self.assertEqual(held["resolved"], self.secret)
        self.assertEqual(
            self.holds[0]["key"], ("skill-path", "example", digest, self.secret)
        )

    def test_a_skill_held_with_a_marked_path_runs_on_one_allow_once_each(self):
        self.install(
            run=ECHO,
            argv=["sh", "{skill}/run.sh", "{args.out}"],
            args={"out": {"type": "path"}},
        )
        self.start()
        self.script = ["once", "once"]
        out = self.dispatch(
            "invoke-skill", skill="example", args={"out": {"path": self.secret}}
        )
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["stdout"].decode().splitlines(), [self.secret])
        self.assertEqual(len(self.holds), 2)

    def test_a_marked_path_outside_of_a_skill_not_installed_is_refused_as_today(self):
        self.start()
        out = self.dispatch(
            "invoke-skill", skill="absent", args={"out": {"path": self.secret}}
        )
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["check"], "workspace-boundary")
        self.assertEqual(self.holds, [])

    def test_a_target_of_the_invocation_outside_is_never_asked(self):
        self.install()
        self.rules(skills={"example": {"rule": "allow", "digest": self.digest()}})
        self.start()
        out = self.dispatch("invoke-skill", skill="example", target=self.secret)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["check"], "workspace-boundary")
        self.assertEqual(self.holds, [])

    # -- the dispatch ----------------------------------------------------

    def test_the_hold_limit_refuses_the_ninth_hold(self):
        held = {
            "id": "L-000000",
            "op": "file_read",
            "target": "t",
            "resolved": "/t",
            "asker": "file_read",
            "kind": "path",
            "check": "workspace-boundary",
            "rule": "OC-008(a)",
            "key": ("path", "/t"),
        }

        def owner(root, cycle_id, intent):
            raise channel.Held(dict(held))

        self.start()
        self.script = ["once"] * 8
        with mock.patch.object(cycle, "_dispatch_to_owner", owner):
            out = self.dispatch("file_read", path="/t")
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["check"], "hold-limit")
        self.assertEqual(out["rule"], "OC-001(c)")
        self.assertEqual(len(self.holds), 8)
        self.assertEqual(self.log("refusal")[-1]["check"], "hold-limit")

    def test_the_act_runs_again_from_its_first_check(self):
        self.start()

        def revoking(hold):
            lifecycle.revoke_credential(self.S)
            return self.asker(hold)

        channel.register(revoking)
        self.script = ["once"]
        out = self.dispatch("file_read", path=self.secret)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["check"], "no-session")
        self.assertEqual(self.log("execution"), [])
        self.start()
        channel.register(self.asker)
        self.script = ["deny"]
        again = self.dispatch("file_read", path=self.secret)
        self.assertEqual(again["outcome"], "refused")
        self.assertEqual(len(self.holds), 2)
        self.assertEqual(self.holds[1]["key"], ("path", self.secret))

    def test_the_asker_is_called_with_the_store_unlocked(self):
        self.start()
        free = []

        def probing(hold):
            taken = threading.Event()

            def take():
                with self.store.write_lock():
                    taken.set()

            thread = threading.Thread(target=take, daemon=True)
            thread.start()
            thread.join(5)
            free.append(taken.is_set())
            return self.asker(hold)

        channel.register(probing)
        self.script = ["deny"]
        self.dispatch("file_read", path=self.secret)
        self.assertEqual(free, [True])

    def test_the_once_set_is_empty_after_any_dispatch(self):
        self.start()
        self.script = ["once"]
        out = self.dispatch("file_read", path=self.secret)
        self.assertEqual(out["outcome"], "done")
        self.assertFalse(channel.allowed(("path", self.secret)))

        def owner(root, cycle_id, intent):
            raise channel.Held(
                {
                    "id": "L-000000",
                    "op": "file_read",
                    "target": "t",
                    "resolved": "/t",
                    "asker": "file_read",
                    "kind": "path",
                    "check": "workspace-boundary",
                    "rule": "OC-008(a)",
                    "key": ("path", "/t"),
                }
            )

        self.script = ["once"] * 8
        with mock.patch.object(cycle, "_dispatch_to_owner", owner):
            out = self.dispatch("file_read", path="/t")
        self.assertEqual(out["check"], "hold-limit")
        self.assertFalse(channel.allowed(("path", "/t")))

        calls = []

        def raising(root, cycle_id, intent):
            calls.append(intent)
            if len(calls) == 1:
                raise channel.Held(
                    {
                        "id": "L-000001",
                        "op": "file_read",
                        "target": "u",
                        "resolved": "/u",
                        "asker": "file_read",
                        "kind": "path",
                        "check": "workspace-boundary",
                        "rule": "OC-008(a)",
                        "key": ("path", "/u"),
                    }
                )
            raise RuntimeError("the act failed")

        self.script = ["once"]
        with mock.patch.object(cycle, "_dispatch_to_owner", raising):
            with self.assertRaises(RuntimeError):
                self.dispatch("file_read", path="/u")
        self.assertFalse(channel.allowed(("path", "/u")))

    # -- the channel -----------------------------------------------------

    def test_clear_empties_both_sets(self):
        channel.allow_chat(("path", "/a"))
        channel.allow_once(("path", "/b"))
        channel.clear()
        self.assertFalse(channel.allowed(("path", "/a")))
        self.assertFalse(channel.allowed(("path", "/b")))

    def test_once_is_consumed_and_chat_is_not(self):
        channel.allow_once(("path", "/a"))
        channel.allow_chat(("path", "/b"))
        self.assertTrue(channel.allowed(("path", "/a")))
        self.assertTrue(channel.allowed(("path", "/a")))
        channel.end_intent()
        self.assertFalse(channel.allowed(("path", "/a")))
        self.assertTrue(channel.allowed(("path", "/b")))
        self.assertTrue(channel.allowed(("path", "/b")))

    def test_can_ask_needs_an_asker_and_a_cycle(self):
        self.assertFalse(channel.can_ask())
        with sil.originated_by("s-1/c-1"):
            self.assertTrue(channel.can_ask())
            channel.unregister()
            self.assertFalse(channel.can_ask())
