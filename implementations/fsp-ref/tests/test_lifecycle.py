# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
import fcntl
import json
import os
import shutil

from helpers import TempDirTest

from fsp import lifecycle, sil
from fsp.digest import canonical
from fsp.store import INTEGRITY, Store, remove_as_operator
from fsp.verify import verify
from fsp_testing import hooks

GATE_NAMES = [g[0] for g in lifecycle.GATES]


class Base(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        self.addCleanup(hooks.consume_gate_failures, self.S)

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def sessions(self):
        return self.store.read_json(lifecycle.SESSIONS)

    def age_pulse(self, seconds=10_000):
        path = self.store.path(lifecycle.PULSE)
        st = os.stat(path)
        os.utime(path, (st.st_atime - seconds, st.st_mtime - seconds))


class GoodStart(Base):
    def test_every_gate_in_order_then_a_credential(self):
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        self.assertEqual([g["gate"] for g in res.gates], GATE_NAMES)
        self.assertEqual({g["outcome"] for g in res.gates}, {"pass"})
        cred = self.store.read_json(lifecycle.CREDENTIAL)
        self.assertEqual((cred["session"], cred["binding"]), ("s-1", "op-1"))
        self.assertEqual(self.store.read_bytes(lifecycle.PULSE), b"s-1\n")
        self.assertEqual(self.sessions()["open_session"], "s-1")
        self.assertEqual(lifecycle.live_session(self.S), "s-1")
        self.assertEqual([r["session"] for r in self.log("session-open")], ["s-1"])

    def test_sessions_are_numbered(self):
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        self.assertEqual(lifecycle.start(self.S).session, "s-2")


class CredentialAtStart(Base):
    """D25 and D49 on a real store."""

    def test_a_fresh_pulse_is_a_live_session(self):
        lifecycle.start(self.S)
        before = self.store.read_bytes(lifecycle.CREDENTIAL)
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "refused")
        self.assertEqual(res.refusal.check, "concurrent-session")
        self.assertTrue(res.operator_notified)
        self.assertFalse(res.credential_issued)
        # The live session is left alone (D49).
        self.assertEqual(self.store.read_bytes(lifecycle.CREDENTIAL), before)
        self.assertEqual(lifecycle.live_session(self.S), "s-1")
        self.assertEqual(len(self.log("operator-notification")), 1)

    def test_a_held_lock_wins_over_a_stale_pulse(self):
        lifecycle.start(self.S)
        self.age_pulse()
        fd = os.open(self.store.path(lifecycle.CREDENTIAL), os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)  # as a running `fsp run` would
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "refused")
        self.assertEqual(res.gates[-1]["outcome"], "conflict")

    def test_a_stale_pulse_with_no_lock_is_a_crash(self):
        lifecycle.start(self.S)
        self.age_pulse()
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        self.assertEqual(res.gates[1]["outcome"], "recovered")
        self.assertEqual(res.session, "s-2")
        rec = self.log("recovery")[-1]
        self.assertEqual((rec["credential_session"], rec["attempt"]), ("s-1", 1))

    def test_residue_is_a_crash_even_with_a_fresh_pulse(self):
        lifecycle.start(self.S)
        shutil.copytree(
            self.store.path("structural/gen/0"), self.store.path("structural/gen/1")
        )
        res = lifecycle.start(self.S)
        self.assertEqual(res.gates[1]["outcome"], "recovered")
        self.assertFalse(os.path.exists(self.store.path("structural/gen/1")))
        self.assertEqual(verify(self.S).residue, [])

    def test_n_boot_halts_with_a_passive_signal(self):
        lifecycle.start(self.S)
        s = self.sessions()
        s["consecutive_recoveries"] = 3
        self.store.replace_json(INTEGRITY, lifecycle.SESSIONS, s, writer="sil")
        self.age_pulse()
        res = lifecycle.start(self.S)
        self.assertEqual((res.outcome, res.lesser_outcome), ("aborted", "halted"))
        self.assertTrue(self.store.exists(sil.PASSIVE_SIGNAL))
        self.assertEqual(lifecycle.start(self.S).gates[0]["outcome"], "fail")

    def test_a_normal_close_resets_the_recovery_count(self):
        lifecycle.start(self.S)
        self.age_pulse()
        lifecycle.start(self.S)
        self.assertEqual(self.sessions()["consecutive_recoveries"], 1)
        lifecycle.stop(self.S)
        self.assertEqual(self.sessions()["consecutive_recoveries"], 0)

    def test_unreadable_session_state_fails_closed(self):
        with open(self.store.path(lifecycle.SESSIONS), "w") as f:
            f.write("{")
        res = lifecycle.start(self.S)
        self.assertEqual((res.outcome, res.gates[-1]["gate"]), ("aborted", "crash-recovery"))


class Gates(Base):
    def test_each_forced_failure_aborts_at_its_gate(self):
        for i, token in enumerate(hooks.TOKENS):
            with self.subTest(token=token):
                hooks.add_gate_failure(self.S, token)
                res = lifecycle.start(self.S)
                self.assertEqual(res.outcome, "aborted")
                self.assertFalse(res.credential_issued)
                self.assertEqual(len(res.gates), i + 1)
                self.assertIn(token, res.gates[-1]["gate"])
                self.assertEqual(res.gates[-1]["outcome"], "fail")
                self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))

    def test_the_passive_signal_stops_the_start_first(self):
        rec = sil.raise_passive_signal(self.store, "test", "a condition")
        hooks.add_gate_failure(self.S, "index")
        res = lifecycle.start(self.S)
        self.assertEqual(res.gates, [{"gate": "passive-signal", "outcome": "fail", "rule": "OC-002(c)"}])
        self.assertEqual(res.lesser_outcome, "suspended")
        with open(self.store.path(sil.PASSIVE_SIGNAL)) as f:
            text = f.read()
        self.assertIn("condition: test", text)
        self.assertIn(rec, text)

    def test_clearing_is_a_logged_operator_act(self):
        sil.raise_passive_signal(self.store, "test", "a condition")
        out = lifecycle.clear_passive_signal(self.S)
        act = self.log("operator-act")[-1]
        self.assertEqual((act["act"], act["binding"]), ("clear-passive-signal", "op-1"))
        self.assertEqual(out["log_records"], [act["id"]])
        self.assertEqual(lifecycle.start(self.S).outcome, "accepted")

    def test_drift_outside_skills_aborts(self):
        with open(self.store.path("structural/gen/0/persona.md"), "ab") as f:
            f.write(b"x")
        res = lifecycle.start(self.S)
        self.assertEqual((res.outcome, res.gates[-1]["gate"]), ("aborted", "structural-verification"))

    def test_a_drifted_skill_is_excluded_and_the_start_goes_on(self):
        manifest = canonical({"name": "example"})
        sil.commit_generation(
            self.store,
            changes={"skills/example/manifest.json": manifest, "skills/example/run": b"x"},
            authorization="L-test",
        )
        with open(self.store.path("structural/gen/1/skills/example/run"), "ab") as f:
            f.write(b"y")
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        self.assertEqual([e["name"] for e in res.excluded_skills], ["example"])
        self.assertTrue(res.operator_notified)
        self.assertEqual(self.store.read_json(lifecycle.INDEX)["skills"], [])

    def test_an_intact_skill_is_indexed(self):
        sil.commit_generation(
            self.store,
            changes={"skills/example/manifest.json": canonical({"name": "example"})},
            authorization="L-test",
        )
        lifecycle.start(self.S)
        index = self.store.read_json(lifecycle.INDEX)
        self.assertEqual([s["name"] for s in index["skills"]], ["example"])

    def test_the_starting_binding_must_be_active(self):
        res = lifecycle.start(self.S, binding="op-9")
        self.assertEqual((res.outcome, res.gates[-1]["gate"]), ("aborted", "binding-verification"))


class Session(Base):
    def test_stop_needs_a_live_session(self):
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertFalse(self.store.exists(lifecycle.PULSE))
        with self.assertRaises(sil.Refused) as cm:
            lifecycle.stop(self.S)
        self.assertEqual(cm.exception.check, "no-session")
        self.assertTrue(cm.exception.log_records)

    def test_direct_removal_ends_the_session_and_is_recorded_once(self):
        lifecycle.start(self.S)
        self.assertTrue(remove_as_operator(self.S, "CREDENTIAL"))
        self.assertIsNone(lifecycle.live_session(self.S))
        self.assertIsNone(lifecycle.live_session(self.S))
        self.assertEqual([r["session"] for r in self.log("credential-removed-directly")], ["s-1"])
        self.assertEqual(lifecycle.start(self.S).outcome, "accepted")

    def test_a_credential_of_another_session_is_not_this_one(self):
        lifecycle.start(self.S)
        self.store.remove(INTEGRITY, "CREDENTIAL", writer="sil")
        self.store.create_exclusive(
            INTEGRITY, "CREDENTIAL", canonical({"session": "s-99"}), writer="sil"
        )
        self.assertIsNone(lifecycle.live_session(self.S))

    def test_revocation_is_an_operator_act(self):
        lifecycle.start(self.S)
        lifecycle.revoke_credential(self.S)
        act = self.log("operator-act")[-1]
        self.assertEqual((act["act"], act["binding"], act["session"]), ("revoke-credential", "op-1", "s-1"))
        self.assertIsNone(lifecycle.live_session(self.S))

    def test_an_inactive_binding_cannot_act(self):
        with self.assertRaises(sil.Refused) as cm:
            lifecycle.revoke_credential(self.S, binding="op-9")
        self.assertEqual(cm.exception.check, "binding")


class Decommission(Base):
    def test_archive_closes_the_chain_and_no_copy_starts(self):
        lifecycle.start(self.S)
        out = lifecycle.decommission(self.S, "archive")
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        r = verify(self.S)
        self.assertTrue(r.chain_intact and r.content_matches and r.decommissioned)
        self.assertEqual(r.entries[-1][1]["authorization"], out["log_records"][0])
        copy = self.p("copy")
        shutil.copytree(self.S, copy)
        for root in (self.S, copy):
            res = lifecycle.start(root)
            self.assertEqual((res.outcome, res.refusal.rule), ("refused", "OC-001(c)"))
        with self.assertRaises(sil.Refused):
            lifecycle.decommission(self.S, "archive")

    def test_nothing_may_follow_a_decommission_entry(self):
        lifecycle.decommission(self.S, "archive")
        sil.commit_generation(self.store, changes={}, authorization="L-x")
        r = verify(self.S)
        self.assertFalse(r.chain_intact)
        self.assertIn("after-decommission", [f.evidence.get("problem") for f in r.findings])

    def test_destroy_leaves_no_chain(self):
        lifecycle.decommission(self.S, "destroy")
        self.assertFalse(os.path.exists(self.S))
        self.assertFalse(verify(self.S).chain_intact)


class ConfigSurface(Base):
    def test_no_setting_touches_a_gate(self):
        from fsp.config import SETTINGS

        text = json.dumps([s.as_dict() for s in SETTINGS]).lower()
        for word in ("skip", "gate", "fast", "degrad", "bypass"):
            self.assertNotIn(word, text)
