# Security

## Report privately

Use GitHub's **private vulnerability reporting**: the *Security* tab of this
repository, then *Report a vulnerability*. The report is visible only to the
maintainers until a fix or an advisory is published.

OBEC has one maintainer. Every report is read by the Specification Owner, and
acknowledged as soon as practicable.

## What belongs here, and what belongs in an issue

A weakness in the **argument** of the specification is a public matter. If an
invariant is untestable, a restatement, a policy, unsatisfiable, or names
structure, open an issue as [CONTRIBUTING §7](CONTRIBUTING.md#7-challenging-an-invariant)
describes. Challenges are the contribution the project most wants, and they are
stronger in the open.

Report privately when the weakness is **usable against something running**:

- a construction that passes the ten conformance tests while the guarantee they
  test does not hold, concrete enough that an implementation could be built or
  attacked with it;
- a defect in the conformance runner or the stub — for example, adapter output
  that makes the runner execute code, write outside its disposable stores, or
  record a pass for a step that failed;
- a vulnerability in a published OBEC implementation, including ones listed in
  [`implementations/`](implementations/README.md). Report those to their
  maintainers first; tell us too if it follows from the specification rather
  than from the implementation.

If you cannot tell which kind you have, report privately. It costs a delay, not
a disclosure.

## Already known

[OBEC-Core §6.2](spec/obec-core.md#62-what-is-left-open) lists what the
specification leaves open: prompt injection, worker skill results, the content
of authorized proposals, tampering with the Entity Store under a semi-trusted
host, and others. These are stated limits, not vulnerabilities. A report that
one of them is **worse than §6.2 says** is welcome, privately.

## Supported versions

Before 1.0 only the latest revision on `main` is maintained. No entity should
be created under a pre-release version, which is also why none needs patching.
