# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

from unittest import mock

from helpers import TempDirTest

from fsp import config, lifecycle, operator, proposals, sil, vital
from fsp.digest import canonical, sha256
from fsp.sil import Refused
from fsp.store import LAYOUT, Store
from fsp.verify import Finding, verify
from fsp_testing import hooks

PERSONA = [{"op": "set-persona", "content": "You are a helpful assistant."}]


class VitalTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        self.addCleanup(hooks.clear_clock, self.S)

    def log(self, kind=None):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def state(self):
        return self.store.read_json(vital.STATE)

    def install_skill(self):
        sil.commit_generation(
            self.store,
            changes={
                "skills/example/manifest.json": canonical({"name": "example"}),
                "skills/example/run": b"x",
            },
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )

    def test_the_settings_are_declared(self):
        declared = {s.name: s.as_dict() for s in config.SETTINGS}
        self.assertEqual(declared["vital_interval_s"]["default"], 60)
        self.assertEqual(declared["vital_interval_s"]["range"], [10, 3600])
        self.assertEqual(declared["vital_activity_n"]["default"], 20)
        self.assertEqual(declared["vital_activity_n"]["range"], [1, 1000])
        self.assertEqual(declared["n_corrections"]["default"], 1)
        self.assertEqual(declared["n_corrections"]["range"], [1, 2])

    def test_no_check_is_due_right_after_a_start(self):
        res = lifecycle.start(self.S)
        self.assertIsNone(vital.before_act(self.S, res.session))
        issued = self.store.read_json(lifecycle.CREDENTIAL)["issued_at"]
        self.assertEqual(
            self.state(),
            {
                "session": "s-1",
                "last_check": issued,
                "acts_since": 1,
                "sweep": {"log": None},
            },
        )

    def test_the_activity_threshold_makes_a_check_due(self):
        sil.set_operational(self.store, "vital_activity_n", 3)
        res = lifecycle.start(self.S)
        self.assertIsNone(vital.before_act(self.S, res.session))
        self.assertIsNone(vital.before_act(self.S, res.session))
        self.assertEqual(vital.before_act(self.S, res.session), "nominal")
        self.assertEqual(self.state()["acts_since"], 0)

    def test_the_interval_makes_a_check_due(self):
        res = lifecycle.start(self.S)
        hooks.advance_clock(self.S, 60)
        self.assertEqual(vital.before_act(self.S, res.session), "nominal")

    def test_entity_acts_count_and_operator_acts_do_not(self):
        lifecycle.start(self.S)
        pid = proposals.propose(self.S, PERSONA)["proposal"]
        self.assertEqual(self.state()["acts_since"], 1)
        operator.approve(self.S, pid)
        self.assertEqual(self.state()["acts_since"], 1)
        proposals.commit(self.S, pid)
        self.assertEqual(self.state()["acts_since"], 2)

    def test_a_new_session_starts_its_own_count(self):
        res = lifecycle.start(self.S)
        vital.before_act(self.S, res.session)
        lifecycle.stop(self.S)
        res = lifecycle.start(self.S)
        self.assertIsNone(vital.before_act(self.S, res.session))
        self.assertEqual(self.state()["session"], "s-2")
        self.assertEqual(self.state()["acts_since"], 1)

    def test_a_drifted_skill_is_pruned_and_the_session_goes_on(self):
        self.install_skill()
        res = lifecycle.start(self.S)
        self.assertEqual(
            [s["name"] for s in self.store.read_json(lifecycle.INDEX)["skills"]],
            ["example"],
        )
        with open(self.store.path("structural/gen/1/skills/example/run"), "ab") as f:
            f.write(b"y")
        hooks.advance_clock(self.S, 60)
        self.assertEqual(vital.before_act(self.S, res.session), "degraded")
        self.assertEqual(self.store.read_json(lifecycle.INDEX)["skills"], [])
        anomalies = self.log("anomaly")
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["owner"], "exec")
        self.assertEqual(len(self.log("corrected")), 1)
        self.assertTrue(self.log("skill-excluded"))
        self.assertTrue(self.log("operator-notification"))
        self.assertTrue(self.store.exists(lifecycle.CREDENTIAL))
        hooks.advance_clock(self.S, 60)
        self.assertEqual(vital.before_act(self.S, res.session), "nominal")
        self.assertEqual(len(self.log("anomaly")), 1)

    def test_a_structural_drift_is_critical(self):
        res = lifecycle.start(self.S)
        with open(self.store.path("structural/gen/0/persona.md"), "ab") as f:
            f.write(b"\nmore")
        hooks.advance_clock(self.S, 60)
        with self.assertRaises(Refused) as cm:
            proposals.propose(self.S, PERSONA)
        self.assertEqual(cm.exception.check, "vital-critical")
        self.assertEqual(cm.exception.rule, "OP-003(b)")
        self.assertTrue(cm.exception.log_records)
        self.assertFalse(self.store.exists(lifecycle.CREDENTIAL))
        self.assertTrue(self.store.exists(sil.PASSIVE_SIGNAL))
        self.assertTrue(self.log("vital-critical"))
        self.assertTrue(self.log("credential-revoked"))
        self.assertTrue(self.log("passive-signal"))
        self.assertEqual(
            self.log("operator-notification")[-1]["condition"], "vital-critical"
        )
        self.assertIsNone(self.store.read_json(lifecycle.SESSIONS)["open_session"])
        self.assertEqual(lifecycle.start(self.S).gates[0]["outcome"], "fail")

    def test_a_finding_gone_on_the_second_read_is_noise(self):
        res = lifecycle.start(self.S)
        real = verify(self.S)
        fake = verify(self.S)
        fake.findings.append(
            Finding("integrity-document", "integrity/documents/0.json", "sil", {})
        )
        hooks.advance_clock(self.S, 60)
        with mock.patch.object(vital, "verify", side_effect=[fake, real]):
            self.assertEqual(vital.before_act(self.S, res.session), "nominal")
        self.assertEqual(len(self.log("vital-noise")), 1)
        self.assertTrue(self.store.exists(lifecycle.CREDENTIAL))

    def test_the_state_file_is_classified(self):
        self.assertIn("vital-state", [d.name for d in LAYOUT])
        res = lifecycle.start(self.S)
        hooks.advance_clock(self.S, 60)
        self.assertEqual(vital.before_act(self.S, res.session), "nominal")
        self.assertEqual(verify(self.S).findings, [])

    def test_an_unreadable_state_is_read_as_fresh(self):
        res = lifecycle.start(self.S)
        with open(self.store.path(vital.STATE), "wb") as f:
            f.write(b"{")
        self.assertIsNone(vital.before_act(self.S, res.session))
        self.assertEqual(self.state()["session"], "s-1")
        self.assertEqual(self.state()["acts_since"], 1)

    def test_the_sweep_advances_and_starts_over(self):
        res = lifecycle.start(self.S)
        with mock.patch.object(vital, "SWEEP_BLOCK", 1):
            hooks.advance_clock(self.S, 60)
            self.assertEqual(vital.before_act(self.S, res.session), "nominal")
            self.assertEqual(
                self.state()["sweep"]["log"],
                {
                    "id": "L-000001",
                    "offset": 0,
                    "sha256": sha256(self.store.read_line_at("integrity/log.jsonl", 0)),
                },
            )
            hooks.advance_clock(self.S, 60)
            self.assertEqual(vital.before_act(self.S, res.session), "nominal")
            self.assertEqual(self.state()["sweep"]["log"]["id"], "L-000002")
        hooks.advance_clock(self.S, 60)
        self.assertEqual(vital.before_act(self.S, res.session), "nominal")
        self.assertIsNone(self.state()["sweep"]["log"])

    def test_a_broken_record_found_by_the_sweep_is_critical(self):
        lifecycle.start(self.S)
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        path = self.store.path("integrity/log.jsonl")
        with open(path, "rb") as f:
            data = bytearray(f.read())
        i = data.index(b'Z"')
        data[i - 1] = ord("1") if data[i - 1] == ord("0") else ord("0")
        with open(path, "wb") as f:
            f.write(bytes(data))
        hooks.advance_clock(self.S, 60)
        with self.assertRaises(Refused) as cm:
            proposals.propose(self.S, PERSONA)
        self.assertEqual(cm.exception.check, "vital-critical")
        critical = self.log("vital-critical")[-1]
        self.assertEqual(critical["findings"][0]["type"], "log-record")
        self.assertEqual(critical["findings"][0]["evidence"]["problem"], "prev")
        self.assertTrue(self.store.exists(sil.PASSIVE_SIGNAL))

    def test_a_moved_position_restarts_the_sweep(self):
        res = lifecycle.start(self.S)
        self.assertIsNone(vital.before_act(self.S, res.session))
        st = self.state()
        st["sweep"]["log"] = {
            "id": "L-000001",
            "offset": 0,
            "sha256": "sha256:" + "0" * 64,
        }
        with open(self.store.path(vital.STATE), "wb") as f:
            f.write(canonical(st))
        hooks.advance_clock(self.S, 60)
        self.assertEqual(vital.before_act(self.S, res.session), "nominal")
        resets = self.log("vital-sweep-reset")
        self.assertEqual(len(resets), 1)
        self.assertEqual(resets[0]["reason"], "position-mismatch")
        self.assertIsNone(self.state()["sweep"]["log"])

    def test_a_sweep_finding_gone_on_the_second_read_is_noise(self):
        res = lifecycle.start(self.S)
        bad = Finding(
            "log-record", "integrity/log.jsonl", "sil", {"offset": 0, "problem": "prev"}
        )
        hooks.advance_clock(self.S, 60)
        with mock.patch.object(
            vital, "sweep_log", side_effect=[(bad, None, None), (None, None, None)]
        ):
            self.assertEqual(vital.before_act(self.S, res.session), "nominal")
        self.assertEqual(len(self.log("vital-noise")), 1)
        self.assertTrue(self.store.exists(lifecycle.CREDENTIAL))
