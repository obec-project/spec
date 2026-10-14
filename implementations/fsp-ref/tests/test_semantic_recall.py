# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Semantic memory read through its ledger: what is live, recall, what context
reads, and the Vital Check's report (D82)."""

from __future__ import annotations

import json
from unittest import mock

from helpers import TempDirTest

from fsp import lifecycle, mil, operator, sil, vital
from fsp.digest import canonical
from fsp.sil import Refused
from fsp.store import Store


class SemanticRecallTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def learn(self, slug, category="knowledge", content=None, supersedes=None):
        if content is None:
            content = "About " + slug + "."
        with self.store.write_lock():
            pid = mil.request_promotion(
                self.store,
                "s-1",
                slug=slug,
                category=category,
                content=content,
                supersedes=supersedes,
            )
        operator.approve_promotion(self.S, pid)
        with self.store.write_lock():
            return mil.promote(self.store, "s-1", pid)

    def rewrite(self, records):
        with open(self.store.path(mil.SEMANTIC), "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def tamper(self, sid, **fields):
        self.rewrite(
            [
                {**r, **fields} if r["id"] == sid else r
                for r in mil.semantic_records(self.store)
            ]
        )

    def ids(self, records):
        return [r["id"] for r in records]

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def commit_config(self, always_loaded):
        sil.commit_generation(
            self.store,
            changes={
                "config.json": canonical(
                    {"name": "entity", "always_loaded": always_loaded}
                )
            },
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )

    def test_a_promoted_record_is_live(self):
        sid = self.learn("tea")
        check = mil.semantic_check(self.store)
        self.assertEqual(check["findings"], [])
        self.assertEqual(self.ids(mil.semantic_live(check)), [sid])

    def test_recall_searches_slug_and_content(self):
        sid = self.learn("short answers", "guidance", "The Operator prefers brevity.")
        got = mil.recall(self.S, query="short brevity")
        self.assertIn(sid, self.ids(got["records"]))
        absent = mil.recall(self.S, query="absent")
        self.assertEqual(absent["records"], [])
        self.assertEqual(absent["withheld"], [])

    def test_a_diverging_record_is_withheld(self):
        sid = self.learn("tea")
        self.tamper(sid, content="About coffee.")
        check = mil.semantic_check(self.store)
        self.assertEqual(check["findings"], [{"type": "semantic-digest", "id": sid}])
        got = mil.recall(self.S, query="coffee")
        self.assertEqual(got["records"], [])
        self.assertEqual(got["withheld"], [sid])
        self.assertEqual(self.log("recall")[-1]["withheld"], [sid])

    def test_a_record_without_its_entry_is_withheld(self):
        with self.store.write_lock():
            pid = mil.request_promotion(
                self.store,
                "s-1",
                slug="tea",
                category="knowledge",
                content="About tea.",
            )
        operator.approve_promotion(self.S, pid)
        with mock.patch.object(
            sil, "semantic_ledger_append", side_effect=OSError("crash")
        ):
            with self.assertRaises(OSError):
                with self.store.write_lock():
                    mil.promote(self.store, "s-1", pid)
        (rec,) = mil.semantic_records(self.store)
        check = mil.semantic_check(self.store)
        self.assertEqual(
            check["findings"], [{"type": "semantic-unsealed", "id": rec["id"]}]
        )
        self.assertEqual(mil.semantic_live(check), [])

    def test_an_entry_without_its_record_is_found(self):
        sid = self.learn("tea")
        self.rewrite([])
        check = mil.semantic_check(self.store)
        self.assertEqual(check["findings"], [{"type": "semantic-missing", "id": sid}])

    def test_a_record_without_a_string_id_is_withheld(self):
        sid = self.learn("tea")
        (rec,) = mil.semantic_records(self.store)
        self.rewrite([rec, {**rec, "id": ["x"]}, {**rec, "id": None}])
        out = mil.recall(self.S, query="tea")
        self.assertEqual(self.ids(out["records"]), [sid])
        self.assertEqual(out["withheld"], [None])

    def test_a_retracted_record_leaves_recall(self):
        sid = self.learn("tea")
        operator.retract_semantic(self.S, sid)
        self.assertEqual(mil.recall(self.S, query="tea")["records"], [])
        with self.assertRaises(Refused) as ctx:
            mil.recall(self.S, lineage=sid)
        self.assertEqual(ctx.exception.check, "recall-scope")

    def test_a_superseded_record_stays_in_its_lineage(self):
        a = self.learn("tea")
        b = self.learn("tea, green", supersedes=a)
        self.assertEqual(self.ids(mil.recall(self.S, query="tea")["records"]), [b])
        self.assertEqual(self.ids(mil.recall(self.S, lineage=a)["records"]), [a, b])
        self.assertEqual(self.ids(mil.recall(self.S, lineage=b)["records"]), [a, b])

    def test_an_unknown_semantic_id_falls_to_the_episodic_path(self):
        with self.assertRaises(Refused) as ctx:
            mil.recall(self.S, lineage="S-0000")
        self.assertEqual(ctx.exception.check, "recall-scope")

    def test_always_loaded_and_the_index(self):
        k = self.learn("knowledge fact", "knowledge")
        o = self.learn("who the Operator is", "operator")
        p = self.learn("ongoing work", "project")
        r = self.learn("firm constraint", "rule")
        g = self.learn("how to work", "guidance")
        self.assertEqual(self.ids(mil.always_loaded(self.store)), [r, g, o])
        self.assertEqual(
            mil.semantic_index(self.store),
            [
                {"id": p, "slug": "ongoing work", "category": "project"},
                {"id": k, "slug": "knowledge fact", "category": "knowledge"},
            ],
        )

    def test_always_loaded_comes_from_the_head_config(self):
        self.commit_config(["project"])
        self.assertEqual(mil.always_loaded_categories(self.store), ["project"])

    def test_an_invalid_always_loaded_is_the_default(self):
        self.commit_config(["project", "project"])
        self.assertEqual(
            mil.always_loaded_categories(self.store), ["rule", "guidance", "operator"]
        )

    def test_the_vital_check_reports_a_finding_once(self):
        sil.set_operational(self.store, "vital_activity_n", 1)
        sid = self.learn("tea")
        self.tamper(sid, content="About coffee.")
        self.assertEqual(vital.before_act(self.S, "s-1"), "degraded")
        self.assertEqual(vital.before_act(self.S, "s-1"), "degraded")
        self.assertEqual(len(self.log("semantic-withheld")), 1)
        notices = [
            n
            for n in self.log("operator-notification")
            if n["condition"] == "semantic-withheld"
        ]
        self.assertEqual(len(notices), 1)
        self.assertEqual(
            self.store.read_json(vital.STATE)["sweep"]["semantic"],
            ["semantic-digest:" + sid],
        )

    def test_a_clean_memory_keeps_the_check_nominal(self):
        sil.set_operational(self.store, "vital_activity_n", 1)
        self.learn("tea")
        self.assertEqual(vital.before_act(self.S, "s-1"), "nominal")
        self.assertEqual(self.log("semantic-withheld"), [])
