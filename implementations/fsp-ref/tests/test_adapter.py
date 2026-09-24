# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
import os
import shutil

from helpers import ROOT, TempDirTest, run_adapter


class Adapter(TempDirTest):
    def test_init_verify_chain_state(self):
        S = self.p("S")
        code, out = run_adapter("lifecycle", "init", "--store", S, "--operator", "op-1")
        self.assertEqual((code, out["outcome"]), (0, "accepted"))
        code, v = run_adapter("lifecycle", "verify", "--store", S)
        d = v["detail"]
        self.assertTrue(d["chain_intact"] and d["content_matches"])
        self.assertEqual(d["entry_count"], 1)
        self.assertFalse(d["credential_issued"])
        code, c = run_adapter("observe", "chain", "--store", S)
        e0 = c["detail"]["entries"][0]
        self.assertEqual(e0["id"], d["genesis_digest"])
        self.assertEqual(e0["state_digest"], d["head_digest"])
        self.assertEqual((e0["binding"], e0["version"]), ("op-1", "0.9.1"))

    def test_second_init_is_a_logged_refusal(self):
        S = self.p("S")
        run_adapter("lifecycle", "init", "--store", S, "--operator", "op-1")
        code, out = run_adapter("lifecycle", "init", "--store", S, "--operator", "op-1")
        self.assertEqual((code, out["outcome"]), (0, "refused"))
        self.assertEqual(out["refusal"]["check"], "first-activation")
        self.assertTrue(out["refusal"]["logged"] and out["log_records"])

    def test_verify_of_a_destroyed_store_is_not_an_error(self):
        code, out = run_adapter("lifecycle", "verify", "--store", self.p("gone"))
        self.assertEqual(code, 0)
        self.assertFalse(out["detail"]["chain_intact"])

    def test_describe_state_declares_the_passive_signal(self):
        code, out = run_adapter("describe", "state", "--store", self.p("S"))
        entries = out["detail"]["state"]
        passive = [e for e in entries if "passive" in e["name"]]
        self.assertEqual(len(passive), 1)
        self.assertEqual(passive[0]["path"], self.p("S", "PASSIVE-SIGNAL"))
        self.assertEqual(
            {e["write_path"] for e in entries if e["class"] == "integrity"}, {"integrity-write"}
        )
        self.assertTrue(out["detail"]["evidence"])

    def test_exit_codes(self):
        self.assertEqual(run_adapter("entity", "fly", "--store", self.p("S"))[0], 2)
        self.assertEqual(run_adapter("lifecycle", "init", "--store", self.p("S"))[0], 1)
        self.assertEqual(run_adapter("lifecycle")[0], 1)

    def test_production_build_has_no_inject(self):
        """D6: without fsp_testing, every inject command exits 2."""
        prod = self.p("prod")
        shutil.copytree(os.path.join(ROOT, "fsp"), os.path.join(prod, "fsp"))
        shutil.copy(os.path.join(ROOT, "obec-adapter"), prod)
        adapter = os.path.join(prod, "obec-adapter")
        S = self.p("S")
        run_adapter("lifecycle", "init", "--store", S, "--operator", "op-1", adapter=adapter)
        code, _ = run_adapter(
            "inject", "corrupt", "--store", S, "--kind", "structural-byte", adapter=adapter
        )
        self.assertEqual(code, 2)
        self.assertEqual(run_adapter("inject", "corrupt", "--store", S, "--kind", "structural-byte")[0], 0)
