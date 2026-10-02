# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
import json
import os
import unittest

from helpers import TempDirTest, run_adapter

from fsp import chain, lifecycle, operator, sil
from fsp.digest import canonical, sha256
from fsp.store import INTEGRITY, Store
from fsp.verify import verify
from fsp_testing import inject


class LogVerificationTests(TempDirTest):
    """Integrity log verification at startup and on demand (D45)."""

    def test_binding_add_records_locator_and_verifies(self):
        # After an operator.binding_add outside a session, verify passes, the
        # last entry's authorization is the locator of the binding-add act, and
        # the line at its offset has its sha256.
        root = self.p("S")
        sil.first_activation(root, "op-1")
        out = operator.binding_add(root, "op-2", binding="op-1")
        r = verify(root)
        self.assertTrue(r.verified, r.as_dict())
        store = Store(root)
        head = sil.read_head(store)
        entry = store.read_json(chain.entry_relpath(head["entry"]))
        auth = entry.get("authorization")
        self.assertIsInstance(auth, dict)
        self.assertEqual(set(auth.keys()), {"id", "sha256", "offset"})
        self.assertEqual(auth["id"], out["log_records"][0])
        line = store.read_line_at("integrity/log.jsonl", auth["offset"])
        self.assertIsNotNone(line)
        self.assertEqual(sha256(line), auth["sha256"])

    def test_commit_unauthorized_detected(self):
        # A commit with no recorded authorization breaks the chain with one
        # blocking finding, authorization-unresolved, and no credential issues.
        root = self.p("S")
        sil.first_activation(root, "op-1")
        inject.corrupt(root, {"kind": "commit-unauthorized"})
        r = verify(root)
        self.assertFalse(r.chain_intact)
        blocking = r.blocking_findings()
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0].type, "chain-entry")
        self.assertEqual(blocking[0].evidence.get("problem"), "authorization-unresolved")
        res = lifecycle.start(root)
        self.assertNotEqual(res.outcome, "accepted")
        self.assertFalse(Store(root).exists(lifecycle.CREDENTIAL))

    def test_authorization_pointing_to_non_authorizing_real_record(self):
        # An authorization naming a real record that authorizes nothing (the
        # genesis log record, L-000002) does not resolve.
        root = self.p("S")
        sil.first_activation(root, "op-1")
        store = Store(root)
        log_bytes = store.read_bytes("integrity/log.jsonl")
        lines = log_bytes.split(b"\n")
        l2_bytes = lines[1]
        l2_rec = json.loads(l2_bytes.decode("utf-8"))
        self.assertEqual(l2_rec["id"], "L-000002")
        l2_offset = len(lines[0]) + 1
        l2_locator = {
            "id": "L-000002",
            "sha256": sha256(l2_bytes),
            "offset": l2_offset,
        }

        r = verify(root)
        n = r.head_entry + 1
        head = sil.read_head(store)
        body = chain.commit(
            n=n,
            predecessor=head["entry_id"],
            state_digest=r.head_digest,
            authorization=l2_locator,
            at="1970-01-01T00:00:00Z",
            kind="commit",
        )
        store.replace(INTEGRITY, chain.entry_relpath(n), canonical(body), writer=sil.WRITER)
        os.link(
            os.path.join(root, chain.document_relpath(r.head_entry)),
            os.path.join(root, chain.document_relpath(n)),
        )
        os.rename(
            os.path.join(root, chain.gen_relpath(r.head_entry)),
            os.path.join(root, chain.gen_relpath(n)),
        )
        new_head = chain.head(entry=n, entry_id=chain.entry_id(body), baseline=r.head_digest)
        store.replace(INTEGRITY, chain.HEAD, canonical(new_head), writer=sil.WRITER)

        r2 = verify(root)
        self.assertFalse(r2.chain_intact)
        blocking = [f for f in r2.blocking_findings() if f.type == "chain-entry"]
        self.assertTrue(any(f.evidence.get("problem") == "authorization-unresolved" for f in blocking))

    def test_checkpoint_after_start_and_stop(self):
        # start + stop leaves a checkpoint equal to the session-close locator.
        root = self.p("S")
        sil.first_activation(root, "op-1")
        lifecycle.start(root)
        out = lifecycle.stop(root)
        close_id = out["log_records"][0]
        store = Store(root)
        chk = store.read_json("integrity/log-checkpoint.json")
        self.assertEqual(chk["id"], close_id)
        line = store.read_line_at("integrity/log.jsonl", chk["offset"])
        self.assertIsNotNone(line)
        self.assertEqual(chk["sha256"], sha256(line))
        rec = json.loads(line.decode("utf-8"))
        self.assertEqual(rec["id"], close_id)
        self.assertEqual(rec["kind"], "session-close")

    def test_byte_flip_in_record_after_checkpoint_detected(self):
        # A byte flipped in a record after the checkpoint is found by the tail
        # verification, and the start aborts.
        root = self.p("S")
        sil.first_activation(root, "op-1")
        lifecycle.start(root)
        lifecycle.stop(root)
        lifecycle.start(root)
        store = Store(root)
        chk = store.read_json("integrity/log-checkpoint.json")
        log_path = store.path("integrity/log.jsonl")
        with open(log_path, "rb") as f:
            data = bytearray(f.read())
        chk_line = store.read_line_at("integrity/log.jsonl", chk["offset"])
        tail_start = chk["offset"] + len(chk_line) + 1
        idx = data.find(b"sha256:", tail_start)
        self.assertNotEqual(idx, -1)
        data[idx + 10] ^= 0x01
        with open(log_path, "wb") as f:
            f.write(data)

        r = verify(root)
        self.assertFalse(r.chain_intact)
        self.assertTrue(any(f.type == "log-record" for f in r.findings))

        pulse_path = store.path(lifecycle.PULSE)
        st = os.stat(pulse_path)
        os.utime(pulse_path, (st.st_atime - 10000, st.st_mtime - 10000))
        res = lifecycle.start(root)
        self.assertEqual(res.outcome, "aborted")

    def test_byte_flip_before_checkpoint_ignored_by_tail_but_caught_by_full(self):
        # A byte flipped in L-000001, before the checkpoint and named by no
        # entry, passes the tail verification and is found by the full one,
        # including through the adapter's lifecycle verify.
        root = self.p("S")
        sil.first_activation(root, "op-1")
        lifecycle.start(root)
        lifecycle.stop(root)
        store = Store(root)
        log_path = store.path("integrity/log.jsonl")
        with open(log_path, "rb") as f:
            data = bytearray(f.read())
        first_nl = data.find(b"\n")
        self.assertGreater(first_nl, 0)
        mid = first_nl // 2
        data[mid] ^= 0x01
        with open(log_path, "wb") as f:
            f.write(data)

        r_tail = verify(root)
        self.assertTrue(r_tail.verified)
        self.assertEqual(r_tail.log_mode, "tail")

        r_full = verify(root, full_log=True)
        self.assertFalse(r_full.chain_intact)
        self.assertTrue(any(f.type == "log-record" for f in r_full.findings))

        code, out = run_adapter("lifecycle", "verify", "--store", root)
        self.assertFalse(out["detail"]["chain_intact"])

    def test_missing_and_unreadable_checkpoint_fallbacks(self):
        # Without a checkpoint, or with one that is not canonical, the log is
        # verified in full and the start logs why.
        root = self.p("S")
        sil.first_activation(root, "op-1")
        store = Store(root)

        # No checkpoint
        self.assertFalse(store.exists("integrity/log-checkpoint.json"))
        r = verify(root)
        self.assertTrue(r.verified)
        self.assertEqual(r.log_mode, "full")
        self.assertEqual(r.log_full_reason, "checkpoint-missing")
        lifecycle.start(root)
        records, _ = store.read_jsonl("integrity/log.jsonl")
        verif_records = [rec for rec in records if rec.get("kind") == "log-verification"]
        self.assertTrue(verif_records)
        self.assertEqual(verif_records[-1]["mode"], "full")
        self.assertEqual(verif_records[-1]["reason"], "checkpoint-missing")
        lifecycle.stop(root)

        # A checkpoint that is not canonical
        chk_path = store.path("integrity/log-checkpoint.json")
        with open(chk_path, "rb") as f:
            chk_bytes = f.read()
        with open(chk_path, "wb") as f:
            f.write(b"{\n  " + chk_bytes[1:])
        r2 = verify(root)
        self.assertTrue(r2.verified)
        self.assertEqual(r2.log_mode, "full")
        self.assertEqual(r2.log_full_reason, "checkpoint-unreadable")
        lifecycle.start(root)
        records2, _ = store.read_jsonl("integrity/log.jsonl")
        verif_records2 = [rec for rec in records2 if rec.get("kind") == "log-verification"]
        self.assertTrue(verif_records2)
        self.assertEqual(verif_records2[-1]["mode"], "full")
        self.assertEqual(verif_records2[-1]["reason"], "checkpoint-unreadable")

    def test_canonical_checkpoint_pointing_to_different_record_produces_finding(self):
        # A canonical checkpoint whose offset points at another record is a
        # log-checkpoint finding.
        root = self.p("S")
        sil.first_activation(root, "op-1")
        lifecycle.start(root)
        lifecycle.stop(root)
        store = Store(root)
        chk = store.read_json("integrity/log-checkpoint.json")
        chk["offset"] = 0
        store.replace(INTEGRITY, "integrity/log-checkpoint.json", canonical(chk), writer=sil.WRITER)

        r = verify(root)
        self.assertFalse(r.chain_intact)
        chk_findings = [f for f in r.findings if f.type == "log-checkpoint"]
        self.assertEqual(len(chk_findings), 1)
        self.assertEqual(chk_findings[0].evidence.get("problem"), "mismatch")


if __name__ == "__main__":
    unittest.main()
