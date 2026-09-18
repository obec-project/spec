# Conformance Claims

The register of implementations claiming conformance to OBEC, what each claims,
and against which versions.

> **No claims are registered.** OBEC-Core is Pre-release at 0.9.1 and the first
> implementation has not yet run the suite.

---

## 1. The register

| Implementation | Revision | Form | Specification | Suite | Registered | Status |
|---|---|---|---|---|---|---|
| *(none yet)* | | | | | | |

**Form** is one of `OBEC-Core` (all ten invariants) or `OBEC-Attest`
(OC-001 – OC-005, OC-009, OC-010), plus any active extensions —
see [COMPLIANCE.md §1](../COMPLIANCE.md#1-forms-of-conformance).

**Status** is `active`, `superseded`, `withdrawn` or `disputed` (§6).

---

## 2. What a claim carries

A claim is a pull request adding a row above and a file under `claims/`. The
runner produces most of it:

| Item | Source |
|---|---|
| suite output, every step marked executed or attested | `claim.md` and `claim.json` from the runner |
| evidence pointer for each attested step | the adapter's `describe` results, recorded by the runner |
| the adapter source, or a permalink at the revision tested | you |
| how `inject` is gated out of production builds | you |
| the configuration the run used | `describe config`, recorded by the runner |
| the implementation revision under test | `--implementation` |
| the structural surface the implementation maintains | you |
| the integrity log of the run | you |

The last four of [COMPLIANCE.md §3](../COMPLIANCE.md#3-claiming-conformance)
are not mechanical and the runner says so at the end of every claim it writes.

**A claim without suite output is not a claim.** It is a statement of intent,
and the register does not record those.

---

## 3. Submitting

1. Run the suite against your adapter:

   ```sh
   python3 conformance/runner/run.py \
       --adapter ./your-obec-adapter \
       --adapter-b ./your-obec-adapter-on-host-b \
       --implementation "yourimpl 1.2.0 (abc1234)" \
       --out claim
   ```

   Without `--adapter-b`, step 3.2 reports *unestablished* and your claim
   carries a hole where portability should be. It is the cheapest test in the
   specification; supply a second host.

2. Add `claims/<implementation>-<version>.md` containing the claim output and
   the four non-mechanical items.

3. Add a row to §1.

4. Open a pull request titled `claim: <implementation> <version>`.

---

## 4. Review

A claim is reviewed before it is registered. The review is not a re-run — it is
a reading of what the run could not establish on its own:

- **Attested steps.** Twelve of the seventy-six are recorded rather than
  executed, four of them being OC-006 in full. A reviewer follows each evidence
  pointer into the implementation's source and signs off, or does not. **An
  attested step without a signature is not established**, and a claim whose
  attested steps are all unsigned is a test run, not a conformance claim.
- **The adapter.** The adapter is written by the implementer being tested, so
  the suite detects error and not fraud
  ([ADAPTER.md §6](ADAPTER.md#6-what-the-suite-cannot-establish)). The reviewer
  reads it for the two failure modes that produce a passing run against a
  non-conformant implementation: an `entity` command that validates a target
  before calling the operation, and an `inject corrupt` that corrupts nothing.
- **`--adapter-b`.** The runner cannot tell whether the second adapter ran
  elsewhere. The reviewer looks at the recorded command and decides.
- **Unestablished steps.** Each carries a reason. Version-transition steps
  (4.9 – 4.12) are unestablished for everyone until the first version after
  1.0; anything else unestablished is a gap the claim must explain.

The Specification Owner registers the claim
([GOVERNANCE.md §2](../GOVERNANCE.md#2-roles)).

---

## 5. Validity

A claim names two versions because they move independently
([Core §4.1](../spec/obec-core.md#41-what-is-version-bound)).

**A specification revision does not carry a claim forward.** Which revisions
affect it follows the taxonomy in
[Core §4.2](../spec/obec-core.md#42-revision-and-continuity):

| Revision | Effect on a registered claim |
|---|---|
| editorial | none |
| clarifying | none; every conformant implementation stays conformant |
| **hardening** | the claim becomes `superseded`. The implementation may satisfy the new invariants already, but nobody has checked — re-run and re-submit |
| **weakening** | the claim becomes `superseded`, and any entity created under the prior version ends its line there |

**A suite revision does not invalidate a claim.** A claim is conformant to the
suite it passed and says which. A later suite testing an existing guarantee more
closely is not a finding against an implementation that passed an earlier one —
but a claim against an old suite is weaker evidence, and re-running is cheap.

### 5.1 Pre-release claims are provisional

While OBEC-Core is Pre-release, the normative kernel can still change and a
weakening change would sever the chain of any entity created under the current
version. **No entity should be created under a pre-release version**, so a claim
against 0.9.1 attests that an implementation passes the suite, not that anything
built on it is durable.

---

## 6. Correction and withdrawal

The register is only worth what its entries are.

**Withdrawal.** An implementer may withdraw a claim at any time, for any reason,
by pull request. Withdrawal is not an admission of anything; a claim whose
implementation has moved on is better withdrawn than left to rot.

**Dispute.** Anyone may open an issue showing that a registered implementation
fails a test, with steps to reproduce. The entry is marked `disputed` while the
issue is open. Resolution is either a corrected run, a withdrawal, or a
demonstration that the dispute is mistaken.

**Correction.** A claim found to contain an inaccurate attestation is withdrawn,
not amended. The register keeps the withdrawn row, because a register that
quietly deletes its mistakes tells you less than one that does not.

---

## 7. Entry template

```markdown
## <implementation> <version>

- **Revision tested:** <commit or tag>
- **Form:** OBEC-Core | OBEC-Attest [+ extensions]
- **Specification:** OBEC-Core <version>
- **Suite:** <version>
- **Adapter:** <permalink at the revision tested>
- **Adapter (host B):** <command, and where it ran>
- **Injection gating:** <how `inject` returns exit 2 in production builds>
- **Registered:** <date> · **Reviewed by:** <name>

### Suite output
<claim.md, verbatim>

### Attested steps
<each step, its evidence pointer, and the reviewer's sign-off>

### Structural surface
<the structural content the implementation maintains, per COMPLIANCE §3.3>

### Integrity log
<the log of the run, or a pointer to it>
```
