# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The UI: ``fsp run``, a line REPL over the owners' functions (D93). The
process holds its session by the credential's lock and suspends it on a
signal or at the end of input (D92)."""

from __future__ import annotations

import argparse
import json
import os
import queue
import select
import shlex
import signal
import sys
import termios
import threading
import traceback
import tty

from . import channel, context, cycle, lifecycle, mil, model, operator, proposals
from .sil import Refused
from .store import Store

try:
    import readline  # line editing for input(), where the platform has it
except ImportError:
    readline = None

_SIGNALS = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)

_USAGE = {
    "model": "/model NAME [--num-ctx N] [--endpoint URL]",
    "work": "/work set PATH",
    "grant": "/grant SCOPE --for T --budget N",
    "clear": "/clear",
    "compact": "/compact",
    "new": "/new",
    "resume": "/resume ID",
    "inject": "/inject ID [RECORD...]",
    "retract": "/retract ID",
    "allow": "/allow domain D | /allow skill N",
    "deny": "/deny domain D | /deny skill N",
    "review": "/review",
    "notifications": "/notifications [ack]",
    "exit": "/exit",
    "help": "/help",
}
_NOT_YET = ("agenda",)
_REPLAY_TURNS = 3
_PERSONA_CHARS = 200
_DIGEST_CHARS = 12

# The terminal state of stdin while a menu is drawn; None otherwise (D97).
_saved_termios = None


class _Usage(Exception):
    """A known command given arguments it does not take."""


def _say(text):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def _refused(e):
    _say("System: refused (%s): %s" % (e.check, e.detail))


def _plain(text, keep=""):
    """``text`` with every control character but those in ``keep`` made a
    space, so what the entity wrote cannot move the cursor or the menu."""
    return "".join(c if c.isprintable() or c in keep else " " for c in str(text))


def _op_line(op):
    """One line for a proposal's op (D97)."""
    name = op.get("op")
    if name == "set-persona":
        text = str(op.get("content", ""))[:_PERSONA_CHARS]
        return "set-persona %s" % text.replace("\n", " ")
    if name == "install-skill":
        files = op.get("files")
        names = ", ".join(sorted(files)) if isinstance(files, dict) else ""
        return "install-skill %s (%s)" % (op.get("name"), names)
    if name in proposals.DOMAIN_OPS:
        return "%s %s" % (name, op.get("domain"))
    if name == "allow-skill":
        digest = str(op.get("digest", ""))[:_DIGEST_CHARS]
        return "allow-skill %s %s" % (op.get("name"), digest)
    if name in proposals.RULE_OPS:
        return "%s %s" % (name, op.get("name"))
    if name == "set-parameter":
        value = json.dumps(op.get("value"))
        return "set-parameter %s %s" % (op.get("name"), value)
    return json.dumps(op, sort_keys=True)


def _on_terminal():
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


class _LineReader:
    """The lines of one descriptor, read with ``os.read`` into a buffer (D100):
    nothing buffers a line the UI cannot see."""

    def __init__(self, fd):
        self.fd = fd
        self.buffer = b""
        self.eof = False

    def has_line(self):
        return b"\n" in self.buffer

    def fill(self):
        """One ``os.read`` into the buffer; the end of input is remembered."""
        try:
            data = os.read(self.fd, 65536)
        except OSError:
            data = b""
        if data:
            self.buffer += data
        else:
            self.eof = True

    def drain(self):
        """Read what the descriptor already holds, without waiting (D100)."""
        while not self.eof and select.select([self.fd], [], [], 0)[0]:
            self.fill()

    def take(self):
        """The first complete line of the buffer, without its newline."""
        line, _, self.buffer = self.buffer.partition(b"\n")
        return line.decode(getattr(sys.stdin, "encoding", None) or "utf-8", "replace")

    def readline(self):
        """The next line, waiting for it. ``EOFError`` at the end of input."""
        while not self.has_line() and not self.eof:
            self.fill()
        if self.has_line():
            return self.take()
        if self.buffer:
            self.buffer += b"\n"
            return self.take()
        raise EOFError

    def ready(self, timeout):
        """Whether a complete line is buffered, or arrives within ``timeout``
        seconds."""
        if not self.has_line() and not self.eof:
            if select.select([self.fd], [], [], timeout)[0]:
                self.fill()
        return self.has_line()


_stdin = _LineReader(0)


def _input(prompt):
    """A line from the Operator: the line the reader holds, else ``input()``
    on a terminal, else the line reader over descriptor 0 (D100).
    ``EOFError`` at the end of input."""
    if _stdin.has_line():
        sys.stdout.write(prompt)
        sys.stdout.flush()
        return _stdin.take()
    if _on_terminal():
        return input(prompt)
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return _stdin.readline()


def _read_key(fd):
    """One key from ``fd``: a byte, or an escape sequence; ``EOFError`` at the
    end of input."""
    key = os.read(fd, 1)
    if not key:
        raise EOFError
    if key == b"\x1b":
        while len(key) < 3 and select.select([fd], [], [], 0.05)[0]:
            more = os.read(fd, 1)
            if not more:
                break
            key += more
    return key


def _draw_menu(question, options, current, redraw):
    lines = ["\r\x1b[2K%s\n" % question]
    for i, option in enumerate(options):
        label = "  %d) %s" % (i + 1, option)
        if i == current:
            label = "\x1b[7m%s\x1b[0m" % label
        lines.append("\r\x1b[2K%s\n" % label)
    up = "\x1b[%dA" % (len(options) + 1) if redraw else ""
    sys.stdout.write(up + "".join(lines))
    sys.stdout.flush()


def _choose_on_terminal(question, options):
    global _saved_termios
    fd = sys.stdin.fileno()
    _saved_termios = termios.tcgetattr(fd)
    current = 0
    try:
        tty.setcbreak(fd)
        _draw_menu(question, options, current, False)
        while True:
            key = _read_key(fd)
            if key in (b"\x1b[A", b"\x1bOA"):
                current = (current - 1) % len(options)
            elif key in (b"\x1b[B", b"\x1bOB"):
                current = (current + 1) % len(options)
            elif key in (b"\r", b"\n"):
                break
            elif key == b"\x04":
                raise EOFError
            elif key.isdigit() and 1 <= int(key) <= min(len(options), 9):
                current = int(key) - 1
                break
            else:
                continue
            _draw_menu(question, options, current, True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, _saved_termios)
        _saved_termios = None
    sys.stdout.write("\x1b[%dA\x1b[J" % (len(options) + 1))
    _say("%s → %s" % (question, options[current]))
    return current


def choose(question, options) -> int:
    """The index of the option the Operator chooses, from a menu drawn in the
    prompt (D97). Main thread only. ``EOFError`` at the end of input."""
    if _on_terminal():
        return _choose_on_terminal(question, options)
    _say(question)
    for i, option in enumerate(options):
        _say("  %d) %s" % (i + 1, option))
    count = len(options)
    while True:
        answer = _input("choose [1-%d]: " % count).strip()
        if answer.isdigit() and 1 <= int(answer) <= count:
            return int(answer) - 1
        _say("System: choose a number from 1 to %d" % count)


def ask_text(prompt, prefill) -> str:
    """A line of text, the line filled with ``prefill`` where the terminal
    allows it (D97). Main thread only. ``EOFError`` at the end of input."""
    if readline is not None and _on_terminal():
        readline.set_startup_hook(lambda: readline.insert_text(prefill))
        try:
            return input(prompt)
        finally:
            readline.set_startup_hook()
    _say("(current: %s)" % prefill)
    return _input(prompt) or prefill


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
        self.requests = queue.Queue()
        self.direct = False
        self.pending_line = None
        self.interrupted = None

    # -- suspend and exit (D92) ------------------------------------------

    def suspend_and_exit(self, signum):
        """Suspend the session this process holds and end the process, from
        the signal handler and from the end of input. The terminal's state is
        restored first (D97); the exit is taken inside the store's write
        lock, which the process never releases."""
        if self.suspending:
            return
        self.suspending = True
        channel.clear()
        for s in _SIGNALS:
            signal.signal(s, signal.SIG_IGN)
        saved = _saved_termios
        if saved is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, saved)
            except (OSError, ValueError, termios.error):
                pass
        code = 128 + signum if signum else 0
        if not self.starting:
            os._exit(code)
        name = signal.Signals(signum).name if signum else None
        with Store(self.root).write_lock():
            if self.interrupted is not None:
                try:
                    cycle.discard_results(self.root, *self.interrupted)
                except Exception:
                    pass
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
        _stdin.drain()
        t.start()
        while t.is_alive():
            try:
                if self.watching():
                    self.hold_line()
                    request = self.requests.get_nowait()
                else:
                    request = self.requests.get(timeout=0.2)
            except queue.Empty:
                continue
            self.answer(*request)
        if "error" in box:
            e = box["error"]
            traceback.print_exception(type(e), e, e.__traceback__)
            self.release()
            return 1
        return box.get("value")

    def watching(self):
        """Whether stdin is watched for a line: a chain runs, no line is held
        or read and waiting, and input has not ended (D100)."""
        return (
            self.responding.is_set()
            and self.pending_line is None
            and not _stdin.eof
            and not _stdin.has_line()
        )

    def hold_line(self):
        """Hold one line of stdin for the chain's boundary, waiting up to the
        wait loop's 0.2 s for it (D100). At most one line is held."""
        if _stdin.ready(0.2):
            self.pending_line = _stdin.take()

    def answer(self, kind, args, reply):
        """Answer a worker's request on the main thread. The end of input is a
        suspend (D92)."""
        try:
            value = choose(*args) if kind == "choose" else ask_text(*args)
        except EOFError:
            self.suspend_and_exit(None)
            return
        except BaseException as e:
            reply.put((False, e))
            return
        reply.put((True, value))

    def ask(self, kind, *args):
        """A menu (``"choose"``) or a line of text (``"text"``) for the
        Operator, asked from the worker and answered by the main thread
        (D97). Never called with the store's write lock held."""
        if self.direct:
            return choose(*args) if kind == "choose" else ask_text(*args)
        reply = queue.Queue()
        self.requests.put((kind, args, reply))
        ok, value = reply.get()
        if not ok:
            raise value
        return value

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

    def open(self, replay=True):
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
        channel.register(self._answer_hold)
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
        if not replay:
            return None
        self.show_notices()
        for turn in recent[-_REPLAY_TURNS:]:
            for record in turn:
                if record.get("kind") == "stimulus":
                    _say("> %s" % record.get("text", ""))
                elif record.get("kind") == "reply":
                    _say(record.get("text", ""))
        code = self._apply_waiting()
        if code is not None:
            return code
        return self._offer_review()

    # -- a hold (D99) ------------------------------------------------------

    def _answer_hold(self, hold):
        """Put a hold of the execution path to the Operator, from the worker
        that dispatches the act, and apply the answer (D99). Returns the
        answer."""
        _say("System: hold %s" % hold["id"])
        _say("System:   asked by: %s" % _plain(hold["asker"]))
        _say("System:   operation: %s" % _plain(hold["op"]))
        _say("System:   target: %s" % _plain(hold["resolved"]))
        if hold["kind"] == "skill-path":
            _say("System:   its code may read or write there")
        listed = hold["kind"] in ("domain", "skill")
        answers = ["once", "chat"] + (["allowlist"] if listed else []) + ["deny"]
        labels = {
            "once": "Allow once",
            "chat": "Allow for this chat",
            "allowlist": "Add to the allowlist",
            "deny": "Deny",
        }
        choice = self.ask(
            "choose", "Hold %s" % hold["id"], [labels[a] for a in answers]
        )
        answer = answers[choice]
        try:
            operator.answer_hold(self.root, hold, answer, binding=self.binding)
        except Refused as e:
            _refused(e)
            return "deny"
        key = hold["key"]
        if answer == "chat":
            channel.allow_chat(key)
        elif answer in ("once", "allowlist"):
            channel.allow_once(key)
        if answer == "allowlist":
            try:
                operator.allow(self.root, hold["kind"], key[1], binding=self.binding)
            except Refused as e:
                _refused(e)
        return answer

    # -- the review and the rollover (D95, D97) --------------------------

    def _unapproved(self):
        """The pending proposals no approval names, in order of origination."""
        listing = operator.review_list(self.root, binding=self.binding)
        return [p for p in listing["proposals"] if not p["approved"]]

    def _offer_review(self):
        try:
            pending = self._unapproved()
        except Refused as e:
            _refused(e)
            return None
        if not pending:
            return None
        question = "%d proposal(s) pending" % len(pending)
        if self.ask("choose", question, ["Review now", "Later"]) == 0:
            self._review_proposals()
            return self._apply_waiting()
        return None

    def _apply_waiting(self):
        """Roll over when an authorized proposal waits (D95); the exit code
        when the next start fails, otherwise ``None``."""
        store = Store(self.root)
        with store.write_lock():
            waiting = proposals.waiting(store)
        if not waiting:
            return None
        _say("System: applying %d authorized change(s)" % len(waiting))
        closed = lifecycle.rollover(self.root, binding=self.binding)
        self.release()
        code = self.open(replay=False)
        if code is not None:
            return code
        for item in closed["endure"]["committed"]:
            _say("System: %s applied (entry %d)" % (item["proposal"], item["entry"]))
        for item in closed["endure"]["dropped"]:
            _say("System: refused (%s): %s" % (item["check"], item["detail"]))
        return None

    def _show_proposal(self, item, entry):
        if entry.get("origin") == "operator":
            origin = "operator"
        else:
            origin = "entity"
            if entry.get("session"):
                origin += ", session %s" % entry["session"]
            if entry.get("cycle"):
                origin += ", cycle %s" % entry["cycle"]
        _say("System: proposal %s" % item["proposal"])
        _say("System:   origin: %s" % origin)
        _say("System:   categories: %s" % ", ".join(item["categories"]))
        for op in entry.get("ops", []):
            _say("System:   %s" % _plain(_op_line(op)))

    def _review_proposals(self):
        """Each pending proposal no approval names, shown and decided; then the
        notices of commits a window made (D97)."""
        pending = self._unapproved()
        store = Store(self.root)
        with store.write_lock():
            auth = proposals.read_auth(store)
        for item in pending:
            pid = item["proposal"]
            self._show_proposal(item, auth["proposals"].get(pid, {}))
            choice = self.ask(
                "choose", "Proposal %s" % pid, ["Approve", "Reject", "Later"]
            )
            try:
                if choice == 0:
                    operator.approve(self.root, pid, binding=self.binding)
                    _say("System: approved %s" % pid)
                elif choice == 1:
                    operator.reject(self.root, pid, binding=self.binding)
                    _say("System: rejected %s" % pid)
            except Refused as e:
                _refused(e)
        found = operator.notifications(self.root, binding=self.binding)
        for rec in found["notifications"]:
            detail = rec.get("detail")
            if rec.get("condition") == "window-commit" and isinstance(detail, dict):
                _say(
                    "System: committed under window %s: %s (entry %s)"
                    % (detail.get("grant"), detail.get("proposal"), detail.get("entry"))
                )

    def _review_promotions(self):
        """Each requested promotion shown and decided; none can be left (D97,
        D80)."""
        listing = operator.review_list(self.root, binding=self.binding)
        for request in listing["promotions"]:
            pid = request["promotion"]
            _say("System: promotion %s" % pid)
            _say("System:   slug: %s" % _plain(request["slug"]))
            _say("System:   category: %s" % _plain(request["category"]))
            _say("System:   content:")
            _say(_plain(request["content"], keep="\n"))
            while True:
                choice = self.ask(
                    "choose",
                    "Promotion %s" % pid,
                    ["Approve", "Edit and approve", "Reject"],
                )
                try:
                    if choice == 0:
                        operator.approve_promotion(self.root, pid, binding=self.binding)
                    elif choice == 1:
                        text = self.ask("text", "content: ", request["content"])
                        edit = {
                            "slug": request["slug"],
                            "category": request["category"],
                            "content": text,
                        }
                        operator.approve_promotion(
                            self.root, pid, edit=edit, binding=self.binding
                        )
                    else:
                        operator.reject_promotion(self.root, pid, binding=self.binding)
                except Refused as e:
                    _refused(e)
                    if choice == 1:
                        continue
                break

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
        try:
            return self._apply_waiting()
        except Refused as e:
            _refused(e)
            return None

    def _to_review(self):
        """The ids of the proposals pending that no approval names and no
        authorization applies at the next boundary."""
        try:
            pending = {p["proposal"] for p in self._unapproved()}
            store = Store(self.root)
            with store.write_lock():
                waiting = set(proposals.waiting(store))
        except Refused:
            return set()
        return pending - waiting

    def handle(self, text):
        if not text:
            return None
        if text.startswith("//"):
            text = text[1:]
        elif text.startswith("/"):
            return self.command(text)
        before = self._to_review()
        self.responding.set()
        try:
            out = cycle.respond(
                self.root, text, interrupt=lambda: self.pending_line is not None
            )
        finally:
            self.responding.clear()
        for reply in out["replies"]:
            _say(reply)
        if out["aborted"]:
            _say("System: the cycle was aborted: %s" % out["aborted"])
        proposed = len(self._to_review() - before)
        if proposed:
            _say("System: the entity proposed %d change(s) — /review" % proposed)
        if out["interrupted"]:
            self._interrupted(out["interrupted"])
        return None

    def _interrupted(self, stop):
        """The Operator keeps or discards the results of the chain that
        stopped at a cycle boundary (D100, OP-002(a)(c))."""
        _say("System: the chain stopped at %s" % stop["cycle"])
        self.interrupted = (stop["cycle"], stop["results"])
        try:
            keep = self.ask(
                "choose",
                "The interrupted chain's results",
                ["Keep them in view", "Discard them"],
            )
            discarded = keep == 1
            with Store(self.root).write_lock():
                if discarded:
                    cycle.discard_results(self.root, *self.interrupted)
                self.interrupted = None
            if discarded:
                _say("System: results discarded")
        finally:
            self.interrupted = None

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

    def cmd_compact(self, args):
        if args:
            raise _Usage
        out = cycle.compact(self.root, reason="operator")
        done = sum(1 for o in out["saves"] if o.get("outcome") == "done")
        _say(
            "System: compacted: %d saved, %d refused" % (done, len(out["saves"]) - done)
        )

    def cmd_new(self, args):
        if args:
            raise _Usage
        out = operator.new_conversation(self.root, binding=self.binding)
        channel.clear()
        _say("System: session %s closed; a new conversation begins" % out["session"])
        self.release()
        return self.open()

    def cmd_resume(self, args):
        if len(args) != 1:
            raise _Usage
        out = operator.resume_conversation(self.root, args[0], binding=self.binding)
        channel.clear()
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

    def _structural(self, verb, args):
        if len(args) != 2 or args[0] not in ("domain", "skill"):
            raise _Usage
        act = operator.allow if verb == "allow" else operator.deny
        out = act(self.root, args[0], args[1], binding=self.binding)
        _say("System: recorded %s" % out["proposal"])

    def cmd_allow(self, args):
        self._structural("allow", args)

    def cmd_deny(self, args):
        self._structural("deny", args)

    def cmd_review(self, args):
        if args:
            raise _Usage
        if not self._unapproved():
            _say("System: no proposal pending")
        self._review_proposals()

    def cmd_exit(self, args):
        if args:
            raise _Usage
        emitted = cycle.emit_closure(self.root)
        recorded = operator.record_closure(
            self.root, emitted["payload"], binding=self.binding
        )
        for index in recorded["refused"]:
            _say("System: promotion %d refused by the probes" % index)
        self._review_proposals()
        self._review_promotions()
        out = operator.close_conversation(self.root, binding=self.binding)
        channel.clear()
        _say("System: session %s closed" % out["session"])
        self.release()
        return 0


def _review(args):
    """``fsp review``: the review of proposals, with no session (D97)."""
    root = os.path.abspath(args.store)
    if lifecycle.store_state(root) != "active":
        _say("System: %s is not an activated entity store" % root)
        return 1
    ui = _Ui(root, args.binding)
    ui.direct = True
    try:
        ui._review_proposals()
    except EOFError:
        return 0
    except KeyboardInterrupt:
        return 128 + signal.SIGINT
    except Refused as e:
        _refused(e)
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="fsp")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="open a session and read the Operator's lines")
    run.add_argument("--store", required=True, help="the entity store")
    run.add_argument("--binding", help="the Operator binding acting")
    review = sub.add_parser("review", help="review the proposals pending")
    review.add_argument("--store", required=True, help="the entity store")
    review.add_argument("--binding", help="the Operator binding acting")
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    if args.command == "review":
        return _review(args)
    ui = _Ui(os.path.abspath(args.store), args.binding)
    for s in _SIGNALS:
        signal.signal(s, lambda signum, frame: ui.suspend_and_exit(signum))
    try:
        code = ui.work(ui.begin)
        while code is None:
            if ui.pending_line is not None:
                raw, ui.pending_line = ui.pending_line, None
            else:
                try:
                    raw = _input("> ")
                except EOFError:
                    ui.suspend_and_exit(None)
                    return 0
            code = ui.work(lambda raw=raw: ui.line(raw))
    except Exception:
        traceback.print_exc()
        ui.release()
        return 1
    return code
