# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The suite catches what it claims to catch.

A runner that has never seen a failure is a runner nobody should trust. The
stub breaks on demand (OBEC_STUB_BREAK); each break must fail exactly the
tests the runner README says it does, and the unbroken stub must fail none.

Slow by test-suite standards — every case is a full run of the suite.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "..", "run.py")
STUB = os.path.join(HERE, "..", "stub", "obec-adapter-stub")

# Break -> the tests it must fail, as documented in runner/README.md.
BREAKS = {
    "oc001b": {"OC-001", "OC-005"},
    "oc002b": {"OC-002"},
    "oc003b": {"OC-003"},
    "oc003c": {"OC-003", "OC-008"},
    "oc008a": {"OC-008"},
    "oc008d": {"OC-001", "OC-002", "OC-003", "OC-005", "OC-008"},
    "oc010": {"OC-002", "OC-004", "OC-010"},
}

# Without a real second host step 3.2 cannot fail; the suite says so rather
# than pass it, and 4.9-4.12 wait on a version transition that 0.9 cannot make.
UNESTABLISHED = {"3.2", "4.9", "4.10", "4.11", "4.12"}


class SuiteAgainstStub(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_suite(self, env=None, adapter_b=None):
        out = os.path.join(self.tmp.name, "claim")
        cmd = [sys.executable, RUNNER, "--adapter", STUB, "-q", "--out", out]
        if adapter_b:
            cmd += ["--adapter-b", adapter_b]
        proc = subprocess.run(cmd, env={**os.environ, **(env or {})},
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=600)
        with open(out + ".json", encoding="utf-8") as f:
            return proc.returncode, json.load(f)

    def second_host(self):
        """An adapter that reports a different hostname. On one machine it is
        the only way to make step 3.2 able to fail."""
        path = os.path.join(self.tmp.name, "adapter-b")
        with open(path, "w") as f:
            f.write(f'#!/bin/sh\nOBEC_STUB_HOSTNAME=host-b exec "{sys.executable}" "{STUB}" "$@"\n')
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return path

    @staticmethod
    def steps(claim, outcome):
        return {s["step"] for t in claim["tests"] for s in t["steps"]
                if s["outcome"] == outcome}

    @staticmethod
    def failed(claim):
        return {t["rule"] for t in claim["tests"]
                if t["outcome"] in ("fail", "error")}

    def test_clean_stub_fails_nothing(self):
        code, claim = self.run_suite()
        self.assertEqual(self.failed(claim), set())
        self.assertEqual(self.steps(claim, "error"), set())
        self.assertEqual(self.steps(claim, "unestablished"), UNESTABLISHED)
        self.assertFalse(claim["conformant"])
        self.assertEqual(code, 3)   # nothing failed, not conformant

    def test_each_break_fails_exactly_its_tests(self):
        for mode, expected in BREAKS.items():
            with self.subTest(mode=mode):
                env = {"OBEC_STUB_BREAK": mode}
                b = self.second_host() if mode == "oc003b" else None
                code, claim = self.run_suite(env, adapter_b=b)
                self.assertEqual(self.failed(claim), expected)
                self.assertEqual(self.steps(claim, "error"), set())
                self.assertEqual(code, 1)

    def test_hc003b_invisible_on_one_host(self):
        """Without a second host the break must surface as unestablished,
        never as a pass: the suite does not claim what it cannot check."""
        _, claim = self.run_suite({"OBEC_STUB_BREAK": "oc003b"})
        self.assertEqual(self.failed(claim), set())
        self.assertIn("3.2", self.steps(claim, "unestablished"))

    def test_broken_adapter_is_an_error_not_a_failure(self):
        """An adapter that answers nonsense has not been tested at all: every
        test is an error and the run exits 4, never 1."""
        bad = os.path.join(self.tmp.name, "bad-adapter")
        with open(bad, "w") as f:
            f.write("#!/bin/sh\necho not-json\n")
        os.chmod(bad, os.stat(bad).st_mode | stat.S_IXUSR)
        out = os.path.join(self.tmp.name, "claim")
        proc = subprocess.run([sys.executable, RUNNER, "--adapter", bad, "-q",
                               "--out", out], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=600)
        with open(out + ".json", encoding="utf-8") as f:
            claim = json.load(f)
        self.assertEqual({t["outcome"] for t in claim["tests"]}, {"error"})
        self.assertEqual(proc.returncode, 4)

    def test_unimplemented_adapter_fails_nothing(self):
        """An adapter implementing nothing has established nothing: every
        step is unestablished, none fails. A step that fails only because
        the steps it draws on could not run would blame the implementation
        for the suite's missing evidence."""
        none = os.path.join(self.tmp.name, "empty-adapter")
        with open(none, "w") as f:
            f.write("#!/bin/sh\nexit 2\n")
        os.chmod(none, os.stat(none).st_mode | stat.S_IXUSR)
        out = os.path.join(self.tmp.name, "claim")
        proc = subprocess.run([sys.executable, RUNNER, "--adapter", none, "-q",
                               "--out", out], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=600)
        with open(out + ".json", encoding="utf-8") as f:
            claim = json.load(f)
        self.assertEqual(self.failed(claim), set())
        self.assertEqual(self.steps(claim, "pass"), set())
        self.assertEqual(proc.returncode, 3)

    def test_production_build_refuses_injection(self):
        proc = subprocess.run([sys.executable, STUB, "inject", "passive-signal"],
                              env={**os.environ, "OBEC_STUB_PRODUCTION": "1"},
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
