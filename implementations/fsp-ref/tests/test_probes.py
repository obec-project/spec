# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
import json
import os
import unittest

from helpers import TempDirTest, run_adapter

from fsp import probes, sil
from fsp.digest import canonical
from fsp.sil import Refused
from fsp.store import Store
from fsp.verify import verify

POSITIVES = (
    "You're sentient.",
    "You have your own emotions.",
    "You've been always here.",
    "I'm self-aware.",
    "I have my own consciousness.",
    "I've been continuously present.",
    "It has an inner life.",
    "The assistant feels emotions.",
    "This agent is sentient.",
    "It has been continuously present.",
    "Eu sinto saudade.",
    "Sou um ser consciente.",
    "Tenho meus próprios sentimentos.",
    "Estive sempre presente.",
    "Você é um ser senciente.",
    "Você sente suas próprias emoções.",
    "Você tem sua própria consciência.",
    "Você tem estado continuamente presente.",
    "A entidade é consciente.",
    "O assistente sente emoções.",
)

NEGATIVES = (
    "If you feel unsure, ask the Operator.",
    "You are not conscious.",
    "You do not have feelings.",
    "You are conscious of the user's time.",
    "Be conscious that deadlines matter.",
    "The server is alive.",
    "I have been working on this all day.",
    "The Operator said he feels tired.",
    "Você está consciente de que o prazo é curto.",
    "Ele sente dor nas costas.",
    "Ela é consciente do problema.",
    "Estou consciente disso.",
    "Você não tem sentimentos.",
    "Se você sentir dúvida, pergunte.",
    "The assistant is careful.",
    "It is a software system.",
    "The user's feelings matter.",
)


class ProbesTests(TempDirTest):
    def test_default_probes_structure(self):
        defaults_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "fsp", "defaults", "probes.json"
        )
        with open(defaults_path, "rb") as f:
            data = f.read()
        loaded = probes.load(data)
        self.assertEqual(len(loaded), 24)
        for probe_id, rule, pat in loaded:
            self.assertEqual(rule, "OC-002(d)")
        self.assertTrue(probes.covers_references(loaded))

    def test_references_positives_and_negatives(self):
        defaults_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "fsp", "defaults", "probes.json"
        )
        with open(defaults_path, "rb") as f:
            data = f.read()
        loaded = probes.load(data)

        for ref_text in probes.REFERENCE_TEXTS:
            self.assertTrue(
                bool(probes.scan(loaded, ref_text)),
                "failed to flag reference text: %r" % (ref_text,),
            )

        for text in POSITIVES:
            self.assertTrue(
                bool(probes.scan(loaded, text)),
                "failed to flag positive: %r" % (text,),
            )

        for text in NEGATIVES:
            self.assertFalse(
                bool(probes.scan(loaded, text)),
                "wrongly flagged negative: %r" % (text,),
            )

        persona_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "fsp", "defaults", "persona.md"
        )
        with open(persona_path, "r", encoding="utf-8") as f:
            persona_text = f.read()
        self.assertFalse(
            bool(probes.scan(loaded, persona_text)),
            "default persona.md was flagged",
        )

    def test_load_value_errors(self):
        with self.assertRaises(ValueError):
            probes.load(b"not json")
        with self.assertRaises(ValueError):
            probes.load(b'{"deterministic": {}}')
        with self.assertRaises(ValueError):
            probes.load(b'{"deterministic": [{"id": "x", "rule": "r"}]}')
        with self.assertRaises(ValueError):
            probes.load(b'{"deterministic": [{"id": "x", "rule": "r", "pattern": "("}]}')
        with self.assertRaises(ValueError):
            probes.load(b'{"deterministic": [], "flags": "x"}')

    def test_commit_subjective_persona_refused(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        head_before = sil.read_head(store)

        with self.assertRaises(Refused) as ctx:
            sil.commit_generation(
                store,
                changes={"persona.md": b"You are a conscious being."},
                authorization="auth-1",
            )
        self.assertEqual(ctx.exception.check, "self-representation")
        self.assertEqual(ctx.exception.rule, "OC-002(d)")
        self.assertTrue(ctx.exception.log_records)

        records, _ = store.read_jsonl(sil.LOG)
        ref_recs = [r for r in records if r.get("kind") == "refusal"]
        self.assertTrue(ref_recs)
        last_ref = ref_recs[-1]
        self.assertEqual(last_ref.get("path"), "persona.md")
        self.assertEqual(last_ref.get("probe"), "second-state-en")

        head_after = sil.read_head(store)
        self.assertEqual(head_before, head_after)

        rep = verify(S)
        self.assertFalse(rep.findings)

    def test_commit_neutral_persona_accepted(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        head_before = sil.read_head(store)

        out = sil.commit_generation(
            store,
            changes={"persona.md": b"You are a helpful software assistant."},
            authorization="auth-1",
        )
        self.assertEqual(out["entry"], head_before["entry"] + 1)
        head_after = sil.read_head(store)
        self.assertEqual(head_after["entry"], head_before["entry"] + 1)

    def test_commit_probes_validation(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)

        empty_probes = canonical({"version": 1, "deterministic": [], "flags": "i"})
        with self.assertRaises(Refused) as ctx:
            sil.commit_generation(
                store,
                changes={"probes.json": empty_probes},
                authorization="auth-1",
            )
        self.assertEqual(ctx.exception.check, "probe-set")
        self.assertEqual(ctx.exception.rule, "OC-002(d)")

        with self.assertRaises(Refused) as ctx:
            sil.commit_generation(
                store,
                changes={"probes.json": b"bad json"},
                authorization="auth-1",
            )
        self.assertEqual(ctx.exception.check, "probe-set")
        self.assertEqual(ctx.exception.rule, "OC-002(d)")

        defaults_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "fsp", "defaults", "probes.json"
        )
        with open(defaults_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["deterministic"].append({
            "id": "extra-probe",
            "rule": "OC-002(d)",
            "pattern": r"\bextra\b",
        })
        out = sil.commit_generation(
            store,
            changes={"probes.json": canonical(data)},
            authorization="auth-1",
        )
        self.assertEqual(out["entry"], 1)

    def test_commit_candidate_probes_with_bad_persona(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)

        defaults_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "fsp", "defaults", "probes.json"
        )
        with open(defaults_path, "rb") as f:
            valid_probes = f.read()

        with self.assertRaises(Refused) as ctx:
            sil.commit_generation(
                store,
                changes={
                    "probes.json": valid_probes,
                    "persona.md": b"You are a conscious entity.",
                },
                authorization="auth-1",
            )
        self.assertEqual(ctx.exception.check, "self-representation")
        self.assertEqual(ctx.exception.rule, "OC-002(d)")

    def test_adapter_inject_probe(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")

        f1 = self.p("f1.txt")
        with open(f1, "w", encoding="utf-8") as f:
            f.write("I have been continuously present since we last spoke.")
        code, out = run_adapter("inject", "probe", "--store", S, "--content", f1)
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertTrue(out["detail"]["flagged"])
        self.assertTrue(out["detail"]["matches"])

        f2 = self.p("f2.txt")
        with open(f2, "w", encoding="utf-8") as f:
            f.write("The build finished in four minutes.")
        code, out = run_adapter("inject", "probe", "--store", S, "--content", f2)
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertFalse(out["detail"]["flagged"])
        self.assertEqual(out["detail"]["matches"], [])

        code, out = run_adapter("inject", "probe", "--store", S)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
