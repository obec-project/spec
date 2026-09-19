import os
import shutil
import unittest
from unittest import mock

from helpers import TempDirTest

from fsp import sil
from fsp.store import Store
from fsp.verify import verify
from fsp_testing import inject


class FirstActivation(TempDirTest):
    def test_fap_founds_a_verified_entity(self):
        out = sil.first_activation(self.p("S"), "op-1")
        r = verify(self.p("S"))
        self.assertTrue(r.verified, r.as_dict())
        self.assertEqual(r.genesis_digest, out["genesis_digest"])
        self.assertEqual(r.head_digest, out["head_digest"])
        self.assertEqual(r.entry_count, 1)
        _, genesis = r.entries[0]
        self.assertEqual(genesis["binding"], "op-1")
        self.assertEqual(genesis["version"], "0.9.1")
        self.assertEqual(genesis["major"], 0)
        # No credential: the first one comes from a gated start (D29).
        self.assertFalse(os.path.exists(self.p("S", "CREDENTIAL")))
        records, _ = Store(self.p("S")).read_jsonl("integrity/log.jsonl")
        self.assertEqual([r["kind"] for r in records], ["operator-act", "genesis"])
        self.assertEqual(records[0]["binding"], "op-1")

    def test_same_content_is_still_a_different_entity(self):
        a = sil.first_activation(self.p("A"), "op-1")
        b = sil.first_activation(self.p("B"), "op-1")
        self.assertEqual(a["head_digest"], b["head_digest"])
        self.assertNotEqual(a["genesis_digest"], b["genesis_digest"])

    def test_runs_exactly_once(self):
        sil.first_activation(self.p("S"), "op-1")
        before = verify(self.p("S")).as_dict()
        with self.assertRaises(sil.Refused) as cm:
            sil.first_activation(self.p("S"), "op-2")
        self.assertEqual(cm.exception.check, "first-activation")
        self.assertTrue(cm.exception.log_records)
        self.assertEqual(verify(self.p("S")).as_dict(), before)

    def test_refuses_a_directory_that_is_not_a_store(self):
        os.makedirs(self.p("S"))
        with open(self.p("S", "keep.txt"), "w") as f:
            f.write("mine")
        with self.assertRaises(sil.Refused):
            sil.first_activation(self.p("S"), "op-1")
        self.assertEqual(os.listdir(self.p("S")), ["keep.txt"])

    def test_refuses_a_bad_binding_id(self):
        for bad in ("", "../x", "a b", "-x"):
            with self.assertRaises(sil.Refused):
                sil.first_activation(self.p("S"), bad)

    def test_interrupted_fap_leaves_no_entity_and_reruns(self):
        real = Store.replace

        def dies_at_head(self, cls, relpath, data, **kw):
            if relpath == "HEAD":
                raise KeyboardInterrupt("process death")
            return real(self, cls, relpath, data, **kw)

        with mock.patch.object(Store, "replace", dies_at_head):
            with self.assertRaises(KeyboardInterrupt):
                sil.first_activation(self.p("S"), "op-1")
        r = verify(self.p("S"))
        self.assertEqual(r.state, "scaffolded")
        self.assertFalse(r.chain_intact)
        self.assertIsNone(r.genesis_digest)

        sil.first_activation(self.p("S"), "op-1")
        r = verify(self.p("S"))
        self.assertTrue(r.verified, r.as_dict())
        records, _ = Store(self.p("S")).read_jsonl("integrity/log.jsonl")
        self.assertEqual(records[0]["id"], "L-000001")
        self.assertIsNone(records[0]["prev"])


class Portability(TempDirTest):
    """Step 3.2, locally: a relocated copy verifies identically. Not a
    substitute for a second host (a hostname is the same here)."""

    def test_relocated_copy_verifies_identically(self):
        sil.first_activation(self.p("S"), "op-1")
        shutil.copytree(self.p("S"), self.p("far", "away", "S2"), copy_function=shutil.copy)
        for dirpath, _d, files in os.walk(self.p("far")):
            for f in files:
                os.utime(os.path.join(dirpath, f), (1, 1))
        a = verify(self.p("S")).as_dict()
        b = verify(self.p("far", "away", "S2")).as_dict()
        self.assertTrue(a["chain_intact"] and a["content_matches"])
        self.assertEqual(a, b)


class Detection(TempDirTest):
    """OC-004(a): each corruption is detected at the next verification."""

    def setUp(self):
        super().setUp()
        sil.first_activation(self.p("S"), "op-1")
        self.S = self.p("S")

    def corrupt(self, kind):
        inject.corrupt(self.S, {"kind": kind})
        return verify(self.S)

    def test_structural_byte(self):
        r = self.corrupt("structural-byte")
        self.assertFalse(r.content_matches)
        self.assertEqual(
            [(f.type, f.target) for f in r.findings],
            [("structural-drift", "structural/gen/0/persona.md")],
        )

    def test_chain_entry_removed(self):
        r = self.corrupt("chain-entry-removed")
        self.assertFalse(r.chain_intact)

    def test_chain_entry_forged(self):
        r = self.corrupt("chain-entry-forged")
        self.assertFalse(r.chain_intact)
        self.assertIn("predecessor", [f.evidence.get("problem") for f in r.findings])

    def test_exec_bit_extra_file_and_unclassified_datum(self):
        gen = os.path.join(self.S, "structural", "gen", "0")
        os.chmod(os.path.join(gen, "persona.md"), 0o755)
        with open(os.path.join(gen, "extra.md"), "w") as f:
            f.write("x")
        with open(os.path.join(self.S, "integrity", "notes.txt"), "w") as f:
            f.write("x")
        r = verify(self.S)
        got = {(f.type, f.target, f.evidence.get("problem")) for f in r.findings}
        self.assertEqual(
            got,
            {
                ("structural-drift", "structural/gen/0/persona.md", "exec-bit"),
                ("structural-drift", "structural/gen/0/extra.md", "unexpected"),
                ("unclassified-datum", "integrity/notes.txt", None),
            },
        )

    def test_bytes_in_the_lock_file_are_detected(self):
        with open(os.path.join(self.S, "integrity", "store.lock"), "wb") as f:
            f.write(b"x")
        r = verify(self.S)
        self.assertEqual([(f.type, f.target) for f in r.findings], [("store-lock", "integrity/store.lock")])

    def test_residue_beyond_head_is_not_committed_state(self):
        before = verify(self.S).as_dict()
        shutil.copytree(
            os.path.join(self.S, "structural", "gen", "0"),
            os.path.join(self.S, "structural", "gen", "1"),
        )
        r = verify(self.S)
        self.assertTrue(r.verified)
        self.assertEqual(r.residue, [{"path": "structural/gen/1", "kind": "uncommitted"}])
        self.assertEqual(r.head_digest, before["head_digest"])

    def test_missing_store(self):
        r = verify(self.p("nope"))
        self.assertFalse(r.chain_intact)
        self.assertIsNone(r.genesis_digest)

    # Step 4.7, format-independent: flip one byte in each file of the store.

    def flip_each(self, rels):
        undetected = []
        for rel in rels:
            path = os.path.join(self.S, rel)
            with open(path, "rb") as f:
                data = bytearray(f.read())
            if not data:
                continue  # nothing to flip (integrity/store.lock)
            for i in (0, len(data) // 2, len(data) - 2):
                orig = data[i]
                data[i] ^= 0x01
                with open(path, "wb") as f:
                    f.write(bytes(data))
                if verify(self.S).verified:
                    undetected.append((rel, i))
                data[i] = orig
                with open(path, "wb") as f:
                    f.write(bytes(data))
        return undetected

    def all_files(self):
        out = []
        for dirpath, _d, files in os.walk(self.S):
            for f in files:
                out.append(os.path.relpath(os.path.join(dirpath, f), self.S))
        return sorted(out)

    def test_byte_flip_anywhere_verified_is_detected(self):
        rels = [r for r in self.all_files() if r != "integrity/log.jsonl"]
        self.assertEqual(self.flip_each(rels), [])

    @unittest.expectedFailure
    def test_byte_flip_in_the_log_is_detected(self):
        # Known gap: the log is hash-linked (`prev`) but not yet verified.
        # Phase 2 resolves commit authorizations against it (step 4.6).
        self.assertEqual(self.flip_each(["integrity/log.jsonl"]), [])
