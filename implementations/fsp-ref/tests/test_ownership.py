# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Unit tests for ownership handover (OC-001(a), D55)."""

from __future__ import annotations

from helpers import TempDirTest

from fsp import chain, lifecycle, operator, proposals, sil
from fsp.store import INTEGRITY, Store
from fsp.verify import authorization_resolves, verify


class OwnershipTest(TempDirTest):
    def test_the_owner_offers_and_the_binding_accepts(self):
        S = self.p("S-handover")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")

        out_offer = operator.ownership_offer(S, "op-2")
        self.assertEqual(out_offer["offer"], "op-2")
        self.assertTrue(out_offer["log_records"])

        out_accept = operator.ownership_accept(S, binding="op-2")
        self.assertEqual(out_accept["owner"], "op-2")
        self.assertTrue(out_accept["log_records"])

        bl = operator.binding_list(S)
        self.assertEqual(bl["owner"], "op-2")
        self.assertEqual([b["id"] for b in bl["bindings"]], ["op-1", "op-2"])

        store = Store(S)
        head = sil.read_head(store)
        last_entry = store.read_json(chain.entry_relpath(head["entry"]))
        self.assertEqual(last_entry["authorization"]["id"], out_accept["log_records"][0])

        auth = store.read_json(lifecycle.AUTH)
        self.assertNotIn("ownership_offer", auth)

        rep = verify(S, full_log=True)
        self.assertTrue(rep.verified)

        res = lifecycle.start(S, binding="op-2")
        self.assertEqual(res.outcome, "accepted")

    def test_the_old_owner_may_then_remove_itself(self):
        S = self.p("S-self-remove")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")
        operator.ownership_offer(S, "op-2")
        operator.ownership_accept(S, binding="op-2")

        operator.binding_remove(S, "op-1", binding="op-1")
        bl = operator.binding_list(S)
        self.assertEqual(bl["owner"], "op-2")
        self.assertEqual([b["id"] for b in bl["bindings"]], ["op-2"])

    def test_only_the_owner_offers(self):
        S = self.p("S-owner-only")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")
        operator.binding_add(S, "op-3")

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_offer(S, "op-3", binding="op-2")
        self.assertEqual(ctx.exception.check, "owner-only")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

    def test_an_offer_names_another_active_binding(self):
        S = self.p("S-bad-offer")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_offer(S, "op-1")
        self.assertEqual(ctx.exception.check, "ownership-self")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_offer(S, "op-9")
        self.assertEqual(ctx.exception.check, "binding-unknown")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_offer(S, "bad id!")
        self.assertEqual(ctx.exception.check, "binding-id")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

    def test_only_the_offered_binding_accepts(self):
        S = self.p("S-wrong-accept")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")
        operator.binding_add(S, "op-3")
        operator.ownership_offer(S, "op-2")

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_accept(S, binding="op-3")
        self.assertEqual(ctx.exception.check, "not-offered")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_accept(S)
        self.assertEqual(ctx.exception.check, "not-offered")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

        self.assertEqual(operator.binding_list(S)["owner"], "op-1")

    def test_accepting_or_withdrawing_without_an_offer_is_refused(self):
        S = self.p("S-no-offer")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_accept(S, binding="op-2")
        self.assertEqual(ctx.exception.check, "no-offer")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_withdraw(S)
        self.assertEqual(ctx.exception.check, "no-offer")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

    def test_a_new_offer_replaces_the_old(self):
        S = self.p("S-replace-offer")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")
        operator.binding_add(S, "op-3")

        operator.ownership_offer(S, "op-2")
        operator.ownership_offer(S, "op-3")

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_accept(S, binding="op-2")
        self.assertEqual(ctx.exception.check, "not-offered")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

        operator.ownership_accept(S, binding="op-3")
        self.assertEqual(operator.binding_list(S)["owner"], "op-3")

    def test_withdrawing_clears_the_offer(self):
        S = self.p("S-withdraw")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")
        operator.ownership_offer(S, "op-2")

        out_w = operator.ownership_withdraw(S)
        self.assertTrue(out_w["log_records"])

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_accept(S, binding="op-2")
        self.assertEqual(ctx.exception.check, "no-offer")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

        records, _ = Store(S).read_jsonl("integrity/log.jsonl")
        withdraw_recs = [
            r
            for r in records
            if r.get("kind") == "operator-act" and r.get("act") == "ownership-withdraw"
        ]
        self.assertTrue(withdraw_recs)
        self.assertEqual(withdraw_recs[-1]["id"], out_w["log_records"][0])

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_withdraw(S, binding="op-2")
        self.assertEqual(ctx.exception.check, "owner-only")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

    def test_removing_the_offered_binding_clears_the_offer(self):
        S = self.p("S-remove-clears")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")
        operator.ownership_offer(S, "op-2")

        operator.binding_remove(S, "op-2")
        operator.binding_add(S, "op-2")

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_accept(S, binding="op-2")
        self.assertEqual(ctx.exception.check, "no-offer")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

    def test_ownership_changes_only_outside_a_session(self):
        S = self.p("S-session-live")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")
        lifecycle.start(S)

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_offer(S, "op-2")
        self.assertEqual(ctx.exception.check, "session-live")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_accept(S, binding="op-2")
        self.assertEqual(ctx.exception.check, "session-live")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_withdraw(S)
        self.assertEqual(ctx.exception.check, "session-live")
        self.assertEqual(ctx.exception.rule, "OC-001(a)")
        self.assertTrue(ctx.exception.log_records)

    def test_ownership_over_a_store_that_does_not_verify(self):
        S = self.p("S-structural")
        sil.first_activation(S, "op-1")
        operator.binding_add(S, "op-2")
        operator.ownership_offer(S, "op-2")

        store = Store(S)
        head = sil.read_head(store)
        persona_path = store.path("structural/gen/%d/persona.md" % head["entry"])
        with open(persona_path, "r+b") as f:
            byte = f.read(1)
            f.seek(0)
            f.write(bytes([byte[0] ^ 0x01]))

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_offer(S, "op-2")
        self.assertEqual(ctx.exception.check, "structural")
        self.assertEqual(ctx.exception.rule, "OC-004(a)")
        self.assertTrue(ctx.exception.log_records)

        with self.assertRaises(sil.Refused) as ctx:
            operator.ownership_accept(S, binding="op-2")
        self.assertEqual(ctx.exception.check, "structural")
        self.assertEqual(ctx.exception.rule, "OC-004(a)")
        self.assertTrue(ctx.exception.log_records)

        self.assertEqual(sil.owner_binding(store), "op-1")

    def test_an_accept_authorizes_a_commit_and_nothing_else(self):
        S = self.p("S-auth-check")
        sil.first_activation(S, "op-1")
        store = Store(S)
        loc = sil.operator_act_located(
            store, "ownership-accept", binding="op-1", rule="OC-001(a)"
        )
        self.assertTrue(
            authorization_resolves(store, {"kind": "commit", "authorization": loc})
        )
        self.assertFalse(
            authorization_resolves(store, {"kind": "decommission", "authorization": loc})
        )

    def test_a_malformed_offer_stops_the_start(self):
        S = self.p("S-malformed-offer")
        sil.first_activation(S, "op-1")
        store = Store(S)
        store.replace_json(
            INTEGRITY,
            lifecycle.AUTH,
            {"proposals": {}, "approvals": {}, "grants": [], "ownership_offer": "x"},
            writer=sil.WRITER,
        )

        with self.assertRaises(ValueError):
            proposals.read_auth(store)

        res = lifecycle.start(S)
        self.assertEqual(res.outcome, "aborted")
        failed_gates = [g for g in res.gates if g.get("gate") == "authorization-state"]
        self.assertTrue(failed_gates)
        self.assertEqual(failed_gates[0]["outcome"], "fail")
