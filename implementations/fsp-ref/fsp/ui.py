# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The UI: ``fsp run``, a line REPL over the owners' functions (D93). The
process holds its session by the credential's lock and suspends it on a
signal or at the end of input (D92)."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import sys
import threading
import traceback

from . import context, cycle, lifecycle, mil, model, operator
from .sil import Refused
from .store import Store

try:
    import readline  # line editing for input(), where the platform has it
except ImportError:
    pass

_SIGNALS = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)

_USAGE = {
    "model": "/model NAME [--num-ctx N] [--endpoint URL]",
    "work": "/work set PATH",
    "grant": "/grant SCOPE --for T --budget N",
    "clear": "/clear",
    "new": "/new",
    "resume": "/resume ID",
    "inject": "/inject ID [RECORD...]",
    "retract": "/retract ID",
    "notifications": "/notifications [ack]",
    "exit": "/exit",
    "help": "/help",
}
_NOT_YET = ("allow", "deny", "review", "agenda", "compact")
_REPLAY_TURNS = 3


class _Usage(Exception):
    """A known command given arguments it does not take."""


def _say(text):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def _refused(e):
    _say("System: refused (%s): %s" % (e.check, e.detail))


def _flags(args, names):
    """``(positionals, flags)`` for ``args``, each flag in ``names`` taking one
    value and given once; ``None`` if ``args`` does not parse that way."""
    positional, flags = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            if a not in names or a in flags or i + 1 >= len(args):
                return None
            flags[a] = args[i + 1]
            i += 2
        else:
            positional.append(a)
            i += 1
    return positional, flags


class _Ui:
    def __init__(self, root, binding):
        self.root = root
        self.binding = binding
        self.session = None
        self.holder = None
        self.starting = False
        self.suspending = False
        self.responding = threading.Event()

    # -- suspend and exit (D92) ------------------------------------------

    def suspend_and_exit(self, signum):
        """Suspend the session this process holds and end the process, from
        the signal handler and from the end of input. The exit is taken
        inside the store's write lock, which the process never releases."""
        if self.suspending:
            return
        self.suspending = True
        for s in _SIGNALS:
            signal.signal(s, signal.SIG_IGN)
        code = 128 + signum if signum else 0
        if not self.starting:
            os._exit(code)
        name = signal.Signals(signum).name if signum else None
        with Store(self.root).write_lock():
            out = lifecycle.suspend(
                self.root, signal=name, chain=self.responding.is_set()
            )
            try:
                if out["suspended"]:
                    sys.stdout.write("System: suspended\n")
                sys.stdout.flush()
            except (OSError, ValueError, RuntimeError):
                pass
            os._exit(code)

    # -- the worker ------------------------------------------------------

    def work(self, fn):
        """Run ``fn`` in a worker thread and wait for it, the main thread free
        to take a signal. Returns its value; an exception that is not a
        refusal is a crash: the traceback, the hold released, no suspend."""
        box = {}

        def target():
            try:
                box["value"] = fn()
            except BaseException as e:
                box["error"] = e

        t = threading.Thread(target=target, daemon=True)
        t.start()
        while t.is_alive():
            t.join(0.2)
        if "error" in box:
            e = box["error"]
            traceback.print_exception(type(e), e, e.__traceback__)
            self.release()
            return 1
        return box.get("value")

    def release(self):
        holder, self.holder = self.holder, None
        if holder is not None:
            holder.release()

    # -- the open --------------------------------------------------------

    def begin(self):
        store = Store(self.root)
        crossing = operator.workspace_crossing(store, os.getcwd())
        if crossing is not None:
            ws, limit = crossing
            _say(
                "System: the folder %s crosses %s (D30); run fsp from the "
                "project's folder, with --store naming the store" % (ws, limit)
            )
            return 1
        return self.open()

    def open(self):
        self.starting = True
        try:
            res = lifecycle.start(self.root, binding=self.binding, hold=True)
        except lifecycle.CannotStart as e:
            _say("System: %s" % e)
            return 1
        if res.outcome != "accepted":
            failed = [g for g in res.gates if g["outcome"] != "pass"]
            where = ", ".join("%s: %s" % (g["gate"], g["outcome"]) for g in failed)
            _say("System: the start was %s (%s)" % (res.outcome, where))
            if res.refusal is not None:
                _say("System: %s" % res.refusal.detail)
            return 1
        self.holder = res.holder
        self.session = res.session
        workspace = None
        try:
            workspace = operator.set_workspace(
                self.root, os.getcwd(), binding=self.binding
            )["workspace"]
        except Refused as e:
            _refused(e)
        store = Store(self.root)
        with store.write_lock():
            conversation = mil.conversation_of(store, self.session)
            setting = model.setting(store)
            recent = context.turns(mil.transcript(store, self.session))
        if setting is None:
            in_force = "none"
        else:
            in_force = "%s (num_ctx %d)" % (setting["name"], setting["num_ctx"])
        _say(
            "System: session %s, conversation %s, model %s, workspace %s"
            % (self.session, conversation, in_force, workspace)
        )
        self.show_notices()
        for turn in recent[-_REPLAY_TURNS:]:
            for record in turn:
                if record.get("kind") == "stimulus":
                    _say("> %s" % record.get("text", ""))
                elif record.get("kind") == "reply":
                    _say(record.get("text", ""))
        return None

    def show_notices(self):
        notices = operator.notifications(self.root, binding=self.binding)
        found = notices["notifications"]
        _say("System: %d pending notices" % len(found))
        for rec in found:
            detail = rec.get("detail")
            if not isinstance(detail, str):
                detail = json.dumps(detail, sort_keys=True)
            _say("System:   %s %s: %s" % (rec.get("id"), rec.get("condition"), detail))

    # -- a line ----------------------------------------------------------

    def line(self, raw):
        try:
            code = self.handle(raw.strip())
        except Refused as e:
            _refused(e)
            code = None
        if code is not None:
            return code
        if lifecycle.live_session(self.root) != self.session:
            _say("System: the session ended")
            self.release()
            return 1
        return None

    def handle(self, text):
        if not text:
            return None
        if text.startswith("//"):
            text = text[1:]
        elif text.startswith("/"):
            return self.command(text)
        self.responding.set()
        try:
            out = cycle.respond(self.root, text)
        finally:
            self.responding.clear()
        for reply in out["replies"]:
            _say(reply)
        if out["aborted"]:
            _say("System: the cycle was aborted: %s" % out["aborted"])
        return None

    # -- the commands (§6.2) ---------------------------------------------

    def command(self, text):
        try:
            parts = shlex.split(text)
        except ValueError as e:
            _say("System: cannot read the command: %s" % e)
            return None
        name, args = parts[0][1:], parts[1:]
        if name in _NOT_YET:
            _say("System: /%s is not available yet" % name)
            return None
        if name not in _USAGE:
            _say("System: unknown command /%s" % name)
            return None
        try:
            return getattr(self, "cmd_" + name)(args)
        except _Usage:
            _say("System: usage: %s" % _USAGE[name])
            return None

    def cmd_help(self, args):
        if args:
            raise _Usage
        for usage in _USAGE.values():
            _say("System: %s" % usage)

    def cmd_model(self, args):
        parsed = _flags(args, ("--num-ctx", "--endpoint"))
        if parsed is None or len(parsed[0]) != 1:
            raise _Usage
        (name,), flags = parsed
        kwargs = {}
        if "--num-ctx" in flags:
            try:
                kwargs["num_ctx"] = int(flags["--num-ctx"])
            except ValueError:
                raise _Usage
        if "--endpoint" in flags:
            kwargs["endpoint"] = flags["--endpoint"]
        out = operator.set_model(self.root, name, binding=self.binding, **kwargs)
        value = out["model"]
        _say("System: model %s (num_ctx %d)" % (value["name"], value["num_ctx"]))

    def cmd_work(self, args):
        if len(args) != 2 or args[0] != "set":
            raise _Usage
        out = operator.set_workspace(
            self.root, os.path.abspath(args[1]), binding=self.binding
        )
        _say("System: workspace %s" % out["workspace"])

    def cmd_grant(self, args):
        parsed = _flags(args, ("--for", "--budget"))
        if parsed is None or len(parsed[0]) != 1 or len(parsed[1]) != 2:
            raise _Usage
        (scope,), flags = parsed
        out = operator.grant(
            self.root,
            scope=scope,
            expiry=flags["--for"],
            budget=flags["--budget"],
            binding=self.binding,
        )
        _say("System: grant %s" % out["grant"])

    def cmd_clear(self, args):
        if args:
            raise _Usage
        operator.clear_transcript(self.root, binding=self.binding)
        _say("System: transcript cleared")

    def cmd_new(self, args):
        if args:
            raise _Usage
        out = operator.new_conversation(self.root, binding=self.binding)
        _say("System: session %s closed; a new conversation begins" % out["session"])
        self.release()
        return self.open()

    def cmd_resume(self, args):
        if len(args) != 1:
            raise _Usage
        out = operator.resume_conversation(self.root, args[0], binding=self.binding)
        _say(
            "System: session %s closed; resuming conversation %s"
            % (out["session"], args[0])
        )
        self.release()
        return self.open()

    def cmd_inject(self, args):
        if not args:
            raise _Usage
        out = operator.inject_records(
            self.root, args[0], args[1:] or None, binding=self.binding
        )
        _say("System: injected %d records from %s" % (len(out["added"]), args[0]))

    def cmd_retract(self, args):
        if len(args) != 1:
            raise _Usage
        out = operator.retract_semantic(self.root, args[0], binding=self.binding)
        _say("System: retracted %s" % out["record"])

    def cmd_notifications(self, args):
        if not args:
            return self.show_notices()
        if args != ["ack"]:
            raise _Usage
        out = operator.acknowledge_notifications(self.root, binding=self.binding)
        _say("System: acknowledged %d notices" % len(out["acknowledged"]))

    def cmd_exit(self, args):
        if args:
            raise _Usage
        out = operator.exit_with_closure(self.root, binding=self.binding)
        _say("System: session %s closed" % out["session"])
        self.release()
        return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="fsp")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="open a session and read the Operator's lines")
    run.add_argument("--store", required=True, help="the entity store")
    run.add_argument("--binding", help="the Operator binding acting")
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    ui = _Ui(os.path.abspath(args.store), args.binding)
    for s in _SIGNALS:
        signal.signal(s, lambda signum, frame: ui.suspend_and_exit(signum))
    try:
        code = ui.work(ui.begin)
        while code is None:
            try:
                raw = input("> ")
            except EOFError:
                ui.suspend_and_exit(None)
                return 0
            code = ui.work(lambda raw=raw: ui.line(raw))
    except Exception:
        traceback.print_exc()
        ui.release()
        return 1
    return code
