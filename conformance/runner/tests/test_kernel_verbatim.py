"""The kernel is a verbatim extract of OBEC-Core §2.

OBEC-Core §4.1 says that where spec/obec-kernel.md differs from §2, §2 governs
and the kernel is in error, and that a check of that correspondence belongs in
the conformance suite. This is that check. It runs against the documents, not
against an implementation.

For each invariant it holds that:

- the kernel and §2 address the same clauses;
- every sentence of the kernel appears, word for word, in that invariant's
  section of §2 (the extract may omit, never reword);
- every sentence of §2 that carries a capitalised RFC 2119 keyword appears in
  the kernel (the extract may omit apparatus, never a requirement).

Clause labels, bold and list markers are presentation and are ignored; tests
and notes are apparatus and are not part of the extract.
"""

import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
KERNEL = os.path.join(ROOT, "spec", "obec-kernel.md")
CORE = os.path.join(ROOT, "spec", "obec-core.md")

INVARIANT = re.compile(r"^#{2,3} (HC-\d{3}) — .*$", re.M)
CLAUSE = re.compile(r"\*\*\(([a-z])\)[^*]*\*\*")
KEYWORD = re.compile(r"\b(MUST|REQUIRED|SHALL|SHOULD|RECOMMENDED|MAY|OPTIONAL)\b")
SENTENCE_END = re.compile(r"(?<=[.:;])\s+(?=[A-Z(])")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def section(text, start, end):
    """The text between two headings, exclusive."""
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


def invariants(text):
    """{"HC-001": body, ...}, each body ending at the next rule or heading."""
    heads = list(INVARIANT.finditer(text))
    out = {}
    for n, h in enumerate(heads):
        stop = heads[n + 1].start() if n + 1 < len(heads) else len(text)
        body = text[h.end():stop]
        cut = re.search(r"^(---|#{1,3} )", body, re.M)
        out[h.group(1)] = body[:cut.start()] if cut else body
    return out


def normative(body):
    """Drop the apparatus: *Test.* and *Note (...)* paragraphs."""
    paras = re.split(r"\n\s*\n", body)
    return "\n\n".join(p for p in paras
                       if not re.match(r"\s*\*(Test|Note)\b", p))


def flatten(body):
    body = CLAUSE.sub(" ", body)
    body = body.replace("**", "")
    body = re.sub(r"^\s*[-*] ", " ", body, flags=re.M)
    return re.sub(r"\s+", " ", body).strip()


def sentences(body):
    return [s for s in SENTENCE_END.split(flatten(body)) if s]


class KernelIsVerbatim(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        core = read(CORE)
        core2 = section(core, "\n## 2. ", "\n## 3. ")
        cls.core = {k: normative(v) for k, v in invariants(core2).items()}
        kernel = read(KERNEL)
        kernel = kernel[kernel.index("\n## HC-001"):]
        cls.kernel = {k: normative(v) for k, v in invariants(kernel).items()}

    def test_same_invariants(self):
        self.assertEqual(sorted(self.kernel), sorted(self.core))
        self.assertEqual(len(self.core), 10)

    def test_same_clauses(self):
        for rule in self.core:
            with self.subTest(rule=rule):
                self.assertEqual(CLAUSE.findall(self.kernel[rule]),
                                 CLAUSE.findall(self.core[rule]))

    def test_kernel_sentences_appear_in_core(self):
        for rule, body in self.kernel.items():
            core = flatten(self.core[rule])
            for s in sentences(body):
                with self.subTest(rule=rule, sentence=s):
                    self.assertIn(s, core, "kernel sentence not in §2")

    def test_core_requirements_appear_in_kernel(self):
        for rule, body in self.core.items():
            kernel = flatten(self.kernel[rule])
            for s in sentences(body):
                if KEYWORD.search(s):
                    with self.subTest(rule=rule, sentence=s):
                        self.assertIn(s, kernel, "§2 requirement missing from kernel")

    def test_versions_agree(self):
        version = re.compile(r'^version: "([^"]+)"', re.M)
        v = version.search(read(CORE)).group(1)
        kernel = read(KERNEL)
        self.assertEqual(version.search(kernel).group(1), v)
        self.assertIn(f'companion_to: "OBEC-Core {v}"', kernel)


if __name__ == "__main__":
    unittest.main()
