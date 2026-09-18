"""Outcome vocabulary for steps, tests and runs."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    # The adapter returned exit code 2, or an attested step arrived without an
    # evidence pointer. Distinct from FAIL on purpose: "cannot be determined"
    # is not "does not conform", and a claim that conflated them would either
    # overstate or understate the implementation.
    UNESTABLISHED = "unestablished"
    # The adapter crashed, timed out, or returned output the runner could not
    # parse. A defect in the adapter, not a verdict on the implementation.
    ERROR = "error"
    # Recorded, not asserted: a human reviews the evidence and signs off.
    ATTESTED = "attested"


@dataclass
class StepResult:
    step: str                 # "2.10"
    kind: str                 # "E" or "A"
    outcome: Outcome
    detail: str = ""
    evidence: Any = None      # attested steps: the describe output + pointer
    calls: list = field(default_factory=list)   # adapter invocations made

    @property
    def counts_against_conformance(self) -> bool:
        return self.outcome in (Outcome.FAIL, Outcome.ERROR)


@dataclass
class TestResult:
    rule: str                 # "HC-002"
    title: str
    steps: list = field(default_factory=list)

    @property
    def outcome(self) -> Outcome:
        if any(s.outcome is Outcome.ERROR for s in self.steps):
            return Outcome.ERROR
        if any(s.outcome is Outcome.FAIL for s in self.steps):
            return Outcome.FAIL
        if any(s.outcome is Outcome.UNESTABLISHED for s in self.steps):
            return Outcome.UNESTABLISHED
        if any(s.outcome is Outcome.ATTESTED for s in self.steps):
            return Outcome.ATTESTED
        return Outcome.PASS

    def tally(self) -> dict:
        t = {o.value: 0 for o in Outcome}
        for s in self.steps:
            t[s.outcome.value] += 1
        return t


class StepFailure(Exception):
    """Raised by an assertion. Caught per step, never per test: one failing
    step does not abandon the rest, because a claim listing every failure is
    more useful than one listing the first."""


class StepUnestablished(Exception):
    """Raised when the adapter reports a command it does not implement."""
