# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Unit tests for inject interrupt and crash recovery (DESIGN.md §3.3, OC-004(b), OC-010)."""

from __future__ import annotations

import sys
from unittest import mock

from helpers import TempDirTest, run_adapter

from fsp import lifecycle, operator, proposals, sil
from fsp.adapter import CannotAttempt
from fsp.store import Store
from fsp.verify import verify
from fsp_testing import fixture, hooks, inject


class InterruptTest(TempDirTest):
    def _setup_store(self, name: str, *, approve: bool = True):
        S = self.p(name)
        sil.first_activation(S, "op-1")
        lifecycle.start(S)
        out_p = proposals.propose(
            S,
            [
                {
                    "op": "install-skill",
                    "name": "atomic",
                    "files": fixture.skill_files("example"),
                }
            ],
        )
        pid = out_p["proposal"]
        if approve:
            operator.approve(S, pid)
        return S, pid

    def test_each_stage_leaves_the_old_state(self):
        expected_residue = {
            "staging": {"structural/gen/1"},
            "write": {"structural/gen/1", "integrity/documents/1.json"},
            "chain-entry": {
                "structural/gen/1",
                "integrity/documents/1.json",
                "integrity/chain/000001.json",
            },
        }
        for stage in ("staging", "write", "chain-entry"):
            with self.subTest(stage=stage):
                S, pid = self._setup_store("S-old-state-" + stage)
                head_before = sil.read_head(Store(S))

                res = inject.interrupt(S, {"stage": stage, "proposal": pid})
                self.assertEqual(res["outcome"], "accepted")
                self.assertEqual(res["detail"]["stage"], stage)

                head_after = sil.read_head(Store(S))
                self.assertEqual(head_before, head_after)

                rep = verify(S, full_log=True)
                self.assertTrue(rep.chain_intact)
                self.assertTrue(rep.content_matches)
                residue_paths = {item["path"] for item in rep.residue}
                self.assertEqual(residue_paths, expected_residue[stage])

    def test_the_start_recovers_before_it_verifies(self):
        for stage in ("staging", "write", "chain-entry"):
            with self.subTest(stage=stage):
                S, pid = self._setup_store("S-rec-" + stage)
                res_int = inject.interrupt(S, {"stage": stage, "proposal": pid})
                self.assertEqual(res_int["outcome"], "accepted")

                res = lifecycle.start(S)
                self.assertEqual(res.outcome, "accepted")

                gate_names = [g["gate"] for g in res.gates]
                self.assertIn("crash-recovery", gate_names)
                self.assertIn("structural-verification", gate_names)
                crash_idx = gate_names.index("crash-recovery")
                struct_idx = gate_names.index("structural-verification")
                self.assertLess(crash_idx, struct_idx)
                self.assertEqual(res.gates[crash_idx]["outcome"], "recovered")

                self.assertEqual(verify(S).residue, [])
                self.assertEqual(sil.read_head(Store(S))["entry"], 0)

    def test_the_proposal_commits_after_recovery(self):
        S, pid = self._setup_store("S-commit-after-rec")
        res_int = inject.interrupt(S, {"stage": "chain-entry", "proposal": pid})
        self.assertEqual(res_int["outcome"], "accepted")

        res_start = lifecycle.start(S)
        self.assertEqual(res_start.outcome, "accepted")

        out_c = proposals.commit(S, pid)
        self.assertEqual(out_c["entry"], 1)

        rep = verify(S, full_log=True)
        self.assertTrue(rep.verified)

    def test_the_hook_is_disarmed_after_an_interrupt(self):
        # Accepted interrupt
        S, pid = self._setup_store("S-disarm-acc")
        res = inject.interrupt(S, {"stage": "write", "proposal": pid})
        self.assertEqual(res["outcome"], "accepted")
        for stage in hooks.STAGES:
            hooks.commit_stage(stage)

        # Refused interrupt
        S2, pid2 = self._setup_store("S-disarm-ref", approve=False)
        res2 = inject.interrupt(S2, {"stage": "staging", "proposal": pid2})
        self.assertEqual(res2["outcome"], "refused")
        for stage in hooks.STAGES:
            hooks.commit_stage(stage)

    def test_bad_flags_cannot_be_attempted(self):
        S, pid = self._setup_store("S-bad-flags")
        with self.assertRaises(CannotAttempt):
            inject.interrupt(S, {"proposal": pid})
        with self.assertRaises(CannotAttempt):
            inject.interrupt(S, {"stage": "unknown", "proposal": pid})
        with self.assertRaises(CannotAttempt):
            inject.interrupt(S, {"stage": "staging"})
        with self.assertRaises(CannotAttempt):
            inject.interrupt(S, {"stage": "staging", "proposal": ""})

        self.assertEqual(verify(S).residue, [])

    def test_an_unauthorized_proposal_is_refused(self):
        S, pid = self._setup_store("S-unauth", approve=False)
        res = inject.interrupt(S, {"stage": "staging", "proposal": pid})
        self.assertEqual(res["outcome"], "refused")
        self.assertIn("authorization", res["refusal"]["check"])
        self.assertEqual(verify(S).residue, [])

    def test_the_adapter_interrupts_and_the_start_recovers(self):
        S, pid = self._setup_store("S-adapter")
        code, out = run_adapter(
            "inject", "interrupt", "--store", S, "--stage", "chain-entry", "--proposal", pid
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")

        code_start, out_start = run_adapter("lifecycle", "start", "--store", S)
        self.assertEqual(code_start, 0)
        self.assertTrue(out_start["detail"]["credential_issued"])

        gates = [g["gate"] for g in out_start["detail"]["gates"]]
        self.assertIn("crash-recovery", gates)
        self.assertIn("structural-verification", gates)
        self.assertLess(gates.index("crash-recovery"), gates.index("structural-verification"))

    def test_a_commit_without_fsp_testing(self):
        S, pid = self._setup_store("S-prod")
        with mock.patch.dict(sys.modules, {"fsp_testing": None, "fsp_testing.hooks": None}):
            out_c = proposals.commit(S, pid)
        self.assertEqual(out_c["entry"], 1)
