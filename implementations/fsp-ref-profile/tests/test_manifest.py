# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

import json
import os

from helpers import TempDirTest

from fsp import lifecycle, sil
from fsp import manifest as skill_manifest
from fsp.adapter import CannotAttempt
from fsp.digest import canonical
from fsp.store import GuardError, Store, remove_host_tree
from fsp_testing import fixture, inject


class ManifestTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        sil.first_activation(self.S, "op-1")
        self.store = Store(self.S)

    def install(self):
        sil.commit_generation(
            self.store,
            changes={
                "skills/example/" + k: v.encode()
                for k, v in fixture.skill_files("example").items()
            },
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )

    def fixture_manifest(self):
        return json.loads(fixture.skill_files("example")["manifest.json"])

    def test_the_fixture_is_a_valid_skill(self):
        files = fixture.skill_files("example")
        self.assertEqual(set(files), {"manifest.json", "run.sh"})
        self.assertEqual(
            skill_manifest.problems(json.loads(files["manifest.json"]), "example"),
            [],
        )

    def test_each_rule_of_the_manifest_is_checked(self):
        base = self.fixture_manifest()
        variations = [
            dict(base, name="other"),
            {k: v for k, v in base.items() if k != "description"},
            dict(base, argv=[]),
            dict(base, argv=["/bin/sh"]),
            dict(base, argv=["{skill}"]),
            dict(base, argv=["sh", "{home}"]),
            dict(base, timeout_s=0),
            dict(base, timeout_s=601),
            dict(base, timeout_s=True),
            dict(base, targets=["/abs"]),
            dict(base, targets=["../x"]),
            dict(base, irreversible="no"),
        ]
        for manifest in variations:
            with self.subTest(manifest=manifest):
                self.assertNotEqual(skill_manifest.problems(manifest, "example"), [])
        self.assertNotEqual(skill_manifest.problems([], "example"), [])

    def test_the_digest_ignores_order_and_follows_content(self):
        a = {"path": "run.sh", "sha256": "sha256:" + "1" * 64, "exec": False}
        b = {"path": "manifest.json", "sha256": "sha256:" + "2" * 64, "exec": False}
        digest = skill_manifest.skill_digest([a, b])
        self.assertEqual(digest, skill_manifest.skill_digest([b, a]))
        changed = dict(b, sha256="sha256:" + "3" * 64)
        self.assertNotEqual(digest, skill_manifest.skill_digest([a, changed]))

    def test_a_copy_lands_outside_the_store_and_is_removed(self):
        self.install()
        d = self.store.copy_out(
            "structural/gen/1/skills/example", ["manifest.json", "run.sh"]
        )
        self.assertFalse(
            d == os.path.realpath(self.S)
            or d.startswith(os.path.realpath(self.S) + os.sep)
        )
        with open(os.path.join(d, "run.sh"), "rb") as f:
            self.assertEqual(f.read(), b"exit 0\n")
        remove_host_tree(d, stores=(self.S,))
        self.assertFalse(os.path.exists(d))

    def test_removing_a_tree_inside_the_store_is_refused(self):
        with self.assertRaises(GuardError):
            remove_host_tree(self.store.path("structural"), stores=(self.S,))
        self.assertTrue(os.path.isdir(self.store.path("structural")))

    def test_the_fixture_is_indexed(self):
        self.install()
        lifecycle.start(self.S)
        index = self.store.read_json(lifecycle.INDEX)
        self.assertIn("example", [s["name"] for s in index["skills"]])

    def test_an_invalid_manifest_is_excluded_and_the_start_goes_on(self):
        sil.commit_generation(
            self.store,
            changes={"skills/bad/manifest.json": canonical({"name": "bad"})},
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )
        res = lifecycle.start(self.S)
        self.assertEqual(res.outcome, "accepted")
        bad = [e for e in res.excluded_skills if e["name"] == "bad"]
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0]["reason"].startswith("manifest:"))

    def test_inject_corrupts_the_fixture(self):
        self.install()
        res = inject.corrupt(self.S, {"kind": "skill-file"})
        self.assertEqual(res["outcome"], "accepted")
        gen = "structural/gen/1/skills/example/"
        self.assertNotEqual(self.store.read_bytes(gen + "run.sh"), b"exit 0\n")
        res = inject.corrupt(self.S, {"kind": "skill-manifest"})
        self.assertEqual(res["outcome"], "accepted")
        self.assertEqual(
            self.store.read_bytes(gen + "manifest.json"), b"{not a manifest"
        )

    def test_inject_without_the_fixture_cannot_attempt(self):
        with self.assertRaises(CannotAttempt):
            inject.corrupt(self.S, {"kind": "skill-file"})
