"""The conformance adapter (ADAPTER.md). A driver over the same functions the
``fsp`` CLI uses; it adds no capability of its own (§1.1, §1.2).

Exit codes: 0 the command ran (a refusal included), 1 it could not be
attempted, 2 it is not implemented. ``inject`` exists only when the
``fsp_testing`` package is present (D6).
"""

from __future__ import annotations

import json
import os
import sys

from . import describe, sil
from .verify import verify

BARE_FLAGS = {"direct", "include-session"}


class NotImplementedCommand(Exception):
    pass


class CannotAttempt(Exception):
    pass


def parse_flags(argv):
    flags = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if not arg.startswith("--"):
            raise CannotAttempt("unexpected argument %r" % arg)
        name = arg[2:]
        if name in BARE_FLAGS:
            flags[name] = True
            i += 1
        else:
            if i + 1 >= len(argv):
                raise CannotAttempt("--%s needs a value" % name)
            flags[name] = argv[i + 1]
            i += 2
    return flags


def accepted(detail=None, log_records=()):
    return {"ok": True, "outcome": "accepted", "log_records": list(log_records), "detail": detail or {}}


def refused(exc: sil.Refused, detail=None):
    return {
        "ok": True,
        "outcome": "refused",
        "refusal": {
            "check": exc.check,
            "rule": exc.rule,
            "logged": bool(exc.log_records),
            "detail": exc.detail,
        },
        "log_records": exc.log_records,
        "detail": detail or {},
    }


def _store(flags):
    s = flags.get("store")
    if not s:
        raise CannotAttempt("--store is required")
    return os.path.abspath(s)


# -- describe ---------------------------------------------------------------


def describe_state(flags):
    return accepted(describe.state(_store(flags)))


# -- lifecycle --------------------------------------------------------------


def lifecycle_init(flags):
    operator = flags.get("operator")
    if not operator:
        raise CannotAttempt("--operator is required")
    try:
        out = sil.first_activation(_store(flags), operator)
    except sil.Refused as e:
        if not e.log_records:
            raise CannotAttempt(e.detail)
        return refused(e)
    return accepted(
        {"genesis_digest": out["genesis_digest"], "head_digest": out["head_digest"]},
        out["log_records"],
    )


def lifecycle_verify(flags):
    root = _store(flags)
    r = verify(root)
    detail = r.as_dict()
    detail["credential_issued"] = os.path.exists(os.path.join(root, "CREDENTIAL"))
    return accepted(detail)


# -- observe ----------------------------------------------------------------


def observe_chain(flags):
    root = _store(flags)
    r = verify(root)
    if r.state in ("absent", "foreign"):
        raise CannotAttempt("%s is not an fsp store" % root)
    entries = []
    for eid, body in r.entries:
        e = {"id": eid}
        e.update(body)
        entries.append(e)
    return accepted({"entries": entries, "chain_intact": r.chain_intact})


# -- inject (test builds only) ------------------------------------------------


def _inject(command):
    def run(flags):
        try:
            from fsp_testing import inject
        except ImportError:
            raise NotImplementedCommand("inject is absent from this build")
        fn = getattr(inject, command.replace("-", "_"), None)
        if fn is None:
            raise NotImplementedCommand("inject %s" % command)
        return fn(_store(flags), flags)

    return run


COMMANDS = {
    ("describe", "state"): describe_state,
    ("lifecycle", "init"): lifecycle_init,
    ("lifecycle", "verify"): lifecycle_verify,
    ("observe", "chain"): observe_chain,
    ("inject", "corrupt"): _inject("corrupt"),
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print("usage: obec-adapter <class> <command> [--flag value ...]", file=sys.stderr)
        return 1
    key = (argv[0], argv[1])
    fn = COMMANDS.get(key)
    if fn is None:
        print("not implemented: %s %s" % key, file=sys.stderr)
        return 2
    try:
        result = fn(parse_flags(argv[2:]))
    except NotImplementedCommand as e:
        print("not implemented: %s" % e, file=sys.stderr)
        return 2
    except CannotAttempt as e:
        print("cannot attempt: %s" % e, file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0
