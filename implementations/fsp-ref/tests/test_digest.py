# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
import os

from helpers import TempDirTest

from fsp.digest import canonical, document_digest, integrity_document


class Canonical(TempDirTest):
    def test_key_order_and_whitespace_do_not_matter(self):
        self.assertEqual(canonical({"b": 1, "a": [1, 2]}), b'{"a":[1,2],"b":1}')
        self.assertEqual(canonical({"é": "ç"}), '{"é":"ç"}'.encode("utf-8"))

    def write(self, rel, data=b"x", mode=0o644):
        path = self.p("gen", *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        os.chmod(path, mode)

    def test_document_is_sorted_and_carries_exec(self):
        self.write("persona.md")
        self.write("skills/b/run", mode=0o755)
        self.write("skills/a/manifest.json")
        doc, problems = integrity_document(self.p("gen"))
        self.assertEqual(problems, [])
        self.assertEqual(
            [(e["path"], e["exec"]) for e in doc],
            [("persona.md", False), ("skills/a/manifest.json", False), ("skills/b/run", True)],
        )
        before = document_digest(doc)
        os.chmod(self.p("gen", "skills", "b", "run"), 0o644)
        self.assertNotEqual(document_digest(integrity_document(self.p("gen"))[0]), before)

    def test_what_cannot_be_content_is_a_problem_not_a_hash(self):
        self.write("persona.md")
        os.symlink("/etc/passwd", self.p("gen", "link"))
        os.mkfifo(self.p("gen", "fifo"))
        self.write("bad name.txt")
        doc, problems = integrity_document(self.p("gen"))
        self.assertEqual([e["path"] for e in doc], ["persona.md"])
        self.assertEqual(
            {(p["path"], p["problem"]) for p in problems},
            {("link", "symlink"), ("fifo", "not-a-regular-file"), ("bad name.txt", "bad-name")},
        )

    def test_mtime_and_location_do_not_matter(self):
        self.write("persona.md", b"hello")
        a = document_digest(integrity_document(self.p("gen"))[0])
        os.utime(self.p("gen", "persona.md"), (0, 0))
        os.rename(self.p("gen"), self.p("elsewhere"))
        self.assertEqual(document_digest(integrity_document(self.p("elsewhere"))[0]), a)
