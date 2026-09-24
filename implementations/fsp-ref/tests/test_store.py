import errno
import os
import subprocess
import sys
from unittest import mock

from helpers import ROOT, TempDirTest

from fsp.store import (
    INTEGRITY,
    LOCK,
    MNEMONIC,
    STRUCTURAL,
    GuardError,
    LockUnavailable,
    Store,
    class_of,
    create_store_dir,
    flock_exclusive,
)


class ClassGuard(TempDirTest):
    def setUp(self):
        super().setUp()
        create_store_dir(self.p("S"))
        self.s = Store(self.p("S"))

    def refused(self, check, fn, *a, **kw):
        with self.assertRaises(GuardError) as cm:
            fn(*a, **kw)
        self.assertEqual(cm.exception.check, check)

    def test_classes_of_the_layout(self):
        self.assertEqual(class_of("HEAD"), INTEGRITY)
        self.assertEqual(class_of("CREDENTIAL"), INTEGRITY)
        self.assertEqual(class_of("structural/gen/3/skills/x/manifest.json"), STRUCTURAL)
        self.assertEqual(class_of("integrity/chain/000001.json"), INTEGRITY)
        self.assertEqual(class_of("memory/session/s-1.jsonl"), MNEMONIC)
        self.assertIsNone(class_of("integrity/chain/1.json"))
        self.assertIsNone(class_of("structural/persona.md"))
        self.assertIsNone(class_of("notes.txt"))

    def test_each_class_has_one_writer(self):
        self.s.replace(INTEGRITY, "HEAD", b"{}", writer="sil")
        self.refused("sole-writer", self.s.replace, INTEGRITY, "HEAD", b"{}", writer="mil")
        self.refused("sole-writer", self.s.replace, INTEGRITY, "HEAD", b"{}", writer="sil.commit")
        self.refused(
            "sole-writer",
            self.s.replace,
            STRUCTURAL,
            "structural/gen/0/persona.md",
            b"x",
            writer="sil",
        )
        self.refused(
            "sole-writer",
            self.s.append,
            MNEMONIC,
            "memory/episodic/records.jsonl",
            {},
            writer="sil",
        )

    def test_a_class_cannot_reach_another_by_path(self):
        # The owner of mnemonic content naming an integrity path.
        self.refused(
            "content-class", self.s.append, MNEMONIC, "integrity/log.jsonl", {}, writer="mil"
        )
        self.refused(
            "content-class", self.s.replace, STRUCTURAL, "HEAD", b"{}", writer="sil.commit"
        )
        self.refused("content-class", self.s.replace, INTEGRITY, "notes.txt", b"", writer="sil")
        self.refused("content-class", self.s.replace, "secret", "HEAD", b"", writer="sil")

    def test_paths_must_be_normalized(self):
        for bad in ("../HEAD", "/HEAD", "integrity/../HEAD", "integrity//log.jsonl", "./HEAD", ""):
            self.refused("store-path", self.s.replace, INTEGRITY, bad, b"", writer="sil")

    def test_write_forms(self):
        self.refused(
            "write-form", self.s.replace, INTEGRITY, "integrity/log.jsonl", b"", writer="sil"
        )
        self.refused("write-form", self.s.append, INTEGRITY, "HEAD", {}, writer="sil")
        self.s.append(INTEGRITY, "integrity/log.jsonl", {"a": 1}, writer="sil")
        self.refused("append-only", self.s.remove, INTEGRITY, "integrity/log.jsonl", writer="sil")


class WriteForms(TempDirTest):
    def setUp(self):
        super().setUp()
        create_store_dir(self.p("S"))
        self.s = Store(self.p("S"))

    def test_replace_sets_exec_bit_and_leaves_no_temp(self):
        rel = "structural/gen/0/skills/x/run"
        self.s.replace(STRUCTURAL, rel, b"#!/bin/sh\n", writer="sil.commit", executable=True)
        self.assertTrue(os.stat(self.s.path(rel)).st_mode & 0o100)
        self.s.replace(STRUCTURAL, rel, b"x", writer="sil.commit")
        self.assertFalse(os.stat(self.s.path(rel)).st_mode & 0o100)
        self.assertEqual(os.listdir(os.path.dirname(self.s.path(rel))), ["run"])

    def test_torn_append_is_detected_not_parsed(self):
        rel = "integrity/log.jsonl"
        self.s.append(INTEGRITY, rel, {"id": "L-000001"}, writer="sil")
        self.s.append(INTEGRITY, rel, {"id": "L-000002"}, writer="sil")
        records, truncated = self.s.read_jsonl(rel)
        self.assertEqual([r["id"] for r in records], ["L-000001", "L-000002"])
        self.assertFalse(truncated)
        with open(self.s.path(rel), "ab") as f:
            f.write(b'{"id":"L-0000')
        records, truncated = self.s.read_jsonl(rel)
        self.assertEqual(len(records), 2)
        self.assertTrue(truncated)
        self.assertEqual(self.s.read_last_jsonl(rel)["id"], "L-000002")

    def test_read_last_across_chunks(self):
        rel = "integrity/log.jsonl"
        for i in range(3000):
            self.s.append(INTEGRITY, rel, {"id": "L-%06d" % i, "pad": "x" * 40}, writer="sil")
        self.assertEqual(self.s.read_last_jsonl(rel)["id"], "L-002999")
        self.assertIsNone(self.s.read_last_jsonl("integrity/ledger.jsonl"))

    def test_exclusive_create(self):
        self.assertTrue(self.s.create_exclusive(INTEGRITY, "CREDENTIAL", b"c", writer="sil"))
        self.assertFalse(self.s.create_exclusive(INTEGRITY, "CREDENTIAL", b"d", writer="sil"))
        self.assertEqual(self.s.read_bytes("CREDENTIAL"), b"c")


class WriteLock(TempDirTest):
    def setUp(self):
        super().setUp()
        create_store_dir(self.p("S"))
        self.s = Store(self.p("S"))
        with self.s.write_lock():  # creates integrity/store.lock
            pass

    def test_excludes_another_process_and_is_reentrant(self):
        s = self.s
        probe = (
            "import fcntl,os,sys; fd=os.open(sys.argv[1], os.O_RDWR|os.O_CREAT)\n"
            "try:\n fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB); print('free')\n"
            "except BlockingIOError: print('held')\n"
        )

        def other():
            return subprocess.run(
                [sys.executable, "-c", probe, s.path(LOCK)], capture_output=True, text=True
            ).stdout.strip()

        self.assertEqual(other(), "free")
        with s.write_lock():
            with s.write_lock():
                self.assertEqual(other(), "held")
            self.assertEqual(other(), "held")
        self.assertEqual(other(), "free")
        self.assertEqual(class_of(LOCK), INTEGRITY)
        self.assertEqual(os.path.getsize(s.path(LOCK)), 0)

    def test_a_filesystem_without_flock_fails_closed(self):
        def no_locks(fd, op):
            raise OSError(errno.ENOLCK, "No locks available")

        with mock.patch("fcntl.flock", no_locks):
            with self.assertRaises(LockUnavailable) as cm:
                self.s.replace(INTEGRITY, "HEAD", b"{}", writer="sil")
        self.assertEqual(cm.exception.check, "store-lock")
        self.assertIn("ENOLCK", cm.exception.detail)
        self.assertFalse(self.s.exists("HEAD"))

    def test_non_blocking_probe_distinguishes_held_from_free(self):
        fd = os.open(self.s.path(LOCK), os.O_RDWR | os.O_CREAT)
        self.addCleanup(os.close, fd)
        with self.s.write_lock():
            self.assertFalse(flock_exclusive(fd, blocking=False))
        self.assertTrue(flock_exclusive(fd, blocking=False))

    def test_the_lock_file_is_never_written_or_removed(self):
        with self.s.write_lock():
            pass
        for call in (
            lambda: self.s.replace(INTEGRITY, LOCK, b"x", writer="sil"),
            lambda: self.s.append(INTEGRITY, LOCK, {}, writer="sil"),
            lambda: self.s.remove(INTEGRITY, LOCK, writer="sil"),
        ):
            with self.assertRaises(GuardError):
                call()
        self.assertTrue(self.s.exists(LOCK))

    def test_fap_residue_removal_keeps_the_held_lock_file(self):
        with self.s.write_lock():
            inode = os.stat(self.s.path(LOCK)).st_ino
            self.s.append(INTEGRITY, "integrity/log.jsonl", {"id": "L-000001"}, writer="sil")
            self.s.remove_fap_residue(writer="sil")
            self.assertEqual(os.stat(self.s.path(LOCK)).st_ino, inode)
            self.assertEqual(self.s.listdir("integrity"), ["store.lock"])


class NoRawWrites(TempDirTest):
    """Every write to the store goes through store.py (DESIGN.md §2)."""

    FORBIDDEN = (
        "os.rename(",
        "os.replace(",
        "os.remove(",
        "os.unlink(",
        "os.rmdir(",
        "os.mkdir(",
        "os.makedirs(",
        "os.write(",
        "os.link(",
        "os.symlink(",
        "os.chmod(",
        "os.fchmod(",
        "os.truncate(",
        "shutil.",
        '"w"',
        '"wb"',
        '"a"',
        '"ab"',
        '"x"',
        "'w'",
        "'a'",
        ".write_text(",
        ".write_bytes(",
    )

    def test_only_store_py_writes(self):
        pkg = os.path.join(ROOT, "fsp")
        offenders = []
        for dirpath, _dirs, files in os.walk(pkg):
            for name in files:
                if not name.endswith(".py") or name == "store.py":
                    continue
                path = os.path.join(dirpath, name)
                with open(path, encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        code = line.split("#", 1)[0]
                        for token in self.FORBIDDEN:
                            if token in code:
                                offenders.append("%s:%d %s" % (os.path.relpath(path, ROOT), lineno, token))
        self.assertEqual(offenders, [])
