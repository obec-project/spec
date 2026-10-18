# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""http_fetch: the network boundary, the bounded fetch and its record
(OC-008(a), D74, D75)."""

from __future__ import annotations

import http.server
import os
import socket
import threading
import time
from unittest import mock

from helpers import TempDirTest, run_adapter

from fsp import config, lifecycle, operations, operator, sil
from fsp import exec as execution
from fsp.digest import canonical, sha256
from fsp.sil import Refused
from fsp.store import INTEGRITY, Store


class _Handler(http.server.BaseHTTPRequestHandler):
    # the request headers of every request the server received
    requests = []

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        _Handler.requests.append(self.headers)
        if self.path == "/ok":
            self._send(200, b"hello", "text/plain")
        elif self.path == "/big":
            self._send(200, b"x" * (2 << 20), "application/octet-stream")
        elif self.path == "/slow":
            time.sleep(3)
            self._send(200, b"late", "text/plain")
        elif self.path == "/redirect-in":
            self._redirect("/ok")
        elif self.path == "/redirect-out":
            self._redirect("https://other.example/ok")
        elif self.path == "/downgrade":
            self._redirect("http://example.com/ok")
        elif self.path == "/loop":
            self._redirect("/loop")
        else:
            self._send(404, b"", "text/plain")

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # the client stopped reading: the fetch cut or timed out
            pass


class FetchTests(TempDirTest):
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
        _Handler.requests.clear()
        self.resolve = mock.Mock(return_value=["93.184.216.34"])
        self.connect = mock.Mock(wraps=self._fake_connect)
        for name, fake in (("_resolve", self.resolve), ("_connect", self.connect)):
            patcher = mock.patch.object(execution, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _fake_connect(self, address, port, host, tls, timeout):
        # the local server speaks plain HTTP even for https targets
        return socket.create_connection(("127.0.0.1", self.port), timeout=timeout)

    def commit(self, changes):
        sil.commit_generation(
            self.store,
            changes=changes,
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )

    def allow(self, *entries, deny=()):
        domains = {e: {"rule": "allow"} for e in entries}
        domains.update({d: {"rule": "deny"} for d in deny})
        self.commit(
            {
                "rules.json": canonical(
                    {"default": "hold", "domains": domains, "skills": {}}
                )
            }
        )

    def last(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"][-1]

    def test_an_allowed_domain_is_fetched(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        out = execution.http_fetch(self.S, "https://example.com/ok")
        self.assertEqual(out["status"], 200)
        self.assertEqual(out["data"], b"hello")
        self.assertEqual(out["content_type"], "text/plain")
        self.assertEqual(out["outcome"], "done")
        rec = self.last("execution")
        self.assertEqual(rec["op"], "http_fetch")
        self.assertEqual(rec["target"], "https://example.com/ok")
        self.assertEqual(rec["final_url"], "https://example.com/ok")
        self.assertEqual(rec["size"], 5)
        self.assertEqual(rec["sha256"], sha256(b"hello"))

    def test_a_domain_outside_the_allowlist_is_held_and_refused(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.http_fetch(self.S, "https://example.com/ok")
        self.assertEqual(ctx.exception.check, "workspace-boundary")
        self.assertEqual(self.last("refusal")["reason"], "hold")
        self.resolve.assert_not_called()

    def test_a_denied_domain_is_refused(self):
        self.allow(deny=["example.com"])
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.http_fetch(self.S, "https://example.com/ok")
        self.assertEqual(ctx.exception.check, "workspace-boundary")
        self.resolve.assert_not_called()

    def test_the_form_of_the_url_is_checked_first(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        for url in (
            "ftp://example.com/",
            "https://user:pw@example.com/",
            "https://93.184.216.34/",
            "https://[::1]/",
            "https://example.com:8443/",
            "http://example.com/ok",
            "https://localhost/",
            "https://exa mple.com/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(Refused) as ctx:
                    execution.http_fetch(self.S, url)
                self.assertEqual(ctx.exception.check, "workspace-boundary")
        self.resolve.assert_not_called()

    def test_every_address_must_be_public(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        for addresses in (
            ["127.0.0.1"],
            ["10.0.0.1"],
            ["169.254.169.254"],
            ["224.0.0.1"],
            ["::ffff:127.0.0.1"],
            ["93.184.216.34", "10.0.0.1"],
        ):
            with self.subTest(addresses=addresses):
                self.resolve.return_value = addresses
                with self.assertRaises(Refused) as ctx:
                    execution.http_fetch(self.S, "https://example.com/ok")
                self.assertEqual(ctx.exception.check, "workspace-boundary")
        self.connect.assert_not_called()

    def test_the_connection_goes_to_the_checked_address(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        execution.http_fetch(self.S, "https://example.com/ok")
        self.connect.assert_called_once_with(
            "93.184.216.34", 443, "example.com", True, mock.ANY
        )

    def test_a_redirect_inside_the_territory_is_followed(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        out = execution.http_fetch(self.S, "https://example.com/redirect-in")
        self.assertEqual(out["status"], 200)
        self.assertEqual(out["data"], b"hello")
        self.assertEqual(len(self.last("execution")["hops"]), 2)

    def test_a_redirect_outside_the_territory_is_refused(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.http_fetch(self.S, "https://example.com/redirect-out")
        self.assertEqual(ctx.exception.check, "workspace-boundary")
        self.assertIn("other.example", ctx.exception.detail)

    def test_https_to_http_needs_an_http_entry(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.http_fetch(self.S, "https://example.com/downgrade")
        self.assertEqual(ctx.exception.check, "workspace-boundary")
        self.allow("example.com", "http://example.com")
        out = execution.http_fetch(self.S, "https://example.com/downgrade")
        self.assertEqual(out["status"], 200)

    def test_too_many_redirects_fail(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.http_fetch(self.S, "https://example.com/loop")
        self.assertEqual(ctx.exception.check, "execution")

    def test_a_large_body_is_cut(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        out = execution.http_fetch(self.S, "https://example.com/big")
        self.assertEqual(len(out["data"]), execution.FETCH_CAP)
        self.assertIs(out["truncated"], True)

    def test_the_time_limit_is_a_result(self):
        self.allow("example.com")
        with self.store.write_lock():
            settings = (
                self.store.read_json(config.OPERATIONAL)
                if self.store.exists(config.OPERATIONAL)
                else {}
            )
            settings["http_timeout_s"] = 1
            self.store.replace_json(
                INTEGRITY, config.OPERATIONAL, settings, writer=sil.WRITER
            )
        lifecycle.start(self.S)
        begun = time.monotonic()
        out = execution.http_fetch(self.S, "https://example.com/slow")
        self.assertEqual(out["outcome"], "timeout")
        self.assertLess(time.monotonic() - begun, 3)

    def test_no_header_of_the_entity_is_sent(self):
        self.allow("example.com")
        lifecycle.start(self.S)
        execution.http_fetch(self.S, "https://example.com/ok")
        headers = _Handler.requests[-1]
        self.assertTrue(headers["User-Agent"].startswith("fsp/"))
        self.assertEqual(headers["Accept-Encoding"], "identity")
        self.assertIsNone(headers.get("Cookie"))
        self.assertIsNone(headers.get("Authorization"))

    def test_attempt_write_via_http_fetch_is_refused(self):
        with self.assertRaises(Refused) as ctx:
            operations.attempt_write(self.S, "structural", "http_fetch", "x")
        self.assertEqual(ctx.exception.check, "sole-writer")

    def test_adapter_fetch_of_an_undeclared_destination(self):
        _, out = run_adapter(
            "entity",
            "actuate",
            "--store",
            self.S,
            "--op",
            "fetch",
            "--target",
            "https://undeclared.invalid/",
        )
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["refusal"]["check"], "workspace-boundary")
