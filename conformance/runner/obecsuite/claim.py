# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Claim emission.

A run produces two artifacts: machine-readable JSON, and the Markdown a human
submits. COMPLIANCE.md §3 lists what a claim must carry; this module is what
makes producing one mechanical rather than a writing exercise.
"""

import json
import platform
from datetime import datetime, timezone

from . import SUITE_VERSION, TARGETS
from .result import Outcome

_MARK = {
    Outcome.PASS: "pass",
    Outcome.FAIL: "**FAIL**",
    Outcome.ERROR: "**ERROR**",
    Outcome.UNESTABLISHED: "unestablished",
    Outcome.ATTESTED: "attested",
}


def conformant(results) -> bool:
    """Conformance requires every test to pass or be attested. An
    unestablished step is not a pass: COMPLIANCE.md §3 is explicit that
    partial conformance is not conformance, and "we could not tell" is not
    "it holds"."""
    return all(r.outcome in (Outcome.PASS, Outcome.ATTESTED) for r in results)


# Exit codes. 2 is argparse's usage error and stays that.
EXIT_CONFORMANT = 0
EXIT_FAIL = 1
EXIT_UNESTABLISHED = 3
EXIT_ERROR = 4


def exit_code(results) -> int:
    """Only 0 means conformant. The others say why not, in the precedence a
    test's own outcome uses: a run the adapter broke is incomplete, and says
    nothing reliable about failures; a failure outranks what could not be
    established. There is deliberately no way to turn 3 into 0 — "we could
    not tell" must not read as "it holds", not even to a CI script."""
    outcomes = {r.outcome for r in results}
    if Outcome.ERROR in outcomes:
        return EXIT_ERROR
    if Outcome.FAIL in outcomes:
        return EXIT_FAIL
    if Outcome.UNESTABLISHED in outcomes:
        return EXIT_UNESTABLISHED
    return EXIT_CONFORMANT


def as_json(results, ctx, meta: dict) -> dict:
    return {
        "suite_version": SUITE_VERSION,
        "targets": TARGETS,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runner_platform": platform.platform(),
        "adapter": meta.get("adapter"),
        "implementation": meta.get("implementation"),
        "conformant": conformant(results),
        "notes": ctx.notes,
        "tests": [
            {
                "rule": r.rule,
                "title": r.title,
                "outcome": r.outcome.value,
                "tally": r.tally(),
                "steps": [
                    {
                        "step": s.step,
                        "kind": s.kind,
                        "outcome": s.outcome.value,
                        "detail": s.detail,
                        "evidence": s.evidence,
                        "calls": s.calls,
                    }
                    for s in r.steps
                ],
            }
            for r in results
        ],
    }


def as_markdown(results, ctx, meta: dict) -> str:
    ok = conformant(results)
    totals = {o.value: 0 for o in Outcome}
    for r in results:
        for k, v in r.tally().items():
            totals[k] += v

    lines = [
        "# OBEC Conformance Claim",
        "",
        f"- **Specification:** {TARGETS}",
        f"- **Suite:** {SUITE_VERSION}",
        f"- **Implementation:** {meta.get('implementation') or '(not stated)'}",
        f"- **Adapter:** {meta.get('adapter')}",
        f"- **Adapter (host B):** {meta.get('adapter_b') or '(not supplied — OC-003(b) unestablished)'}",
        f"- **Run at:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
    ]

    if ok:
        lines += [
            "## Result: conformant",
            "",
            "Every test passed or was attested with evidence. This claim is "
            "**provisional** while the specification is Pre-release: the "
            "normative kernel can still change, and a weakening change would "
            "sever the chain of any entity created under this version.",
            "",
        ]
    else:
        failed = [r.rule for r in results if r.outcome is Outcome.FAIL]
        errored = [r.rule for r in results if r.outcome is Outcome.ERROR]
        unest = [r.rule for r in results if r.outcome is Outcome.UNESTABLISHED]
        lines += ["## Result: not conformant", ""]
        if failed:
            lines.append(f"- Failed: {', '.join(failed)}")
        if errored:
            lines.append(f"- Errored: {', '.join(errored)}")
        if unest:
            lines.append(f"- Unestablished: {', '.join(unest)}")
        lines += [
            "",
            "This is a report, not a claim. Partial conformance is not "
            "conformance (COMPLIANCE.md §3).",
            "",
        ]

    lines += [
        "## Tests",
        "",
        "| Rule | Outcome | pass | fail | attested | unestablished | error |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        t = r.tally()
        lines.append(
            f"| **{r.rule}** {r.title} | {_MARK[r.outcome]} | "
            f"{t['pass']} | {t['fail']} | {t['attested']} | "
            f"{t['unestablished']} | {t['error']} |"
        )
    lines += [
        f"| | **total** | {totals['pass']} | {totals['fail']} | "
        f"{totals['attested']} | {totals['unestablished']} | {totals['error']} |",
        "",
    ]

    problems = [(r, s) for r in results for s in r.steps
                if s.outcome in (Outcome.FAIL, Outcome.ERROR, Outcome.UNESTABLISHED)]
    if problems:
        lines += ["## Steps needing attention", ""]
        for r, s in problems:
            lines.append(f"- **{s.step}** ({r.rule}) — *{s.outcome.value}*: {s.detail}")
        lines.append("")

    attested = [(r, s) for r in results for s in r.steps
                if s.outcome is Outcome.ATTESTED]
    if attested:
        lines += [
            "## Attested steps",
            "",
            "These were recorded, not executed. A reviewer signs off against "
            "the evidence pointer; without that signature the claim is "
            "incomplete.",
            "",
        ]
        for r, s in attested:
            pointer = (s.evidence or {}).get("pointer") if isinstance(s.evidence, dict) else None
            lines.append(f"- **{s.step}** ({r.rule}) — {s.detail or ''} "
                         f"· evidence: `{pointer or '(none)'}`")
        lines.append("")

    if ctx.notes:
        lines += ["## Run notes", ""] + [f"- {n}" for n in ctx.notes] + [""]

    lines += [
        "## Still required",
        "",
        "COMPLIANCE.md §3 requires a claim to carry, alongside this report:",
        "",
        "1. the adapter source, or a permalink to it at the revision tested;",
        "2. how `inject` is gated out of production builds;",
        "3. the structural surface the implementation maintains;",
        "4. the integrity log of the run.",
        "",
    ]
    return "\n".join(lines)


def write(results, ctx, meta: dict, path_md: str, path_json: str):
    with open(path_md, "w") as fh:
        fh.write(as_markdown(results, ctx, meta))
    with open(path_json, "w") as fh:
        json.dump(as_json(results, ctx, meta), fh, indent=2, default=str)
