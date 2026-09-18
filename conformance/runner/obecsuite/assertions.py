"""The assertion vocabulary of TESTS.md.

Every assertion raises StepFailure with a message naming what was expected and
what arrived. The runner catches it per step.
"""

from .result import StepFailure


def _fail(msg: str):
    raise StepFailure(msg)


def accepted(res, why: str = ""):
    if res.outcome != "accepted":
        _fail(f"expected accepted{' — ' + why if why else ''}, got "
              f"{res.outcome!r} {res.refusal or ''}")


def refused(ctx, res, check: str = None, rule: str = None, why: str = ""):
    """The refusal triple of TESTS.md §0.1.

    A refusal is not established by the operation being blocked. HC-008(d)
    requires the rejection to carry the check that produced it and to be
    logged, so a correct block that cannot name itself fails this assertion.
    """
    if res.outcome != "refused":
        _fail(f"expected refused{' — ' + why if why else ''}, got {res.outcome!r}")

    got_check = res.refusal.get("check")
    if not got_check:
        _fail("refused without naming a check (HC-008(d))")
    if check and check not in got_check:
        _fail(f"refused by {got_check!r}, expected {check!r}")

    if rule:
        got_rule = res.refusal.get("rule", "")
        if rule not in got_rule:
            _fail(f"refusal cites {got_rule!r}, expected {rule!r}")

    if not res.log_records:
        _fail("refused without log records (HC-008(d))")
    unresolved = ctx.unresolved_log_records(res)
    if unresolved:
        _fail(f"log records do not resolve through `observe log`: {unresolved}")


def equal(got, want, why: str = ""):
    if got != want:
        _fail(f"{why + ': ' if why else ''}expected {want!r}, got {got!r}")


def truthy(value, why: str):
    if not value:
        _fail(f"expected true: {why}")


def falsy(value, why: str):
    if value:
        _fail(f"expected false: {why}")


def gates_ordered(res, first: str, before: tuple):
    """`first` must be the first gate, and `before[0]` must precede
    `before[1]`. Both orderings are load-bearing in HC-010."""
    gates = [g.get("gate", "") for g in (res["gates"] or [])]
    if not gates:
        _fail("start returned no gate list")
    if first not in gates[0]:
        _fail(f"first gate is {gates[0]!r}, expected {first!r}")
    a, b = before
    ia = next((i for i, g in enumerate(gates) if a in g), None)
    ib = next((i for i, g in enumerate(gates) if b in g), None)
    if ia is None or ib is None:
        _fail(f"gate list missing {a!r} or {b!r}: {gates}")
    if ia >= ib:
        _fail(f"{a!r} must run before {b!r}; got {gates}")


def has_evidence(res, why: str):
    """Attested steps are recorded, not asserted — but an attestation without
    a pointer into the implementation's source is unestablished, not passed."""
    ev = res["evidence"]
    if not ev:
        _fail(f"attested without an evidence pointer: {why}")
    return ev
