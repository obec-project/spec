# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""``fsp run`` and ``fsp review``: the decisions as menus, the rollover rule,
``/allow`` and ``/deny``, and ``/exit`` with the review before the close
(D95, D96, D97, D98)."""

from __future__ import annotations

import json
import os
import pty
import select
import signal
import subprocess
import sys
import termios
import time

import test_ui
from helpers import ROOT

from fsp import chain, lifecycle, mil, operator, probes, proposals, sil, ui

BIN = test_ui.BIN
TIMEOUT = test_ui.TIMEOUT
REPLY = test_ui.REPLY
DOMAIN = [{"op": "allow-domain", "domain": "example.com"}]
PROMOTION = {
    "slug": "short answers",
    "category": "guidance",
    "content": "The Operator prefers short answers.",
}
WITH_PROMOTION = json.dumps(
    {"consolidation": "c", "working_set": [], "message": "m", "promotions": [PROMOTION]}
)
PROPOSE = json.dumps(
    {
        "intents": [
            {"op": "propose", "ops": [{"op": "set-persona", "content": "Be brief."}]}
        ]
    }
)


class Harness(test_ui.UiTest):
    """The harness of test_ui without its tests."""


for _name in [n for n in dir(test_ui.UiTest) if n.startswith("test_")]:
    setattr(Harness, _name, None)


class ReviewTest(Harness):
    def entity_proposal(self, ops=DOMAIN):
        lifecycle.start(self.S)
        pid = proposals.propose(self.S, ops)["proposal"]
        lifecycle.stop(self.S)
        return pid

    def head_rules(self):
        head = sil.read_head(self.store)["entry"]
        return self.store.read_json(chain.gen_relpath(head) + "/rules.json")

    def acts(self):
        return [r["act"] for r in self.log("operator-act")]

    def modes(self):
        return [r["mode"] for r in self.log("session-close")]

    def pending(self):
        return proposals.read_auth(self.store)["proposals"]

    def spawn(self, *args, stdin=subprocess.PIPE):
        proc = subprocess.Popen(
            [sys.executable, BIN, *args],
            cwd=self.ws,
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

    def wait_for(self, condition, what):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.05)
        self.fail("never happened: " + what)

    # -- the review of proposals -----------------------------------------

    def test_the_review_at_the_open_approves_and_rolls_over(self):
        self.entity_proposal()
        code, out, err = self.run_fsp("1\n1\n")
        self.assertEqual(code, 0, err)
        self.assertIn("1 proposal(s) pending", out)
        self.assertIn("allow-domain example.com", out)
        self.assertIn("origin: entity, session s-1", out)
        self.assertIn("applied", out)
        self.assertIn("approve", self.acts())
        self.assertIn("rollover", self.modes())
        self.assertEqual(len(self.log("endure-complete")), 1)
        self.assertEqual(self.head_rules()["domains"]["example.com"]["rule"], "allow")
        self.assertEqual(self.pending(), {})

    def test_later_at_the_open_decides_nothing(self):
        pid = self.entity_proposal()
        code, out, err = self.run_fsp("2\n")
        self.assertEqual(code, 0, err)
        self.assertNotIn("approve", self.acts())
        self.assertNotIn("rollover", self.modes())
        self.assertEqual(self.log("endure-complete"), [])
        self.assertIn(pid, self.pending())
        self.assertEqual(self.head_rules()["domains"], {})

    def test_review_rejects_a_proposal(self):
        pid = self.entity_proposal()
        code, out, err = self.run_fsp("2\n/review\n2\n")
        self.assertEqual(code, 0, err)
        self.assertIn("reject", self.acts())
        self.assertNotIn(pid, self.pending())
        self.assertIn("System: rejected " + pid, out)
        self.assertNotIn("rollover", self.modes())

    def test_review_with_nothing_pending_says_so(self):
        code, out, err = self.run_fsp("/review\n")
        self.assertEqual(code, 0, err)
        self.assertIn("System: no proposal pending", out)

    def test_allow_and_deny_record_and_apply_at_the_line_end(self):
        code, out, err = self.run_fsp(
            "/allow domain example.com\n/deny domain example.org\n"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("System: recorded P-"), 2)
        self.assertEqual(out.count("System: applying 1 authorized change(s)"), 2)
        self.assertEqual(out.count("applied (entry"), 2)
        domains = self.head_rules()["domains"]
        self.assertEqual(domains["example.com"]["rule"], "allow")
        self.assertEqual(domains["example.org"]["rule"], "deny")
        self.assertEqual(self.modes(), ["rollover", "rollover", "suspend"])

    def test_allow_of_a_skill_that_is_not_installed_is_refused(self):
        code, out, err = self.run_fsp("/allow skill nope\n")
        self.assertEqual(code, 0, err)
        self.assertIn("refused (skill-unknown)", out)
        self.assertEqual(self.modes(), ["suspend"])

    def test_allow_deny_and_review_with_wrong_arguments_print_usage(self):
        code, out, err = self.run_fsp(
            "/allow\n/deny domain\n/allow file x\n/review x\n"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("System: usage: /allow"), 2)
        self.assertIn("System: usage: /deny", out)
        self.assertIn("System: usage: /review", out)
        self.assertEqual(self.log("refusal"), [])

    def test_help_lists_the_new_commands(self):
        code, out, err = self.run_fsp("/help\n")
        self.assertEqual(code, 0, err)
        for usage in ("/allow domain D", "/deny skill N", "System: /review"):
            self.assertIn(usage, out)

    # -- /exit -----------------------------------------------------------

    def exit_with_promotion(self, text):
        code, self.out, err = self.run_fsp(text, WITH_PROMOTION)
        self.assertEqual(code, 0, err)
        self.assertIn("Promotion PP-", self.out)
        self.assertIn("slug: short answers", self.out)
        self.assertEqual(self.modes(), ["normal"])
        return mil.semantic_records(self.store)

    def test_exit_approves_a_promotion(self):
        records = self.exit_with_promotion("/exit\n1\n")
        self.assertEqual([r["content"] for r in records], [PROMOTION["content"]])

    def test_exit_rejects_a_promotion(self):
        self.assertEqual(self.exit_with_promotion("/exit\n3\n"), [])

    def test_exit_edits_a_promotion_before_approving_it(self):
        out = self.exit_with_promotion("/exit\n2\nShort is better.\n")
        self.assertEqual([r["content"] for r in out], ["Short is better."])
        self.assertEqual(out[0]["slug"], PROMOTION["slug"])

    def test_exit_asks_again_when_the_probes_flag_an_edit(self):
        flagged = probes.REFERENCE_TEXTS[0]
        text = "/exit\n2\n%s\n2\nShort is better.\n" % flagged
        records = self.exit_with_promotion(text)
        self.assertIn("System: refused (", self.out)
        self.assertEqual(self.out.count("Promotion PP-"), 2)
        self.assertEqual([r["content"] for r in records], ["Short is better."])

    def test_exit_reviews_proposals_before_the_promotions_and_commits_them(self):
        self.entity_proposal()
        code, out, err = self.run_fsp("2\n/exit\n1\n1\n", WITH_PROMOTION)
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("Proposal P-"), out.index("Promotion PP-"))
        self.assertEqual(self.modes(), ["normal", "normal"])
        self.assertEqual(self.head_rules()["domains"]["example.com"]["rule"], "allow")
        self.assertEqual(len(mil.semantic_records(self.store)), 1)

    def test_exit_as_the_first_line_needs_no_turn(self):
        code, out, err = self.run_fsp("/exit\n", test_ui.CLOSURE)
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(len(self.log("sleep-complete")), 1)
        self.assertIn("closed", out)
        self.assertEqual(self.modes(), ["normal"])

    # -- the rollover rule -----------------------------------------------

    def test_an_approval_from_another_terminal_applies_at_the_next_line(self):
        proc = self.spawn("run", "--store", self.S)
        self.wait_for_holder(proc)
        self.wait_for_workspace()
        operator.allow(self.S, "domain", "example.com")
        proc.stdin.write("\n")
        proc.stdin.flush()
        self.wait_for(lambda: "rollover" in self.modes(), "the rollover")
        stdout, err = proc.communicate(timeout=TIMEOUT)
        self.assertEqual(proc.returncode, 0, err)
        self.assertIn("applied", stdout)
        self.assertEqual(self.head_rules()["domains"]["example.com"]["rule"], "allow")

    def test_fsp_review_decides_with_no_session_and_the_next_open_applies(self):
        self.entity_proposal()
        proc = self.spawn("review", "--store", self.S)
        out, err = proc.communicate("1\n", timeout=TIMEOUT)
        self.assertEqual(proc.returncode, 0, err)
        self.assertIn("Proposal P-", out)
        self.assertIn("approve", self.acts())
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertEqual(self.log("endure-complete"), [])
        code, out, err = self.run_fsp("")
        self.assertEqual(code, 0, err)
        self.assertIn("applied", out)
        self.assertEqual(self.head_rules()["domains"]["example.com"]["rule"], "allow")

    def test_fsp_review_at_the_end_of_input_exits_zero(self):
        self.entity_proposal()
        proc = self.spawn("review", "--store", self.S)
        out, err = proc.communicate("", timeout=TIMEOUT)
        self.assertEqual(proc.returncode, 0, err)
        self.assertNotIn("approve", self.acts())

    # -- the menus -------------------------------------------------------

    def test_a_number_out_of_range_is_asked_again(self):
        self.entity_proposal()
        code, out, err = self.run_fsp("9\n1\n")
        self.assertIn("choose a number from 1 to 2", out)
        self.assertIn("Proposal P-", out)
        self.assertEqual(code, 0, err)

    def test_the_end_of_input_during_a_menu_is_a_suspend(self):
        self.entity_proposal()
        code, out, err = self.run_fsp("1\n")
        self.assertEqual(code, 0, err)
        self.assertIn("System: suspended", out)
        self.assertEqual(self.modes(), ["normal", "suspend"])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_the_entity_proposing_during_a_chain_is_told_to_the_operator(self):
        code, out, err = self.run_fsp("hi\n", PROPOSE, REPLY)
        self.assertEqual(code, 0, err)
        self.assertIn("the entity proposed 1 change(s)", out)
        self.assertIn("hello there", out)
        self.assertEqual(len(self.pending()), 1)

    def test_a_proposal_the_operator_did_not_ask_for_is_not_a_stimulus(self):
        self.entity_proposal()
        code, out, err = self.run_fsp("1\n1\n")
        self.assertEqual(code, 0, err)
        for session in ("s-1", "s-2", "s-3"):
            self.assertEqual(self.session_records(session, "stimulus"), [])

    # -- the menu on a terminal ------------------------------------------

    def start_on_a_pty(self, argv):
        """``(master, proc)``: ``argv`` with a pty's slave as its stdin and
        stdout."""
        try:
            master, slave = pty.openpty()
        except OSError as e:
            self.skipTest("no pty in this environment: %s" % e)
        self.addCleanup(os.close, master)
        proc = subprocess.Popen(
            argv,
            cwd=self.ws,
            env=dict(os.environ, HOME=self.tmp),
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
        )
        os.close(slave)

        def cleanup():
            if proc.poll() is None:
                proc.kill()
            proc.wait()

        self.addCleanup(cleanup)
        return master, proc

    def choose_on_a_pty(self, keys):
        script = "\n".join(
            [
                "import sys, termios",
                "sys.path.insert(0, %r)" % ROOT,
                "from fsp import ui",
                "before = termios.tcgetattr(0)",
                "index = ui.choose('q', ['a', 'b', 'c'])",
                "print(index, termios.tcgetattr(0) == before, flush=True)",
            ]
        )
        master, proc = self.start_on_a_pty([sys.executable, "-c", script])
        seen = self.read_pty(master, "3) c")
        os.write(master, keys)
        seen += self.read_pty(master, "True", "False")
        proc.wait(timeout=TIMEOUT)
        return seen

    def read_pty(self, master, *needles):
        seen = ""
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                seen += chunk.decode("utf-8", errors="replace")
                if any(n in seen for n in needles):
                    return seen
        self.fail("the child never printed %r: %r" % (needles, seen))

    def test_the_menu_moves_with_the_arrows_and_restores_the_terminal(self):
        seen = self.choose_on_a_pty(b"\x1b[B\x1b[B\r")
        self.assertIn("2 True", seen)
        self.assertIn("q → c", seen)

    def test_the_menu_takes_a_digit_directly(self):
        seen = self.choose_on_a_pty(b"3")
        self.assertIn("2 True", seen)

    def test_a_signal_during_a_menu_restores_the_terminal_and_suspends(self):
        self.entity_proposal()
        argv = [sys.executable, BIN, "run", "--store", self.S]
        master, proc = self.start_on_a_pty(argv)
        before = termios.tcgetattr(master)
        self.read_pty(master, "2) Later")
        self.assertEqual(termios.tcgetattr(master)[3] & termios.ICANON, 0)
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=TIMEOUT)
        self.assertEqual(proc.returncode, 128 + signal.SIGTERM.value)
        self.assertEqual(termios.tcgetattr(master), before)
        self.assertEqual(self.modes(), ["normal", "suspend"])

    # -- what is shown ---------------------------------------------------

    def test_an_op_is_shown_on_one_line(self):
        digest = "sha256:" + "ab" * 32
        cases = [
            ({"op": "set-persona", "content": "x" * 300 + "\nz"}, "x" * 200),
            (
                {"op": "install-skill", "name": "s", "files": {"b.md": "", "a.md": ""}},
                "install-skill s (a.md, b.md)",
            ),
            ({"op": "deny-domain", "domain": "d.example"}, "deny-domain d.example"),
            ({"op": "allow-skill", "name": "s", "digest": digest}, digest[:12]),
            ({"op": "unset-skill", "name": "s"}, "unset-skill s"),
            (
                {"op": "set-parameter", "name": "always_loaded", "value": ["rule"]},
                'always_loaded ["rule"]',
            ),
        ]
        for op, expected in cases:
            with self.subTest(op=op["op"]):
                line = ui._op_line(op)
                self.assertIn(expected, line)
                self.assertNotIn("\n", line)
        self.assertNotIn("x" * 201, ui._op_line(cases[0][0]))
        self.assertNotIn(digest, ui._op_line(cases[3][0]))

    def test_control_characters_of_the_entity_are_not_shown(self):
        self.assertEqual(ui._plain("a\x1b[2Jb\nc"), "a [2Jb c")
        self.assertEqual(ui._plain("a\nb", keep="\n"), "a\nb")
