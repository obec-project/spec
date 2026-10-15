# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Closure in three phases, the Endure phase, the interrupted commit and
the rollover (D83, D94)."""

from __future__ import annotations

from unittest import mock

from helpers import TempDirTest

from fsp import chain, lifecycle, mil, operator, proposals, sil
from fsp.store import Store
from fsp_testing import fixture, hooks


class Base(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def tearDown(self):
        hooks.clear_clock(self.S)
        super().tearDown()

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def kinds(self):
        return [r["kind"] for r in self.log()]

    def sessions(self):
        return self.store.read_json(lifecycle.SESSIONS)

    def auth(self):
        return proposals.read_auth(self.store)

    def head(self):
        return sil.read_head(self.store)["entry"]

    def domain(self, domain="example.com", *, approve=True):
        pid = proposals.propose(self.S, [{"op": "allow-domain", "domain": domain}])[
            "proposal"
        ]
        if approve:
            operator.approve(self.S, pid)
        return pid

    def skill(self, *, approve=True):
        files = fixture.skill_files("example")
        pid = proposals.propose(
            self.S, [{"op": "install-skill", "name": "example", "files": files}]
        )["proposal"]
        if approve:
            operator.approve(self.S, pid)
        return pid

    def checkpoint(self):
        return self.store.read_json("integrity/log-checkpoint.json")


class PhasesTests(Base):
    def test_a_plain_stop_with_nothing_authorized_runs_integrity_only(self):
        out = lifecycle.stop(self.S)
        self.assertEqual(
            self.kinds()[-3:], ["session-close", "closure-begin", "closure-complete"]
        )
        (complete,) = self.log("closure-complete")
        self.assertEqual(complete["phases"], ["integrity"])
        self.assertEqual(complete["mode"], "normal")
        self.assertEqual(self.log("sleep-complete"), [])
        self.assertEqual(self.log("endure-complete"), [])
        self.assertEqual(self.checkpoint()["id"], complete["id"])
        self.assertEqual(out["log_records"][-1], complete["id"])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertIsNone(self.sessions()["closing"])

    def test_a_new_conversation_runs_the_sleep_phase(self):
        operator.new_conversation(self.S)
        self.assertEqual(len(self.log("sleep-complete")), 1)
        self.assertEqual(len(self.log("gc")), 1)
        (complete,) = self.log("closure-complete")
        self.assertEqual(complete["phases"], ["sleep", "integrity"])
        self.assertEqual(self.checkpoint()["id"], complete["id"])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertIsNone(self.sessions()["closing"])

    def test_closing_is_set_before_any_record_of_the_close(self):
        seen = []
        real = sil.log_append_located

        def spy(store, kind, **kw):
            if kind == "session-close":
                seen.append(self.sessions()["closing"])
            return real(store, kind, **kw)

        with mock.patch.object(lifecycle.sil, "log_append_located", spy):
            lifecycle.stop(self.S)
        self.assertEqual(
            seen,
            [
                {
                    "session": "s-1",
                    "mode": "normal",
                    "done": [],
                    "ran": [],
                    "consolidated": None,
                }
            ],
        )

    def test_the_credential_goes_after_the_checkpoint(self):
        seen = []
        real = sil.write_log_checkpoint

        def spy(store, loc):
            real(store, loc)
            seen.append(self.store.exists(lifecycle.CREDENTIAL))

        with mock.patch.object(lifecycle.sil, "write_log_checkpoint", spy):
            lifecycle.stop(self.S)
        self.assertEqual(seen, [True])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))


class EndureTests(Base):
    def test_an_approved_proposal_commits_at_stop(self):
        pid = self.domain()
        before = self.head()
        out = lifecycle.stop(self.S)
        (done,) = self.log("endure-complete")
        self.assertEqual(done["committed"], [pid])
        self.assertEqual(done["dropped"], [])
        self.assertEqual(self.head(), before + 1)
        auth = self.auth()
        self.assertNotIn(pid, auth["proposals"])
        self.assertNotIn(pid, auth["approvals"])
        self.assertEqual([c["proposal"] for c in out["endure"]["committed"]], [pid])
        self.assertEqual(out["endure"]["committed"][0]["entry"], before + 1)
        (complete,) = self.log("closure-complete")
        self.assertEqual(complete["phases"], ["endure", "integrity"])

    def test_a_proposal_without_authorization_waits(self):
        pid = self.domain(approve=False)
        before = self.head()
        out = lifecycle.stop(self.S)
        self.assertIn(pid, self.auth()["proposals"])
        self.assertEqual(self.head(), before)
        self.assertEqual(self.log("endure-complete"), [])
        self.assertEqual(self.log("proposal-dropped"), [])
        self.assertEqual(out["endure"], {"committed": [], "dropped": []})

    def test_a_window_covers_the_proposal(self):
        grant = operator.grant(self.S, expiry="+1h", budget=3, scope="rules")["grant"]
        pid = self.domain(approve=False)
        before = self.head()
        lifecycle.stop(self.S)
        self.assertEqual(self.head(), before + 1)
        self.assertNotIn(pid, self.auth()["proposals"])
        (window,) = self.auth()["grants"]
        self.assertEqual(window["used"], 1)
        self.assertEqual(window["state"], "open")
        notes = [
            r
            for r in self.log("operator-notification")
            if "window-commit" == r["condition"]
        ]
        self.assertEqual(len(notes), 1)
        self.assertEqual(
            notes[0]["detail"], {"proposal": pid, "grant": grant, "entry": before + 1}
        )
        (done,) = self.log("endure-complete")
        self.assertEqual(done["committed"], [pid])

    def test_two_approved_proposals_commit_in_order_of_origination(self):
        first = self.domain("first.example.com")
        second = self.domain("second.example.com")
        before = self.head()
        out = lifecycle.stop(self.S)
        (done,) = self.log("endure-complete")
        self.assertEqual(done["committed"], [first, second])
        self.assertEqual(self.head(), before + 2)
        self.assertEqual(
            [c["entry"] for c in out["endure"]["committed"]], [before + 1, before + 2]
        )

    def test_a_commit_refused_for_its_content_is_dropped(self):
        first = self.skill()
        second = self.skill()
        before = self.head()
        out = lifecycle.stop(self.S)
        self.assertEqual(self.head(), before + 1)
        (dropped,) = self.log("proposal-dropped")
        self.assertEqual(dropped["proposal"], second)
        self.assertEqual(dropped["check"], "skill-exists")
        self.assertEqual(dropped["rule"], "OC-001(b)")
        notes = [
            r
            for r in self.log("operator-notification")
            if r["condition"] == "commit-refused"
        ]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["detail"]["proposal"], second)
        self.assertEqual(notes[0]["detail"]["check"], "skill-exists")
        auth = self.auth()
        self.assertEqual((auth["proposals"], auth["approvals"]), ({}, {}))
        (done,) = self.log("endure-complete")
        self.assertEqual((done["committed"], done["dropped"]), ([first], [second]))
        self.assertEqual([d["proposal"] for d in out["endure"]["dropped"]], [second])
        self.assertEqual(len(self.log("closure-complete")), 1)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_a_successful_commit_leaves_no_mark(self):
        pid = self.domain()
        proposals.commit(self.S, pid)
        self.assertNotIn(pid, self.auth()["proposals"])
        self.assertNotIn(b"committing", self.store.read_bytes(lifecycle.AUTH))

    def test_the_commit_is_marked_before_head_moves(self):
        pid = self.domain()
        seen = []
        real = sil.commit_generation

        def spy(store, **kw):
            seen.append(self.auth()["proposals"][pid].get("committing"))
            return real(store, **kw)

        with mock.patch.object(proposals.sil, "commit_generation", spy):
            proposals.commit(self.S, pid)
        self.assertEqual(seen, [{"entry": 1, "grant": None}])


class WaitingTests(Base):
    def snapshot(self):
        return (
            self.store.read_bytes(lifecycle.AUTH),
            self.store.read_bytes(sil.LOG),
        )

    def test_waiting_lists_what_the_endure_phase_would_commit(self):
        approved = self.domain("a.example.com")
        self.domain("b.example.com", approve=False)
        before = self.snapshot()
        self.assertEqual(proposals.waiting(self.store), [approved])
        self.assertEqual(self.snapshot(), before)

    def test_waiting_ignores_a_window_past_its_expiry(self):
        operator.grant(self.S, expiry="+1s", budget=3, scope="rules")
        self.domain(approve=False)
        self.assertEqual(len(proposals.waiting(self.store)), 1)
        hooks.advance_clock(self.S, 5)
        before = self.snapshot()
        self.assertEqual(proposals.waiting(self.store), [])
        self.assertEqual(self.snapshot(), before)
        (window,) = self.auth()["grants"]
        self.assertEqual(window["state"], "open")

    def test_waiting_ignores_an_exhausted_window(self):
        operator.grant(self.S, expiry="+1h", budget=1, scope="rules")
        self.domain(approve=False)
        auth = self.auth()
        auth["grants"][0]["used"] = 1
        proposals.write_auth(self.store, auth)
        before = self.snapshot()
        self.assertEqual(proposals.waiting(self.store), [])
        self.assertEqual(self.snapshot(), before)


class RolloverTests(Base):
    def test_a_rollover_runs_endure_and_integrity_and_starts_again(self):
        pid = self.domain()
        before = self.head()
        out = lifecycle.rollover(self.S)
        (close,) = self.log("session-close")
        self.assertEqual(close["mode"], "rollover")
        (begin,) = self.log("closure-begin")
        self.assertEqual(begin["mode"], "rollover")
        (done,) = self.log("endure-complete")
        self.assertEqual(done["committed"], [pid])
        (complete,) = self.log("closure-complete")
        self.assertEqual(complete["phases"], ["endure", "integrity"])
        self.assertEqual(complete["mode"], "rollover")
        self.assertEqual(self.head(), before + 1)
        self.assertEqual(out["endure"]["committed"][0]["proposal"], pid)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertIsNone(self.sessions()["closing"])
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        (gate,) = [g for g in res.gates if g["gate"] == "crash-recovery"]
        self.assertEqual(gate["outcome"], "pass")
        (opened,) = [
            r
            for r in mil.session_records(self.store, "s-2")
            if r["kind"] == "session-open"
        ]
        self.assertEqual(opened["continues"], "s-1")


class CrashTests(Base):
    def crash_after_head(self):
        real = sil.commit_generation

        def crash(*args, **kwargs):
            real(*args, **kwargs)
            raise RuntimeError("crash after HEAD")

        return mock.patch.object(proposals.sil, "commit_generation", crash)

    def test_a_crash_after_head_is_finished_at_the_next_start(self):
        pid = self.domain()
        before = self.head()
        with self.crash_after_head():
            with self.assertRaises(RuntimeError):
                lifecycle.stop(self.S)
        self.assertEqual(self.head(), before + 1)
        self.assertEqual(
            self.auth()["proposals"][pid]["committing"], {"entry": 1, "grant": None}
        )
        self.assertEqual(self.sessions()["closing"]["session"], "s-1")
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        (gate,) = [g for g in res.gates if g["gate"] == "crash-recovery"]
        self.assertEqual(gate["outcome"], "recovered")
        (recovered,) = self.log("commit-recovered")
        self.assertEqual(recovered["proposal"], pid)
        self.assertEqual(recovered["entry"], before + 1)
        self.assertEqual(recovered["rule"], "OC-004(b)")
        auth = self.auth()
        self.assertNotIn(pid, auth["proposals"])
        self.assertNotIn(pid, auth["approvals"])
        self.assertEqual(self.head(), before + 1)
        self.assertEqual(len(self.log("commit")), 1)
        (complete,) = self.log("closure-complete")
        self.assertEqual(complete["session"], "s-1")
        self.assertEqual(self.log("endure-complete"), [])
        self.assertIsNone(self.sessions()["closing"])

    def test_a_crash_after_head_spends_the_window(self):
        operator.grant(self.S, expiry="+1h", budget=1, scope="rules")
        pid = self.domain(approve=False)
        with self.crash_after_head():
            with self.assertRaises(RuntimeError):
                lifecycle.stop(self.S)
        mark = self.auth()["proposals"][pid]["committing"]
        self.assertIsNotNone(mark["grant"])
        lifecycle.start(self.S)
        (window,) = self.auth()["grants"]
        self.assertEqual((window["used"], window["state"]), (1, "closed"))
        self.assertEqual(len(self.log("grant-closed")), 1)
        self.assertEqual(len(self.log("commit-recovered")), 1)

    def test_a_crash_before_head_clears_the_mark(self):
        pid = self.skill()
        before = self.head()
        hooks.arm_interrupt("chain-entry")
        try:
            with self.assertRaises(hooks.Interrupted):
                proposals.commit(self.S, pid)
        finally:
            hooks.disarm_interrupt()
        self.assertIn("committing", self.auth()["proposals"][pid])
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        (gate,) = [g for g in res.gates if g["gate"] == "crash-recovery"]
        self.assertEqual(gate["outcome"], "recovered")
        self.assertEqual(self.log("commit-recovered"), [])
        self.assertEqual(self.head(), before)
        auth = self.auth()
        self.assertNotIn("committing", auth["proposals"][pid])
        self.assertIn(pid, auth["approvals"])
        lifecycle.stop(self.S)
        self.assertEqual(self.head(), before + 1)
        self.assertEqual(len(self.log("commit")), 1)
        (done,) = self.log("endure-complete")
        self.assertEqual(done["committed"], [pid])

    def test_a_crash_in_integrity_resumes_at_the_phase_not_done(self):
        pid = self.domain()
        before = self.head()
        with mock.patch.object(
            lifecycle.sil, "write_log_checkpoint", side_effect=OSError("crash")
        ):
            with self.assertRaises(OSError):
                lifecycle.stop(self.S)
        self.assertEqual(self.sessions()["closing"]["done"], ["sleep", "endure"])
        self.assertEqual(self.head(), before + 1)
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        (done,) = self.log("endure-complete")
        self.assertEqual(done["committed"], [pid])
        completes = self.log("closure-complete")
        self.assertEqual(len(completes), 2)
        self.assertEqual(completes[-1]["phases"], ["endure", "integrity"])
        self.assertEqual(self.checkpoint()["id"], completes[-1]["id"])
        self.assertEqual(self.head(), before + 1)
        self.assertIsNone(self.sessions()["closing"])
        self.assertEqual(len(self.log("commit")), 1)


class DecommissionTests(Base):
    def test_an_authorized_proposal_commits_before_the_terminal_entry(self):
        pid = self.domain()
        before = self.head()
        out = lifecycle.decommission(self.S, "archive")
        self.assertEqual(out["entry"], before + 2)
        self.assertEqual(
            self.store.read_json(chain.entry_relpath(before + 1))["kind"], "commit"
        )
        self.assertEqual(
            self.store.read_json(chain.entry_relpath(before + 2))["kind"],
            "decommission",
        )
        (done,) = self.log("endure-complete")
        self.assertEqual(done["committed"], [pid])
        self.assertEqual(done["session"], "s-1")
        self.assertNotIn(pid, self.auth()["proposals"])
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_nothing_authorized_leaves_decommission_as_it_was(self):
        self.domain(approve=False)
        before = self.head()
        out = lifecycle.decommission(self.S, "archive")
        self.assertEqual(out["entry"], before + 1)
        self.assertEqual(self.log("endure-complete"), [])


class SeedingTests(Base):
    def test_the_new_conversation_is_seeded_from_closure_complete(self):
        record = mil.save(
            self.S,
            caller="cpe",
            destination="episodic",
            content="release notes",
            supersedes=None,
        )["record"]
        payload = {
            "consolidation": "We planned the release.",
            "working_set": [record],
            "message": "Next: tag it.",
            "promotions": [],
        }
        operator.exit_conversation(self.S, payload)
        self.assertEqual(
            self.checkpoint()["id"], self.log("closure-complete")[-1]["id"]
        )
        lifecycle.start(self.S)
        (opened,) = [
            r
            for r in mil.session_records(self.store, "s-2")
            if r["kind"] == "session-open"
        ]
        self.assertEqual(opened["seeded_by"], mil.conversation_of(self.store, "s-1"))
        self.assertEqual(self.log("resumption-discarded"), [])
        (complete,) = self.log("closure-complete")
        self.assertEqual(complete["phases"], ["sleep", "integrity"])
        self.assertEqual(complete["closure"], self.log("sleep-complete")[0]["closure"])
