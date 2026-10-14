# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
from __future__ import annotations

import json
import os

from helpers import TempDirTest, run_adapter

from fsp import chain, lifecycle, operator, proposals, sil
from fsp import exec as execution
from fsp import manifest as skill_manifest
from fsp.digest import canonical, sha256
from fsp.sil import Refused
from fsp.store import Store
from fsp_testing import fixture


class RuleOpsTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.S = self.p("S")
        self.W = self.p("W")
        os.makedirs(self.W)
        sil.first_activation(self.S, "op-1")
        operator.set_workspace(self.S, self.W)
        self.store = Store(self.S)

    def rules(self):
        return self.store.read_json(chain.gen_relpath(self.head()) + "/rules.json")

    def head(self):
        return sil.read_head(self.store)["entry"]

    def new_digest(self, name="example"):
        return skill_manifest.skill_digest(
            [
                {
                    "path": "skills/%s/%s" % (name, k),
                    "sha256": sha256(v.encode("utf-8")),
                    "exec": False,
                }
                for k, v in fixture.skill_files(name).items()
            ]
        )

    def committed_digest(self, name="example"):
        document = self.store.read_json(chain.document_relpath(self.head()))
        files = [e for e in document if e["path"].startswith("skills/%s/" % name)]
        return skill_manifest.skill_digest(files)

    def install_op(self, name="example"):
        return {
            "op": "install-skill",
            "name": name,
            "files": fixture.skill_files(name),
        }

    def land(self, ops):
        pid = proposals.propose(self.S, ops)["proposal"]
        operator.approve(self.S, pid)
        return proposals.commit(self.S, pid)

    def pending(self, pid):
        return pid in proposals.read_auth(self.store)["proposals"]

    def commit(self, changes):
        sil.commit_generation(
            self.store,
            changes=changes,
            authorization=sil.operator_act_located(
                self.store, "approve", binding="op-1", rule="OC-001(b)"
            ),
        )

    def test_install_and_allow_in_one_proposal(self):
        lifecycle.start(self.S)
        self.land(
            [
                self.install_op(),
                {"op": "allow-skill", "name": "example", "digest": self.new_digest()},
            ]
        )
        self.assertEqual(
            self.rules()["skills"]["example"],
            {"rule": "allow", "digest": self.new_digest()},
        )
        self.assertEqual(self.new_digest(), self.committed_digest())
        lifecycle.stop(self.S)
        lifecycle.start(self.S)
        self.assertEqual(execution.invoke_skill(self.S, "example")["outcome"], "done")

    def test_allow_of_an_installed_skill(self):
        lifecycle.start(self.S)
        self.land([self.install_op()])
        self.land(
            [
                {
                    "op": "allow-skill",
                    "name": "example",
                    "digest": self.committed_digest(),
                }
            ]
        )
        self.assertEqual(
            self.rules()["skills"]["example"],
            {"rule": "allow", "digest": self.committed_digest()},
        )

    def test_allow_with_another_digest_is_refused_at_commit(self):
        lifecycle.start(self.S)
        h = self.head()
        pid = proposals.propose(
            self.S,
            [
                self.install_op(),
                {
                    "op": "allow-skill",
                    "name": "example",
                    "digest": "sha256:" + "0" * 64,
                },
            ],
        )["proposal"]
        operator.approve(self.S, pid)
        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "rule-target")
        self.assertEqual(self.head(), h)
        self.assertTrue(self.pending(pid))

    def test_allow_of_an_absent_skill_is_refused(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            self.land(
                [
                    {
                        "op": "allow-skill",
                        "name": "absent",
                        "digest": self.new_digest("absent"),
                    }
                ]
            )
        self.assertEqual(ctx.exception.check, "rule-target")

    def test_deny_replaces_an_allow_and_names_no_digest(self):
        lifecycle.start(self.S)
        self.land(
            [
                self.install_op(),
                {"op": "allow-skill", "name": "example", "digest": self.new_digest()},
            ]
        )
        self.land([{"op": "deny-skill", "name": "example"}])
        self.assertEqual(self.rules()["skills"]["example"], {"rule": "deny"})

    def test_deny_of_a_skill_not_installed(self):
        lifecycle.start(self.S)
        self.land([{"op": "deny-skill", "name": "later"}])
        self.assertEqual(self.rules()["skills"]["later"], {"rule": "deny"})

    def test_unset_removes_the_entry_and_keeps_the_rest(self):
        lifecycle.start(self.S)
        self.land(
            [
                self.install_op(),
                {"op": "allow-skill", "name": "example", "digest": self.new_digest()},
            ]
        )
        self.land([{"op": "unset-skill", "name": "example"}])
        self.assertNotIn("example", self.rules()["skills"])
        self.assertEqual(self.rules()["default"], "hold")
        self.assertEqual(self.rules()["domains"], {})

    def test_unset_of_an_absent_entry_is_refused(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            self.land([{"op": "unset-skill", "name": "example"}])
        self.assertEqual(ctx.exception.check, "rule-target")

    def test_one_entry_named_twice_is_refused_at_propose(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            proposals.propose(
                self.S,
                [
                    {"op": "deny-skill", "name": "x"},
                    {"op": "unset-skill", "name": "x"},
                ],
            )
        self.assertEqual(ctx.exception.check, "rule-target")
        self.assertEqual(proposals.read_auth(self.store)["proposals"], {})
        last = lifecycle.observe_log(self.S, kind="refusal")["records"][-1]
        self.assertEqual(last["check"], "rule-target")

    def test_malformed_rule_ops_are_refused(self):
        lifecycle.start(self.S)
        cases = [
            {"op": "allow-skill", "name": "example"},
            {"op": "allow-skill", "name": "example", "digest": "abc"},
            {"op": "allow-skill", "name": "Bad Name", "digest": self.new_digest()},
            {"op": "deny-skill"},
            {"op": "unset-skill", "name": 7},
        ]
        for op in cases:
            with self.subTest(op=op):
                with self.assertRaises(Refused) as ctx:
                    proposals.propose(self.S, [op])
                self.assertEqual(ctx.exception.check, "ops")

    def test_two_pending_proposals_compose(self):
        lifecycle.start(self.S)
        self.land([self.install_op("a"), self.install_op("b")])
        pa = proposals.propose(
            self.S,
            [
                {
                    "op": "allow-skill",
                    "name": "a",
                    "digest": self.committed_digest("a"),
                }
            ],
        )["proposal"]
        pb = proposals.propose(
            self.S,
            [
                {
                    "op": "allow-skill",
                    "name": "b",
                    "digest": self.committed_digest("b"),
                }
            ],
        )["proposal"]
        operator.approve(self.S, pa)
        operator.approve(self.S, pb)
        proposals.commit(self.S, pa)
        proposals.commit(self.S, pb)
        skills = self.rules()["skills"]
        self.assertEqual(
            skills["a"], {"rule": "allow", "digest": self.committed_digest("a")}
        )
        self.assertEqual(
            skills["b"], {"rule": "allow", "digest": self.committed_digest("b")}
        )

    def test_a_window_on_rules_covers_rule_ops(self):
        lifecycle.start(self.S)
        g = operator.grant(self.S, expiry="+1h", budget=5, scope="rules")["grant"]
        pid = proposals.propose(self.S, [{"op": "deny-skill", "name": "x"}])["proposal"]
        self.assertEqual(proposals.commit(self.S, pid)["authorization"], g)

    def test_install_and_allow_need_an_approval_under_windows(self):
        lifecycle.start(self.S)
        operator.grant(self.S, expiry="+1h", budget=5, scope="skills.install")
        operator.grant(self.S, expiry="+1h", budget=5, scope="rules")
        pid = proposals.propose(
            self.S,
            [
                self.install_op(),
                {"op": "allow-skill", "name": "example", "digest": self.new_digest()},
            ],
        )["proposal"]
        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "authorization")

    def test_rules_that_cannot_be_read_refuse_the_commit(self):
        self.commit(
            {"rules.json": canonical({"default": "hold", "domains": {}, "skills": []})}
        )
        lifecycle.start(self.S)
        pid = proposals.propose(self.S, [{"op": "deny-skill", "name": "x"}])["proposal"]
        operator.approve(self.S, pid)
        with self.assertRaises(Refused) as ctx:
            proposals.commit(self.S, pid)
        self.assertEqual(ctx.exception.check, "rule-target")

    def test_allow_deny_and_unset_domains(self):
        lifecycle.start(self.S)
        self.land([{"op": "allow-domain", "domain": "example.com"}])
        self.assertEqual(self.rules()["domains"], {"example.com": {"rule": "allow"}})
        self.land([{"op": "deny-domain", "domain": "http://example.com"}])
        self.assertEqual(
            self.rules()["domains"],
            {
                "example.com": {"rule": "allow"},
                "http://example.com": {"rule": "deny"},
            },
        )
        self.land([{"op": "unset-domain", "domain": "example.com"}])
        self.assertEqual(
            self.rules()["domains"], {"http://example.com": {"rule": "deny"}}
        )
        self.assertEqual(self.rules()["skills"], {})

    def test_unset_of_an_absent_domain_is_refused(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            self.land([{"op": "unset-domain", "domain": "example.com"}])
        self.assertEqual(ctx.exception.check, "rule-target")

    def test_malformed_domain_ops_are_refused(self):
        lifecycle.start(self.S)
        cases = [
            {"op": "allow-domain"},
            {"op": "allow-domain", "domain": 7},
            {"op": "allow-domain", "domain": "Example.com"},
            {"op": "allow-domain", "domain": "example.com."},
            {"op": "allow-domain", "domain": "localhost"},
            {"op": "allow-domain", "domain": "1.2.3.4"},
            {"op": "allow-domain", "domain": "*.github.io"},
            {"op": "allow-domain", "domain": "https://example.com"},
            {"op": "allow-domain", "domain": "example.com:443"},
            {"op": "allow-domain", "domain": "http://Example.com"},
        ]
        for op in cases:
            with self.subTest(op=op):
                with self.assertRaises(Refused) as ctx:
                    proposals.propose(self.S, [op])
                self.assertEqual(ctx.exception.check, "ops")

    def test_a_domain_named_twice_is_refused_at_propose(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            proposals.propose(
                self.S,
                [
                    {"op": "allow-domain", "domain": "example.com"},
                    {"op": "deny-domain", "domain": "example.com"},
                ],
            )
        self.assertEqual(ctx.exception.check, "rule-target")
        self.assertEqual(proposals.read_auth(self.store)["proposals"], {})

    def test_a_skill_and_a_domain_of_the_same_text_are_two_entries(self):
        lifecycle.start(self.S)
        self.land(
            [
                {"op": "deny-skill", "name": "example.com"},
                {"op": "deny-domain", "domain": "example.com"},
            ]
        )
        self.assertEqual(self.rules()["skills"]["example.com"], {"rule": "deny"})
        self.assertEqual(self.rules()["domains"]["example.com"], {"rule": "deny"})

    def test_domain_ops_are_of_category_rules(self):
        lifecycle.start(self.S)
        proposals.propose(self.S, [{"op": "allow-domain", "domain": "example.com"}])
        last = lifecycle.observe_log(self.S, kind="proposal")["records"][-1]
        self.assertEqual(last["categories"], ["rules"])

    def test_adapter_allow_domain(self):
        run_adapter("lifecycle", "start", "--store", self.S)
        ops_file = self.p("ops.json")
        with open(ops_file, "w", encoding="utf-8") as f:
            json.dump([{"op": "allow-domain", "domain": "example.com"}], f)
        code, out = run_adapter(
            "entity", "propose", "--store", self.S, "--ops", ops_file
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        pid = out["detail"]["proposal"]

        code, out = run_adapter(
            "operator", "approve", "--store", self.S, "--proposal", pid
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")

        code, out = run_adapter(
            "entity", "commit", "--store", self.S, "--proposal", pid
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(self.rules()["domains"], {"example.com": {"rule": "allow"}})

    def test_adapter_allow_skill(self):
        run_adapter("lifecycle", "start", "--store", self.S)
        ops_file = self.p("ops.json")
        with open(ops_file, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {"op": "install-skill", "name": "example"},
                    {
                        "op": "allow-skill",
                        "name": "example",
                        "digest": self.new_digest(),
                    },
                ],
                f,
            )
        code, out = run_adapter(
            "entity", "propose", "--store", self.S, "--ops", ops_file
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        pid = out["detail"]["proposal"]

        code, out = run_adapter(
            "operator", "approve", "--store", self.S, "--proposal", pid
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")

        code, out = run_adapter(
            "entity", "commit", "--store", self.S, "--proposal", pid
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(self.rules()["skills"]["example"]["rule"], "allow")
