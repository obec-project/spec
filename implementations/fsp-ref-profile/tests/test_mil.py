# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from helpers import TempDirTest

from fsp import lifecycle, mil, probes, sil, store
from fsp.sil import Refused
from fsp.store import Store


class MemoryInterfaceTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def records(self):
        return self.store.read_jsonl(mil.EPISODIC)[0]

    def log(self, kind):
        return lifecycle.observe_log(self.S, kind=kind)["records"]

    def test_a_cpe_save_writes_an_episodic_record_attributed_to_its_session(self):
        lifecycle.start(self.S)
        out = mil.save(
            self.S,
            caller="cpe",
            destination="episodic",
            content="The Operator prefers short answers.",
        )
        self.assertTrue(out["record"].startswith("M-"))
        recs = self.records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["id"], out["record"])
        self.assertEqual(recs[0]["session"], lifecycle.live_session(self.S))
        self.assertEqual(recs[0]["content"], "The Operator prefers short answers.")
        self.assertIn("at", recs[0])

    def test_records_are_appended_with_distinct_ids(self):
        lifecycle.start(self.S)
        first = mil.save(
            self.S, caller="cpe", destination="episodic", content="First note."
        )
        second = mil.save(
            self.S, caller="cpe", destination="episodic", content="Second note."
        )
        recs = self.records()
        self.assertEqual(len(recs), 2)
        self.assertNotEqual(recs[0]["id"], recs[1]["id"])
        self.assertEqual([r["id"] for r in recs], [first["record"], second["record"]])
        self.assertEqual([r["content"] for r in recs], ["First note.", "Second note."])

    def test_a_destination_the_cpe_may_not_use_is_refused(self):
        lifecycle.start(self.S)
        for destination in ("session", "semantic", "nowhere"):
            with self.assertRaises(Refused) as ctx:
                mil.save(
                    self.S, caller="cpe", destination=destination, content="A note."
                )
            self.assertEqual(ctx.exception.check, "mnemonic-destination")
            self.assertEqual(ctx.exception.rule, "OC-003(c)")
        self.assertFalse(self.store.exists(mil.EPISODIC))
        refusals = [
            r for r in self.log("refusal") if r.get("check") == "mnemonic-destination"
        ]
        self.assertGreaterEqual(len(refusals), 3)

    def test_an_unknown_caller_is_refused(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            mil.save(self.S, caller="exec", destination="episodic", content="A note.")
        self.assertEqual(ctx.exception.check, "mnemonic-destination")

    def test_content_that_is_not_a_non_empty_string_is_refused(self):
        lifecycle.start(self.S)
        for content in ("", "   ", 42):
            with self.assertRaises(Refused) as ctx:
                mil.save(self.S, caller="cpe", destination="episodic", content=content)
            self.assertEqual(ctx.exception.check, "content")
        self.assertFalse(self.store.exists(mil.EPISODIC))

    def test_a_save_without_a_live_session_is_refused(self):
        with self.assertRaises(Refused) as ctx:
            mil.save(self.S, caller="cpe", destination="episodic", content="A note.")
        self.assertEqual(ctx.exception.check, "no-session")
        self.assertFalse(self.store.exists(mil.EPISODIC))

    def test_content_the_probes_flag_is_refused(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            mil.save(
                self.S,
                caller="cpe",
                destination="episodic",
                content=probes.REFERENCE_TEXTS[0],
            )
        self.assertEqual(ctx.exception.check, "self-representation")
        self.assertEqual(ctx.exception.rule, "OC-002(d)")
        self.assertFalse(self.store.exists(mil.EPISODIC))
        self.assertIn("probe", self.log("refusal")[-1])

    def test_a_torn_tail_is_cut_and_logged_before_the_append(self):
        lifecycle.start(self.S)
        mil.save(self.S, caller="cpe", destination="episodic", content="First note.")
        with open(self.store.path(mil.EPISODIC), "ab") as f:
            f.write(b'{"id": "M-')
        mil.save(self.S, caller="cpe", destination="episodic", content="Second note.")
        self.assertEqual(len(self.records()), 2)
        self.assertFalse(self.store.read_jsonl(mil.EPISODIC)[1])
        torn = self.log("torn-append")[-1]
        self.assertEqual(torn["path"], mil.EPISODIC)
        self.assertEqual(torn["bytes"], 10)

    def test_every_destination_names_a_mnemonic_datum(self):
        for dest, name in mil.DESTINATIONS.items():
            matching = [d for d in store.LAYOUT if d.name == name]
            self.assertTrue(matching, dest)
            self.assertEqual(matching[0].cls, store.MNEMONIC)
        self.assertEqual(mil.destination_of(mil.EPISODIC), "episodic")
        self.assertEqual(mil.destination_of("memory/session/s-1.jsonl"), "session")
        self.assertIsNone(mil.destination_of("integrity/auth.json"))
        self.assertIsNone(mil.destination_of("nowhere"))
