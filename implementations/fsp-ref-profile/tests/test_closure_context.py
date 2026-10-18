# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The closure's context is assembled without a turn when there is none (D98)."""

from __future__ import annotations

import json

from helpers import TempDirTest

from fsp import context, cycle, lifecycle, mil, model, sil
from fsp.store import Store

PAYLOAD = {
    "consolidation": "Nothing was said.",
    "working_set": [],
    "message": "Start fresh.",
    "promotions": [],
}


class ClosureContextTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)
        lifecycle.start(self.S)

    def asm(self, **kw):
        return context.assemble(
            self.store,
            lifecycle.live_session(self.S),
            num_ctx=8192,
            date="2026-10-15",
            **kw,
        )

    def test_without_a_turn_the_closure_context_is_the_system_message(self):
        out = self.asm(answering=False)
        self.assertEqual([m["role"] for m in out["messages"]], ["system"])
        self.assertEqual(out["dropped"]["turns"], [])
        with self.assertRaises(ValueError):
            self.asm()
        with self.assertRaises(ValueError):
            self.asm(answering=True)

    def test_with_turns_answering_makes_no_difference(self):
        mil.stimulate(self.S, "first")
        mil.stimulate(self.S, "second")
        mil.stimulate(self.S, "third")
        answering = self.asm(answering=True)
        closing = self.asm(answering=False)
        self.assertEqual(closing, answering)
        self.assertEqual(self.asm(), answering)
        self.assertGreater(len(closing["messages"]), 1)

    def test_emit_closure_works_with_no_stimulus(self):
        channel = model.FakeModel([json.dumps(PAYLOAD)])
        out = cycle.emit_closure(self.S, channel=channel, date="2026-10-15")
        self.assertEqual(out["payload"], PAYLOAD)
        (messages,) = channel.calls
        self.assertEqual([m["role"] for m in messages], ["system"])
        records = mil.session_records(self.store, "s-1")
        self.assertEqual(len([r for r in records if r["kind"] == "cycle"]), 1)
