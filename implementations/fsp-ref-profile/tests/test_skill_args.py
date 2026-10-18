# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""A skill's typed arguments: the schema, the boundary of a marked path, the
skill-args check and the one-pass fill (OC-008, D71)."""

from __future__ import annotations

import json
import os

from helpers import TempDirTest

from fsp import chain, lifecycle, operator, sil
from fsp import exec as execution
from fsp import manifest as skill_manifest
from fsp.digest import canonical
from fsp.sil import Refused
from fsp.store import Store
from fsp_testing import fixture

ECHO = 'printf "%s\\n" "$@"\n'
SCHEMA = {
    "text": {"type": "string"},
    "n": {"type": "integer", "min": 0, "max": 9},
    "flag": {"type": "boolean"},
    "mode": {"type": "choice", "values": ["-a", "-b"]},
    "out": {"type": "path"},
}
GOOD = {"text": "hi", "n": 3, "flag": True, "mode": "-b", "out": {"path": "o.txt"}}


class SkillArgsTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        self.W = self.p("W")
        os.makedirs(self.W)
        sil.first_activation(self.S, "op-1")
        operator.set_workspace(self.S, self.W)
        self.store = Store(self.S)

    def commit(self, changes):
        sil.commit_generation(
            self.store,
            changes=changes,
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )

    def install(self, name="example", run=None, **manifest):
        files = fixture.skill_files(name)
        if manifest:
            doc = json.loads(files["manifest.json"])
            doc.update(manifest)
            files["manifest.json"] = canonical(doc).decode("utf-8")
        if run is not None:
            files["run.sh"] = run
        self.commit(
            {"skills/%s/%s" % (name, k): v.encode("utf-8") for k, v in files.items()}
        )

    def digest(self, name="example"):
        document = self.store.read_json(
            chain.document_relpath(sil.read_head(self.store)["entry"])
        )
        files = [e for e in document if e["path"].startswith("skills/%s/" % name)]
        return skill_manifest.skill_digest(files)

    def rule(self, name, rule, digest=None):
        self.commit(
            {
                "rules.json": canonical(
                    {
                        "default": "hold",
                        "domains": {},
                        "skills": {
                            name: {"rule": rule, "digest": digest or self.digest(name)}
                        },
                    }
                )
            }
        )

    def refusal(self):
        return lifecycle.observe_log(self.S, kind="refusal")["records"][-1]

    def install_args(self):
        self.install(
            run=ECHO,
            argv=[
                "sh",
                "{skill}/run.sh",
                "{args.text}",
                "{args.n}",
                "{args.flag}",
                "{args.mode}",
                "{args.out}",
            ],
            args=SCHEMA,
        )
        self.rule("example", "allow")

    def lines(self, out):
        return out["stdout"].decode().splitlines()

    def test_a_valid_schema(self):
        m = json.loads(fixture.skill_files("example")["manifest.json"])
        m["args"] = SCHEMA
        m["argv"] = [
            "sh",
            "{skill}/run.sh",
            "{args.text}",
            "{args.n}",
            "{args.flag}",
            "{args.mode}",
            "{args.out}",
        ]
        self.assertEqual(skill_manifest.problems(m, "example"), [])

    def test_each_rule_of_the_schema_is_checked(self):
        base = json.loads(fixture.skill_files("example")["manifest.json"])
        variations = [
            [],
            {"Bad": {"type": "boolean"}},
            {"x": {"type": "float"}},
            {"x": "string"},
            {"x": {"type": "string", "max_length": 0}},
            {"x": {"type": "string", "max_length": 4097}},
            {"x": {"type": "string", "max_length": True}},
            {"x": {"type": "integer", "min": 5, "max": 1}},
            {"x": {"type": "integer", "min": False}},
            {"x": {"type": "boolean", "default": True}},
            {"x": {"type": "choice", "values": []}},
            {"x": {"type": "choice", "values": ["a", "a"]}},
            {"x": {"type": "choice", "values": [1]}},
            {"x": {"type": "choice", "values": ["a\n"]}},
            {"x": {"type": "path", "max_length": 4}},
        ]
        for args in variations:
            with self.subTest(args=args):
                m = dict(base, args=args)
                self.assertNotEqual(skill_manifest.problems(m, "example"), [])
        m = dict(base, args={}, argv=["sh", "{args.missing}"])
        self.assertNotEqual(skill_manifest.problems(m, "example"), [])

    def test_args_reach_argv_typed(self):
        self.install_args()
        lifecycle.start(self.S)
        out = execution.invoke_skill(self.S, "example", args=GOOD)
        self.assertEqual(
            self.lines(out),
            ["hi", "3", "true", "-b", os.path.join(os.path.realpath(self.W), "o.txt")],
        )

    def test_placeholders_are_filled_in_one_pass(self):
        self.install_args()
        lifecycle.start(self.S)
        out = execution.invoke_skill(
            self.S, "example", args=dict(GOOD, text="{workspace}")
        )
        self.assertEqual(self.lines(out)[0], "{workspace}")

    def test_the_args_are_logged(self):
        self.install_args()
        lifecycle.start(self.S)
        execution.invoke_skill(self.S, "example", args=GOOD)
        rec = lifecycle.observe_log(self.S, kind="execution")["records"][-1]
        self.assertEqual(rec["args"], GOOD)

    def test_a_marked_path_outside_is_refused_before_the_index(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(
                self.S,
                "absent",
                args={"out": {"path": self.p("outside.txt")}},
            )
        self.assertEqual(ctx.exception.check, "workspace-boundary")

    def test_a_path_passed_as_a_string_is_refused(self):
        self.install_args()
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "example", args=dict(GOOD, out="o.txt"))
        self.assertEqual(ctx.exception.check, "skill-args")

    def test_a_marked_path_where_a_string_is_declared_is_refused(self):
        self.install_args()
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(
                self.S, "example", args=dict(GOOD, text={"path": "o.txt"})
            )
        self.assertEqual(ctx.exception.check, "skill-args")

    def test_missing_and_unknown_args_are_refused(self):
        self.install_args()
        lifecycle.start(self.S)
        without_n = {k: v for k, v in GOOD.items() if k != "n"}
        cases = [without_n, dict(GOOD, extra=1)]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(Refused) as ctx:
                    execution.invoke_skill(self.S, "example", args=args)
                self.assertEqual(ctx.exception.check, "skill-args")

    def test_values_of_the_wrong_type_are_refused(self):
        self.install_args()
        lifecycle.start(self.S)
        cases = [
            dict(GOOD, n="3"),
            dict(GOOD, n=True),
            dict(GOOD, n=10),
            dict(GOOD, flag=1),
            dict(GOOD, mode="-c"),
            dict(GOOD, text="x" * 4097),
        ]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(Refused) as ctx:
                    execution.invoke_skill(self.S, "example", args=args)
                self.assertEqual(ctx.exception.check, "skill-args")

    def test_a_string_with_a_dash_or_a_control_character_is_refused(self):
        self.install_args()
        lifecycle.start(self.S)
        for text in ["--pre=sh", "a\nb", "a\x00b"]:
            with self.subTest(text=text):
                with self.assertRaises(Refused) as ctx:
                    execution.invoke_skill(
                        self.S, "example", args=dict(GOOD, text=text)
                    )
                self.assertEqual(ctx.exception.check, "skill-args")

    def test_args_are_checked_before_the_rule(self):
        self.install(
            run=ECHO,
            argv=["sh", "{skill}/run.sh", "{args.text}"],
            args={"text": {"type": "string"}},
        )
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "example", args={})
        self.assertEqual(ctx.exception.check, "skill-args")

    def test_a_skill_without_args_takes_none(self):
        self.install()
        self.rule("example", "allow")
        lifecycle.start(self.S)
        for args in [None, {}]:
            with self.subTest(args=args):
                out = execution.invoke_skill(self.S, "example", args=args)
                self.assertEqual(out["outcome"], "done")
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "example", args={"x": 1})
        self.assertEqual(ctx.exception.check, "skill-args")

    def test_arguments_that_are_not_an_object_are_refused(self):
        self.install_args()
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "example", args=["hi"])
        self.assertEqual(ctx.exception.check, "skill-args")

    def test_a_malformed_path_object_is_refused_as_args(self):
        self.install_args()
        lifecycle.start(self.S)
        for out_value in [{"path": 3}, {"path": "o.txt", "x": 1}]:
            with self.subTest(out=out_value):
                with self.assertRaises(Refused) as ctx:
                    execution.invoke_skill(
                        self.S, "example", args=dict(GOOD, out=out_value)
                    )
                self.assertEqual(ctx.exception.check, "skill-args")
