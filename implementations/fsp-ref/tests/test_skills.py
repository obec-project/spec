# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Invoking a skill: the gates, the verified copy, the Operator's rule and the
end of the skill's process group (OC-008, D51, D16, DESIGN §5)."""

from __future__ import annotations

import json
import os
import shutil
import signal
import time
import unittest
from unittest import mock

from helpers import TempDirTest, run_adapter

from fsp import chain, ledger, lifecycle, operator, sil
from fsp import exec as execution
from fsp import manifest as skill_manifest
from fsp.digest import canonical
from fsp.sil import Refused
from fsp.store import Store
from fsp_testing import fixture


class SkillTests(TempDirTest):
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

    def alive(self, pid):
        deadline = time.monotonic() + 3
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            if time.monotonic() >= deadline:
                return True
            time.sleep(0.05)

    def test_an_allowed_skill_runs_and_is_logged(self):
        self.install()
        self.rule("example", "allow")
        lifecycle.start(self.S)
        out = execution.invoke_skill(self.S, "example")
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["exit"], 0)
        rec = lifecycle.observe_log(self.S, kind="execution")["records"][-1]
        self.assertEqual(rec["op"], "invoke-skill")
        self.assertEqual(rec["skill"], "example")
        self.assertEqual(rec["digest"], self.digest())

    def test_it_runs_in_the_workspace_from_a_copy_that_is_removed(self):
        self.install(
            run='pwd\necho "$1"\n',
            argv=["sh", "{skill}/run.sh", "{skill}"],
        )
        self.rule("example", "allow")
        lifecycle.start(self.S)
        out = execution.invoke_skill(self.S, "example")
        lines = out["stdout"].decode("utf-8").splitlines()
        self.assertEqual(lines[0], os.path.realpath(self.W))
        copy = lines[1]
        self.assertFalse(copy.startswith(os.path.realpath(self.S) + os.sep))
        self.assertFalse(os.path.exists(copy))

    def test_an_unindexed_skill_is_refused(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "absent")
        self.assertEqual(ctx.exception.check, "skill-index")

    def test_the_boundary_comes_before_the_index(self):
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "absent", target=self.p("outside.txt"))
        self.assertEqual(ctx.exception.check, "workspace-boundary")

    def test_a_file_changed_after_the_start_is_refused(self):
        self.install()
        self.rule("example", "allow")
        lifecycle.start(self.S)
        gen = self.store.read_json(lifecycle.INDEX)["generation"]
        with open(
            self.store.path("structural/gen/%d/skills/example/run.sh" % gen), "ab"
        ) as f:
            f.write(b"#\n")
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "example")
        self.assertEqual(ctx.exception.check, "skill-manifest")

    def test_a_skill_not_allowed_is_held_and_refused(self):
        self.install()
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "example")
        self.assertEqual(ctx.exception.check, "operator-rule")
        self.assertEqual(self.refusal()["reason"], "hold")

    def test_an_allow_for_another_digest_holds(self):
        self.install()
        self.rule("example", "allow", digest="sha256:" + "0" * 64)
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "example")
        self.assertEqual(ctx.exception.check, "operator-rule")
        self.assertEqual(self.refusal()["reason"], "hold")

    def test_a_denied_skill_is_refused(self):
        self.install()
        self.rule("example", "deny")
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "example")
        self.assertEqual(ctx.exception.check, "operator-rule")
        self.assertEqual(self.refusal()["reason"], "deny")

    def test_a_declared_target_leaving_the_workspace_is_refused(self):
        os.makedirs(self.p("outside"))
        os.symlink(self.p("outside"), os.path.join(self.W, "link"))
        self.install(targets=["link"])
        self.rule("example", "allow")
        lifecycle.start(self.S)
        with self.assertRaises(Refused) as ctx:
            execution.invoke_skill(self.S, "example")
        self.assertEqual(ctx.exception.check, "workspace-boundary")

    def test_a_timeout_ends_the_process_group(self):
        self.install(
            run='sleep 30 >/dev/null 2>&1 &\necho $! > "$HOME/child.pid"\nsleep 30\n',
            timeout_s=1,
        )
        self.rule("example", "allow")
        lifecycle.start(self.S)
        t = time.monotonic()
        out = execution.invoke_skill(self.S, "example")
        self.assertEqual(out["outcome"], "timeout")
        self.assertLess(time.monotonic() - t, 10)
        with open(os.path.join(self.W, "child.pid")) as f:
            child = int(f.read())
        self.assertFalse(self.alive(child))

    def test_nothing_the_skill_started_outlives_it(self):
        self.install(
            run='sleep 30 >/dev/null 2>&1 &\necho $! > "$HOME/child.pid"\nexit 0\n'
        )
        self.rule("example", "allow")
        lifecycle.start(self.S)
        out = execution.invoke_skill(self.S, "example")
        self.assertEqual(out["outcome"], "done")
        with open(os.path.join(self.W, "child.pid")) as f:
            child = int(f.read())
        self.assertFalse(self.alive(child))

    def recorded_pid(self, filename):
        """The PID the skill wrote to ``filename`` in the workspace."""
        with open(os.path.join(self.W, filename)) as f:
            return int(f.read())

    def kill_recorded(self, filename, group=False):
        """Cleanup: SIGKILL the PID the skill wrote to ``filename`` in the
        workspace, or the group it leads; nothing if the file was not written."""
        try:
            pid = self.recorded_pid(filename)
        except FileNotFoundError:
            return
        try:
            if group:
                os.killpg(pid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def test_the_output_is_returned(self):
        self.install(run="printf out; printf err >&2\n")
        self.rule("example", "allow")
        lifecycle.start(self.S)
        out = execution.invoke_skill(self.S, "example")
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["stdout"], b"out")
        self.assertEqual(out["stderr"], b"err")

    def test_an_endless_output_is_kept_bounded(self):
        self.install(run="yes\n", timeout_s=1)
        self.rule("example", "allow")
        lifecycle.start(self.S)
        t = time.monotonic()
        out = execution.invoke_skill(self.S, "example")
        self.assertEqual(out["outcome"], "timeout")
        self.assertEqual(len(out["stdout"]), execution.OUTPUT_CAP)
        self.assertLess(time.monotonic() - t, 10)

    def test_a_large_output_is_cut_and_the_skill_completes(self):
        self.install(run="head -c 1000000 /dev/zero; head -c 1000000 /dev/zero >&2\n")
        self.rule("example", "allow")
        lifecycle.start(self.S)
        out = execution.invoke_skill(self.S, "example")
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(len(out["stdout"]), execution.OUTPUT_CAP)
        self.assertEqual(len(out["stderr"]), execution.OUTPUT_CAP)

    def test_a_skill_that_closes_its_output_still_ends_at_its_limit(self):
        self.install(run="exec >/dev/null 2>&1\nsleep 30\n", timeout_s=1)
        self.rule("example", "allow")
        lifecycle.start(self.S)
        t = time.monotonic()
        out = execution.invoke_skill(self.S, "example")
        self.assertEqual(out["outcome"], "timeout")
        self.assertLess(time.monotonic() - t, 10)

    @unittest.skipUnless(shutil.which("setsid"), "setsid not found")
    def test_a_descendant_that_left_the_group_does_not_hold_the_call(self):
        self.install(
            run='setsid sleep 30 &\necho $! > "$HOME/held.pid"\nexit 0\n',
            timeout_s=1,
        )
        self.rule("example", "allow")
        lifecycle.start(self.S)
        self.addCleanup(self.kill_recorded, "held.pid")
        t = time.monotonic()
        out = execution.invoke_skill(self.S, "example")
        self.assertEqual(out["outcome"], "timeout")
        self.assertLess(time.monotonic() - t, 10)

    def test_a_process_not_reaped_by_the_watchdog_is_critical(self):
        self.install(
            run='echo $$ > "$HOME/skill.pid"\nsleep 30\n',
            timeout_s=1,
        )
        self.rule("example", "allow")
        lifecycle.start(self.S)
        self.addCleanup(self.kill_recorded, "skill.pid", True)
        with mock.patch.object(execution, "_end_group", lambda pid: None):
            with mock.patch.object(execution, "WATCHDOG_GRACE_S", 0.5):
                with mock.patch.object(execution, "_run", wraps=execution._run) as run:
                    with self.assertRaises(Refused) as ctx:
                        execution.invoke_skill(self.S, "example")
        self.assertEqual(ctx.exception.check, "vital-critical")
        critical = lifecycle.observe_log(self.S, kind="vital-critical")["records"][-1]
        self.assertEqual(critical["findings"][0]["type"], "watchdog")
        rec = lifecycle.observe_log(self.S, kind="execution")["records"][-1]
        self.assertEqual(rec["outcome"], "timeout")
        self.assertIsNone(rec.get("exit"))
        self.assertFalse(Store(self.S).exists(lifecycle.CREDENTIAL))
        # The launched process is ended and reaped here: left running, its Popen
        # would warn as it is finalized.
        proc = run.call_args.args[0]
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()

    def test_an_irreversible_skill_goes_through_the_ledger(self):
        self.install(irreversible=True)
        self.rule("example", "allow")
        lifecycle.start(self.S)
        execution.invoke_skill(self.S, "example")
        records, _ = self.store.read_jsonl(ledger.LEDGER)
        self.assertEqual([r["kind"] for r in records], ["open", "resolve"])
        self.assertEqual(records[0]["op"], "invoke-skill")
        self.assertEqual(records[1]["outcome"], "done")

    def test_adapter_invoke_skill(self):
        self.install()
        self.rule("example", "allow")
        run_adapter("lifecycle", "start", "--store", self.S)

        code, out = run_adapter(
            "entity", "invoke-skill", "--store", self.S, "--name", "example"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "accepted")
        self.assertEqual(
            out["detail"], {"skill": "example", "outcome": "done", "exit": 0}
        )

        code, out = run_adapter(
            "entity", "invoke-skill", "--store", self.S, "--name", "absent"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(out["refusal"]["check"], "skill-index")

        code, _ = run_adapter("entity", "invoke-skill", "--store", self.S)
        self.assertEqual(code, 1)
