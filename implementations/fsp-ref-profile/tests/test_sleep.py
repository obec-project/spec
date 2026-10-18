# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Sleep after every normal close, and its re-run after a crash (D83)."""

from __future__ import annotations

from unittest import mock

from helpers import TempDirTest

from fsp import lifecycle, mil, operator, sil
from fsp.store import INTEGRITY, Store


MARKER = {
    "session": "s-1",
    "mode": "normal",
    "done": [],
    "ran": [],
    "consolidated": None,
}


class SleepTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def payload(self, *promotions):
        return {
            "consolidation": "We planned the release.",
            "working_set": [],
            "message": "Next: tag it.",
            "promotions": list(promotions),
        }

    def requests(self, *overrides):
        promotions = [
            {
                "slug": "short answers",
                "category": "guidance",
                "content": "The Operator prefers short answers.",
                **kw,
            }
            for kw in overrides
        ]
        return operator.record_closure(self.S, self.payload(*promotions))["requests"]

    def request(self, **kw):
        (pid,) = self.requests(kw)
        return pid

    def approved(self, **kw):
        pid = self.request(**kw)
        operator.approve_promotion(self.S, pid)
        return pid

    def sessions(self):
        return self.store.read_json(lifecycle.SESSIONS)

    def set_sessions(self, **fields):
        s = self.sessions()
        s.update(fields)
        self.store.replace_json(INTEGRITY, lifecycle.SESSIONS, s, writer="sil")

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def kinds(self):
        return [r["kind"] for r in self.log()]

    def test_stop_runs_a_sleep(self):
        out = lifecycle.stop(self.S)
        self.assertEqual(
            self.kinds()[-3:], ["session-close", "closure-begin", "closure-complete"]
        )
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertIsNone(self.sessions()["closing"])
        chk = self.store.read_json("integrity/log-checkpoint.json")
        self.assertEqual(chk["id"], out["log_records"][-1])
        self.assertEqual(chk["id"], self.log("closure-complete")[-1]["id"])

    def test_the_sleep_promotes_authorized_requests(self):
        self.approved()
        out = operator.close_conversation(self.S)
        records = mil.semantic_records(self.store)
        self.assertEqual(len(records), 1)
        self.assertEqual(out["sleep"]["promoted"], [records[0]["id"]])
        self.assertEqual(out["sleep"]["refused"], [])
        (complete,) = self.log("sleep-complete")
        self.assertEqual(complete["promoted"], [records[0]["id"]])

    def test_an_unauthorized_request_stays_pending(self):
        self.request()
        out = operator.close_conversation(self.S)
        self.assertEqual(out["sleep"], {"promoted": [], "refused": []})
        self.assertEqual(mil.semantic_records(self.store), [])
        self.assertEqual(sil.semantic_ledger(self.store), [])

    def test_a_refused_promotion_does_not_stop_the_sleep(self):
        first, second = self.requests(
            {"slug": "first", "supersedes": "S-0000"}, {"slug": "second"}
        )
        operator.approve_promotion(self.S, first)
        operator.approve_promotion(self.S, second)
        out = operator.close_conversation(self.S)
        self.assertEqual(out["sleep"]["refused"], [first])
        self.assertEqual(len(out["sleep"]["promoted"]), 1)
        self.assertEqual(len(self.log("sleep-complete")), 1)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_a_request_is_promoted_once_across_sleeps(self):
        self.approved()
        operator.close_conversation(self.S)
        lifecycle.start(self.S)
        out = lifecycle.stop(self.S)
        self.assertEqual(out["sleep"]["promoted"], [])
        self.assertEqual(len(mil.semantic_records(self.store)), 1)

    def test_a_request_of_an_earlier_payload_is_not_promoted(self):
        self.approved()
        operator.record_closure(self.S, self.payload())
        out = operator.close_conversation(self.S)
        self.assertEqual(out["sleep"], {"promoted": [], "refused": []})
        self.assertEqual(mil.semantic_records(self.store), [])
        self.assertEqual(sil.semantic_ledger(self.store), [])

    def test_the_session_is_closed_before_the_sleep(self):
        self.approved()
        seen = []

        def capture(*args, **kwargs):
            seen.append((self.sessions(), self.store.exists(lifecycle.CREDENTIAL)))

        with mock.patch.object(mil, "promote", side_effect=capture):
            operator.close_conversation(self.S)
        (sessions, credential) = seen[0]
        self.assertIsNone(sessions["open_session"])
        self.assertEqual(sessions["closing"]["session"], "s-1")
        self.assertTrue(credential)

    def test_a_crash_in_the_sleep_is_recovered_at_the_next_start(self):
        self.approved()
        with mock.patch.object(mil, "promote", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                operator.close_conversation(self.S)
        self.assertTrue(self.store.exists(lifecycle.CREDENTIAL))
        self.assertEqual(self.sessions()["closing"]["session"], "s-1")
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        (gate,) = [g for g in res.gates if g["gate"] == "crash-recovery"]
        self.assertEqual(gate["outcome"], "recovered")
        reruns = [r for r in self.log("sleep-complete") if r["rerun"] is True]
        self.assertEqual([r["session"] for r in reruns], ["s-1"])
        self.assertEqual(len(mil.semantic_records(self.store)), 1)
        self.assertIsNone(self.sessions()["closing"])

    def test_the_marker_alone_is_a_crash(self):
        operator.new_conversation(self.S)
        self.set_sessions(closing=dict(MARKER))
        res = lifecycle.start(self.S)
        (gate,) = [g for g in res.gates if g["gate"] == "crash-recovery"]
        self.assertEqual(gate["outcome"], "recovered")
        self.assertEqual(self.sessions()["consecutive_recoveries"], 1)
        reruns = [r for r in self.log("sleep-complete") if r["rerun"] is True]
        self.assertEqual(len(reruns), 1)

    def test_a_sleep_that_keeps_crashing_halts_at_n_boot(self):
        lifecycle.stop(self.S)
        self.set_sessions(closing=dict(MARKER), consecutive_recoveries=3)
        res = lifecycle.start(self.S)
        self.assertEqual((res.outcome, res.lesser_outcome), ("aborted", "halted"))
        self.assertTrue(self.store.exists(sil.PASSIVE_SIGNAL))

    def test_the_rerun_waits_for_the_authorization_gate(self):
        operator.new_conversation(self.S)
        self.set_sessions(closing=dict(MARKER))
        with open(self.store.path(lifecycle.AUTH), "wb") as f:
            f.write(b"not json")
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "aborted")
        self.assertEqual(res.gates[-1]["gate"], "authorization-state")
        reruns = [r for r in self.log("sleep-complete") if r["rerun"] is True]
        self.assertEqual(reruns, [])
        self.assertEqual(self.sessions()["closing"], MARKER)
