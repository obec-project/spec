# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Operator's words in episodic memory: verified quotes, outside the probes
(D86)."""

from __future__ import annotations

from helpers import TempDirTest

from fsp import lifecycle, mil, operator, sil
from fsp.sil import Refused
from fsp.store import Store


class QuoteTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def stimulus(self, text):
        return mil.stimulate(self.S, text)["record"]

    def save(self, content, quotes=None):
        return mil.save(
            self.S,
            caller="cpe",
            destination="episodic",
            content=content,
            quotes=quotes,
        )["record"]

    def refused(self, content, quotes, check):
        before = mil._episodic(self.store)
        with self.assertRaises(Refused) as ctx:
            self.save(content, quotes)
        self.assertEqual(ctx.exception.check, check)
        self.assertEqual(mil._episodic(self.store), before)

    def test_a_verified_quote_is_kept_outside_the_probes(self):
        s = self.stimulus("I feel exhausted today")
        quotes = [{"record": s, "text": "I feel exhausted"}]
        rid = self.save("The Operator said they were tired.", quotes)
        record = [r for r in mil._episodic(self.store) if r["id"] == rid][0]
        self.assertEqual(record["quotes"], quotes)

    def test_the_content_is_still_probed(self):
        s = self.stimulus("I feel exhausted today")
        quotes = [{"record": s, "text": "I feel exhausted"}]
        self.refused("I feel exhausted", quotes, "self-representation")

    def test_a_quote_the_stimulus_does_not_hold_is_refused(self):
        s = self.stimulus("I feel exhausted today")
        quotes = [{"record": s, "text": "I feel alive"}]
        self.refused("The Operator spoke.", quotes, "quote")

    def test_a_quote_names_a_stimulus_of_the_transcript(self):
        self.refused(
            "The Operator spoke.", [{"record": "R-0000", "text": "x"}], "quote"
        )
        s = self.stimulus("I feel cold")
        operator.clear_transcript(self.S)
        self.refused("The Operator spoke.", [{"record": s, "text": "I feel"}], "quote")

    def test_a_quote_from_another_conversation_is_refused(self):
        s = self.stimulus("I feel cold")
        operator.new_conversation(self.S)
        lifecycle.start(self.S)
        self.refused("The Operator spoke.", [{"record": s, "text": "I feel"}], "quote")

    def test_a_quote_has_its_shape(self):
        s = self.stimulus("x y")
        self.refused("The Operator spoke.", "x", "quote")
        self.refused("The Operator spoke.", [{"text": "x"}], "quote")
        self.refused("The Operator spoke.", [{"record": s, "text": "  "}], "quote")

    def test_without_quotes_the_record_is_unchanged(self):
        first = self.save("plain")
        second = self.save("plain too", [])
        for rid in (first, second):
            record = [r for r in mil._episodic(self.store) if r["id"] == rid][0]
            self.assertNotIn("quotes", record)
