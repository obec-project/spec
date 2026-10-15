# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The process that holds a session: the credential's lock, suspend, the
registry of running skills and the workspace boundary check (D92, D30)."""

from __future__ import annotations

import os
import subprocess
import sys
from unittest import mock

from helpers import ROOT, TempDirTest

from fsp import exec as execution
from fsp import lifecycle, mil, operator, sil
from fsp.store import Store, remove_as_operator

DIE_HOLDING = (
    "import os, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from fsp import lifecycle\n"
    "res = lifecycle.start(sys.argv[2], hold=True)\n"
    "assert res.outcome == 'accepted', res.outcome\n"
    "os._exit(0)\n"
)


class Base(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def sessions(self):
        return self.store.read_json(lifecycle.SESSIONS)

    def hold(self):
        res = lifecycle.start(self.S, hold=True)
        self.assertEqual(res.outcome, "accepted")
        self.addCleanup(res.holder.release)
        return res

    def log_size(self):
        return os.path.getsize(self.store.path(sil.LOG))


class HoldTheLock(Base):
    def test_start_with_hold_takes_the_lock_and_names_the_process(self):
        res = self.hold()
        cred = self.store.read_json(lifecycle.CREDENTIAL)
        self.assertEqual(cred["holder"], {"pid": os.getpid()})
        self.assertEqual(self.store.probe_lock(lifecycle.CREDENTIAL), "held")
        second = lifecycle.start(self.S)
        self.assertEqual(second.outcome, "refused")
        self.assertEqual(second.gates[-1]["gate"], "crash-recovery")
        self.assertEqual(second.gates[-1]["outcome"], "conflict")
        res.holder.release()
        self.assertEqual(self.store.probe_lock(lifecycle.CREDENTIAL), "free")
        res.holder.release()  # idempotent

    def test_a_lock_not_taken_aborts_the_start_and_writes_nothing_else(self):
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        before = self.store.read_bytes(lifecycle.SESSIONS)
        opened = len(self.log("session-open"))
        with mock.patch.object(Store, "hold_lock", return_value=None):
            res = lifecycle.start(self.S, hold=True)
        self.assertEqual(res.outcome, "aborted")
        self.assertIsNone(res.holder)
        aborted = self.log("start-aborted")
        self.assertEqual(len(aborted), 1)
        self.assertEqual(aborted[0]["reason"], "credential-lock")
        self.assertEqual(aborted[0]["gate"], "crash-recovery")
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertEqual(self.store.read_bytes(lifecycle.SESSIONS), before)
        self.assertEqual(len(self.log("session-open")), opened)

    def test_a_holder_that_died_is_a_crash_the_next_start_recovers(self):
        proc = subprocess.run(
            [sys.executable, "-c", DIE_HOLDING, ROOT, self.S],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.store.exists(lifecycle.CREDENTIAL))
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        self.assertEqual(res.gates[1]["gate"], "crash-recovery")
        self.assertEqual(res.gates[1]["outcome"], "recovered")
        self.assertIs(self.log("recovery")[-1]["process_holder"], True)


class Suspend(Base):
    def test_suspend_closes_the_session_without_a_sleep(self):
        res = self.hold()
        out = lifecycle.suspend(self.S, signal="SIGINT", chain=False)
        self.assertIs(out["suspended"], True)
        self.assertEqual(out["session"], res.session)
        close = self.log("session-close")[-1]
        self.assertEqual(close["mode"], "suspend")
        self.assertEqual(close["signal"], "SIGINT")
        self.assertIs(close["chain"], False)
        self.assertEqual(close["skills_ended"], 0)
        self.assertEqual(close["session"], res.session)
        self.assertEqual(close["rule"], "OP-021(a)")
        self.assertEqual(out["log_records"], [close["id"]])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        sessions = self.sessions()
        self.assertIsNone(sessions["open_session"])
        self.assertEqual(sessions["consecutive_recoveries"], 0)
        self.assertIsNone(sessions["closing"])
        self.assertEqual(self.log("closure-begin"), [])
        res.holder.release()
        again = lifecycle.start(self.S, hold=True)
        self.addCleanup(again.holder.release)
        self.assertEqual(again.outcome, "accepted")
        self.assertEqual(again.gates[1]["outcome"], "pass")
        opened = [
            r
            for r in mil.session_records(self.store, again.session)
            if r.get("kind") == "session-open"
        ]
        self.assertEqual(opened[0]["continues"], res.session)

    def test_suspend_records_the_end_of_input_and_the_chain(self):
        self.hold()
        out = lifecycle.suspend(self.S, signal=None, chain=True)
        self.assertIs(out["suspended"], True)
        close = self.log("session-close")[-1]
        self.assertIsNone(close["signal"])
        self.assertIs(close["chain"], True)

    def test_suspend_leaves_a_credential_without_a_holder_alone(self):
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        before = self.log_size()
        credential = self.store.read_bytes(lifecycle.CREDENTIAL)
        out = lifecycle.suspend(self.S, signal="SIGTERM", chain=False)
        self.assertEqual(out, {"suspended": False, "session": None, "log_records": []})
        self.assertEqual(self.log_size(), before)
        self.assertEqual(self.store.read_bytes(lifecycle.CREDENTIAL), credential)
        self.assertEqual(self.sessions()["open_session"], res.session)

    def test_suspend_after_a_direct_revocation_logs_it(self):
        res = self.hold()
        self.assertTrue(remove_as_operator(self.S, lifecycle.CREDENTIAL))
        out = lifecycle.suspend(self.S, signal="SIGHUP", chain=False)
        self.assertIs(out["suspended"], False)
        removed = self.log("credential-removed-directly")
        self.assertEqual([r["session"] for r in removed], [res.session])
        self.assertEqual(removed[0]["rule"], "OC-002(b)")
        self.assertIsNone(self.sessions()["open_session"])
        self.assertEqual(self.log("session-close"), [])


class RunningSkills(Base):
    def test_end_running_ends_every_registered_group(self):
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)

        def cleanup():
            proc.kill()
            proc.wait()

        self.addCleanup(cleanup)
        with execution._RUNNING_LOCK:
            execution._RUNNING.add(proc.pid)
        self.assertEqual(execution.end_running(), 1)
        self.assertEqual(proc.wait(timeout=5), -9)
        self.assertEqual(execution.end_running(), 0)


class WorkspaceCrossing(Base):
    def test_the_limits_are_the_store_and_the_dot_fsp_folder(self):
        home = self.p("h", "home")
        os.makedirs(os.path.join(home, ".fsp"))
        inside = self.p("S", "inside")
        sibling = self.p("sibling")
        os.mkdir(sibling)
        with mock.patch.dict(os.environ, {"HOME": home}):
            for crossing, limit in (
                (self.S, self.S),
                (inside, self.S),
                (self.tmp, self.S),
                (self.p("h"), os.path.join(home, ".fsp")),
                (home, os.path.join(home, ".fsp")),
            ):
                found = operator.workspace_crossing(self.store, crossing)
                self.assertEqual(
                    found,
                    (os.path.realpath(crossing), os.path.realpath(limit)),
                    crossing,
                )
            self.assertIsNone(operator.workspace_crossing(self.store, sibling))
