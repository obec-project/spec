# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Unit tests for write guards and authorization checks (D45, D61)."""

from datetime import datetime, timezone

from helpers import TempDirTest

from fsp import chain, lifecycle, operator, proposals, sil
from fsp.digest import sha256
from fsp.store import Store
from fsp.verify import verify

FRAGMENT = b'{"id":"L-0000'
FAKE_AUTH = {"id": "L-999999", "sha256": "sha256:" + "0" * 64, "offset": 0}


def write_fragment(store):
    with open(store.path("integrity/log.jsonl"), "ab") as f:
        f.write(FRAGMENT)


class WriteGuardsTest(TempDirTest):
    def test_sil_log_append_auto_heals_torn_tail(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)

        log_path = store.path("integrity/log.jsonl")
        with open(log_path, "rb") as f:
            clean_content = f.read()
        fragment = b'{"id":"L-000099","truncated":true'
        with open(log_path, "ab") as f:
            f.write(fragment)

        new_loc = sil.log_append_located(store, "pulse", session="s-1")

        records, truncated = store.read_jsonl("integrity/log.jsonl")
        self.assertFalse(truncated)
        self.assertGreaterEqual(len(records), 2)

        torn_rec = records[-2]
        self.assertEqual(torn_rec["kind"], "torn-append")
        self.assertEqual(torn_rec["rule"], "OC-004(a)")
        self.assertEqual(torn_rec["offset"], len(clean_content))
        self.assertEqual(torn_rec["bytes"], len(fragment))
        self.assertEqual(torn_rec["sha256"], sha256(fragment))

        last_rec = records[-1]
        self.assertEqual(last_rec["kind"], "pulse")
        self.assertEqual(last_rec["id"], new_loc["id"])

        self.assertTrue(verify(S, full_log=True).verified)

    def test_start_after_a_torn_append_is_accepted(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        write_fragment(store)
        self.assertEqual(lifecycle.start(S).outcome, "accepted")
        records, truncated = store.read_jsonl(sil.LOG)
        self.assertFalse(truncated)
        self.assertIn("torn-append", [r["kind"] for r in records])
        self.assertTrue(verify(S, full_log=True).verified)

    def test_operator_act_outside_a_session_after_a_torn_append(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        write_fragment(store)
        operator.binding_add(S, "op-2")
        self.assertTrue(verify(S, full_log=True).verified)
        self.assertEqual(lifecycle.start(S).outcome, "accepted")

    def test_commit_refuses_unresolvable_authorization(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        head_before = sil.read_head(store)
        nxt = chain.gen_relpath(head_before["entry"] + 1)

        with self.assertRaises(sil.Refused) as ctx:
            sil.commit_generation(store, changes={}, authorization=FAKE_AUTH)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

        records, _ = store.read_jsonl(sil.LOG)
        refusals = [r for r in records if r.get("kind") == "refusal"]
        self.assertTrue(refusals)
        self.assertEqual(refusals[-1].get("check"), "authorization")

        n = head_before["entry"] + 1
        self.assertFalse(store.exists(nxt))
        self.assertFalse(store.exists(chain.entry_relpath(n)))
        self.assertFalse(store.exists(chain.document_relpath(n)))
        self.assertEqual(sil.read_head(store), head_before)
        self.assertEqual(verify(S).findings, [])

    def test_commit_refuses_no_authorization(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        head_before = sil.read_head(store)
        with self.assertRaises(sil.Refused) as ctx:
            sil.commit_generation(store, changes={}, authorization=None)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(sil.read_head(store), head_before)

    def test_decommission_needs_a_decommission_act(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        approve = sil.operator_act_located(store, "approve", binding="op-1", rule="OC-001(b)")
        with self.assertRaises(sil.Refused) as ctx:
            sil.commit_generation(store, changes={}, authorization=approve, kind="decommission")
        self.assertEqual(ctx.exception.check, "authorization")
        act = sil.operator_act_located(store, "decommission", binding="op-1", rule="OC-002(c)")
        out = sil.commit_generation(store, changes={}, authorization=act, kind="decommission")
        self.assertEqual(out["entry"], 1)
        self.assertTrue(verify(S).decommissioned)

    def test_commit_refuses_wrong_act_authorization(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        head_before = sil.read_head(store)
        nxt = chain.gen_relpath(head_before["entry"] + 1)

        wrong_act_auth = sil.operator_act_located(
            store, "probe-override", binding="op-1", rule="OC-002(d)"
        )
        with self.assertRaises(sil.Refused) as ctx:
            sil.commit_generation(store, changes={}, authorization=wrong_act_auth)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

        self.assertFalse(store.exists(nxt))

    def test_commit_refuses_tampered_offset_authorization(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        head_before = sil.read_head(store)
        nxt = chain.gen_relpath(head_before["entry"] + 1)

        valid_auth = sil.operator_act_located(
            store, "approve", binding="op-1", rule="OC-001(b)"
        )
        tampered_auth = dict(valid_auth)
        tampered_auth["offset"] = valid_auth["offset"] + 1

        with self.assertRaises(sil.Refused) as ctx:
            sil.commit_generation(store, changes={}, authorization=tampered_auth)
        self.assertEqual(ctx.exception.check, "authorization")
        self.assertEqual(ctx.exception.rule, "OC-001(b)")

        self.assertFalse(store.exists(nxt))

    def test_proposals_open_window_requires_authorization(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)
        exp = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        with self.assertRaises(TypeError):
            proposals.open_window(
                store,
                scope="evolution",
                expires=exp,
                budget=5,
                record="L-000010",
                binding="op-1",
            )

        auth_dict = {"id": "L-000010", "sha256": "sha256:abc", "offset": 123}
        proposals.open_window(
            store,
            scope="evolution",
            expires=exp,
            budget=5,
            record="L-000010",
            binding="op-1",
            authorization=auth_dict,
        )
        data = proposals.read_auth(store)
        grant = next(g for g in data["grants"] if g["id"] == "L-000010")
        self.assertEqual(grant["authorization"], auth_dict)

    def test_proposals_record_approval_requires_authorization(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        store = Store(S)

        with self.assertRaises(TypeError):
            proposals.record_approval(
                store,
                "P-1",
                "sha256:digest",
                "L-000015",
                "op-1",
            )

        auth_dict = {"id": "L-000015", "sha256": "sha256:abc", "offset": 456}
        proposals.record_approval(
            store,
            "P-1",
            "sha256:digest",
            "L-000015",
            "op-1",
            authorization=auth_dict,
        )
        data = proposals.read_auth(store)
        self.assertEqual(data["approvals"]["P-1"]["authorization"], auth_dict)

    def test_proposal_commit_with_valid_authorization_flow(self):
        S = self.p("S")
        sil.first_activation(S, "op-1")
        lifecycle.start(S)

        out_p = proposals.propose(
            S, [{"op": "set-persona", "content": "You are a helpful assistant."}]
        )
        pid = out_p["proposal"]

        appr = operator.approve(S, pid)
        self.assertTrue(appr["log_records"])

        out_c = proposals.commit(S, pid)
        self.assertEqual(out_c["entry"], 1)

        store = Store(S)
        chain_entry = store.read_json("integrity/chain/000001.json")
        self.assertIn("authorization", chain_entry)
        self.assertEqual(chain_entry["authorization"]["id"], appr["log_records"][0])

        rep = verify(S)
        self.assertTrue(rep.chain_intact)
        self.assertTrue(rep.content_matches)
        self.assertFalse(rep.findings)
