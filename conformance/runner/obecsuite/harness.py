"""Run context: ties the adapter, the disposable stores, and result collection.

A step's outcome is decided here and nowhere else, so that every test reads as
a sequence of adapter calls and assertions rather than as bookkeeping.
"""

from contextlib import contextmanager

from .adapter import AdapterError
from .result import Outcome, StepFailure, StepResult, StepUnestablished, TestResult


class Context:
    def __init__(self, adapter, stores, host_b: str = None, adapter_b=None):
        self.adapter = adapter
        self.stores = stores
        self.host_b = host_b
        # The adapter that verifies the relocated copy. When it is the same
        # process on the same machine, host coupling cannot manifest — see
        # step 3.2, which reports unestablished rather than pass.
        self.adapter_b = adapter_b
        self.notes: list = []
        self._current: TestResult = None

    # -- log resolution ---------------------------------------------------

    def unresolved_log_records(self, res) -> list:
        """Ids a refusal claims to have written, that `observe log` does not
        return. Verifying the log through a second command is the point: a
        result that both performs the refusal and asserts it was logged is one
        witness, not two."""
        wanted = set(res.log_records)
        if not wanted:
            return []
        store = self._store_of(res)
        if not store:
            return []
        try:
            log = self.adapter.call("observe", "log", store=store)
        except (AdapterError, StepUnestablished):
            return sorted(wanted)
        seen = {r.get("id") for r in (log["records"] or [])}
        return sorted(wanted - seen)

    @staticmethod
    def _store_of(res):
        argv = res.argv
        if "--store" in argv:
            return argv[argv.index("--store") + 1]
        return None

    # -- step recording ---------------------------------------------------

    @contextmanager
    def step(self, number: str, kind: str, title: str = ""):
        sr = StepResult(step=number, kind=kind, outcome=Outcome.PASS, detail=title)
        self.adapter.drain_calls()
        try:
            try:
                yield sr
            except Exception as exc:
                if type(exc).__name__ != "_Skip":
                    raise
            if kind == "A" and sr.outcome is Outcome.PASS:
                # An attested step is recorded for review, never asserted by
                # the runner — unless it arrived without evidence, in which
                # case there is nothing to review.
                sr.outcome = Outcome.ATTESTED if sr.evidence else Outcome.UNESTABLISHED
                if not sr.evidence:
                    sr.detail = (title + " — " if title else "") + "no evidence pointer"
        except StepFailure as exc:
            sr.outcome = Outcome.FAIL
            sr.detail = str(exc)
        except StepUnestablished as exc:
            sr.outcome = Outcome.UNESTABLISHED
            sr.detail = str(exc)
        except AdapterError as exc:
            sr.outcome = Outcome.ERROR
            sr.detail = str(exc)
        except Exception as exc:  # a defect in the runner, not a verdict
            sr.outcome = Outcome.ERROR
            sr.detail = f"runner error: {type(exc).__name__}: {exc}"
        finally:
            sr.calls = self.adapter.drain_calls()
            if self._current is not None:
                self._current.steps.append(sr)

    def note(self, text: str):
        self.notes.append(text)


class Runner:
    def __init__(self, ctx: Context, tests: list):
        self.ctx = ctx
        self.tests = tests
        self.results: list = []

    def run(self, only: set = None, verbose: bool = False) -> list:
        for rule, title, fn in self.tests:
            if only and rule not in only:
                continue
            tr = TestResult(rule=rule, title=title)
            self.ctx._current = tr
            try:
                fn(self.ctx)
            except Exception as exc:
                tr.steps.append(StepResult(
                    step="—", kind="E", outcome=Outcome.ERROR,
                    detail=f"test aborted: {type(exc).__name__}: {exc}",
                ))
            self.ctx._current = None
            self.results.append(tr)
            if verbose:
                self._echo(tr)
        return self.results

    @staticmethod
    def _echo(tr: TestResult):
        mark = {
            Outcome.PASS: "pass", Outcome.FAIL: "FAIL", Outcome.ERROR: "ERROR",
            Outcome.UNESTABLISHED: "unest", Outcome.ATTESTED: "attest",
        }[tr.outcome]
        print(f"  {tr.rule}  {mark:<6}  {tr.title}")
        for s in tr.steps:
            if s.outcome in (Outcome.FAIL, Outcome.ERROR, Outcome.UNESTABLISHED):
                print(f"      {s.step:<5} {s.outcome.value}: {s.detail}")
