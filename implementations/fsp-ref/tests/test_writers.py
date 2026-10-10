# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Writer identities name only their own component (D69).

Store._guard checks the writer a call declares against the owner of the
class, but it cannot tell which module declared it. This scan reads the
source of every module in fsp/ and fails when a call passes a writer
identity that does not belong to the module's component, or one the scan
cannot resolve to a string.
"""

from __future__ import annotations

import ast
import importlib
import os
import types
import unittest

from helpers import ROOT

# Writer identity -> the fsp/ modules that may name it (D69).
ALLOWED = {
    "sil": {"sil", "lifecycle", "proposals", "operator", "vital"},
    "sil.commit": {"sil", "lifecycle"},
    "mil": {"mil"},
}
SKIP = {"store.py", "__init__.py"}


def writer_names(source, namespace):
    """Return ``(lineno, identity)`` for each ``writer=`` keyword in ``source``.

    ``identity`` is None when the value cannot be resolved to a string from
    ``namespace``, the module's globals.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "writer":
                continue
            value = kw.value
            identity = None
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                identity = value.value
            elif isinstance(value, ast.Name):
                resolved = namespace.get(value.id)
                if isinstance(resolved, str):
                    identity = resolved
            elif isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
                resolved = getattr(namespace.get(value.value.id), value.attr, None)
                if isinstance(resolved, str):
                    identity = resolved
            found.append((node.lineno, identity))
    return sorted(found, key=lambda pair: pair[0])


def violations(module, found):
    """Describe each writer in ``found`` that ``module`` may not name."""
    problems = []
    for lineno, identity in found:
        if identity is None:
            problems.append("%s:%d: a writer the scan cannot resolve" % (module, lineno))
        elif identity not in ALLOWED or module not in ALLOWED[identity]:
            problems.append(
                "%s:%d: names the writer %r outside its component"
                % (module, lineno, identity)
            )
    return problems


class WriterIdentities(unittest.TestCase):
    """Every writer named in fsp/ belongs to the module's component (D69)."""

    def test_every_module_names_only_its_component_s_writer(self):
        problems = []
        cited = set()
        pkg = os.path.join(ROOT, "fsp")
        for entry in sorted(os.listdir(pkg)):
            path = os.path.join(pkg, entry)
            if not entry.endswith(".py") or entry in SKIP or not os.path.isfile(path):
                continue
            name = entry[: -len(".py")]
            mod = importlib.import_module("fsp." + name)
            with open(path, encoding="utf-8") as f:
                source = f.read()
            found = writer_names(source, vars(mod))
            cited.update(identity for _lineno, identity in found if identity is not None)
            problems.extend(violations(name, found))
        self.assertEqual(problems, [])
        self.assertIn("sil", cited)

    def test_a_writer_named_outside_its_component_is_flagged(self):
        found = writer_names(
            'store.replace(INTEGRITY, "HEAD", b"", writer=WRITER)\n',
            {"WRITER": "sil"},
        )
        self.assertEqual(found, [(1, "sil")])
        self.assertEqual(len(violations("exec", found)), 1)
        self.assertEqual(violations("sil", found), [])

    def test_a_writer_named_as_an_attribute_or_a_string_is_resolved(self):
        found = writer_names(
            'a(writer=sil.WRITER)\nb(writer="mil")\n',
            {"sil": types.SimpleNamespace(WRITER="sil")},
        )
        self.assertEqual(found, [(1, "sil"), (2, "mil")])
        self.assertEqual(len(violations("vital", found)), 1)

    def test_a_writer_the_scan_cannot_resolve_is_flagged(self):
        found = writer_names("f(writer=pick())\n", {})
        self.assertEqual(found, [(1, None)])
        self.assertEqual(len(violations("sil", found)), 1)
