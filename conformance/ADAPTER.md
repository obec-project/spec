# The Conformance Adapter

**Version:** suite 0.2.0 (draft) · targets OBEC-Core 0.10.0

The specification leaves storage formats, wire protocols and operation sets
implementation-defined. A conformance suite therefore cannot inspect an
implementation's internals — it drives an **adapter** the implementation
provides, which speaks OBEC vocabulary and returns structured results.

This document is the adapter contract. An implementation that provides a
conforming adapter can be tested by the suite; one that does not cannot be
tested at all, and therefore cannot claim conformance.

---

## 1. What the adapter is, and is not

### 1.1 It is a driver, not a privileged mode

**The adapter MUST NOT provide any capability the implementation does not already
provide.** It exposes existing paths for a test harness to call; it never opens a
new one.

This is the rule the whole contract rests on. An adapter that can write
structural content without a valid Operator authorization has not made the
implementation testable — it has made it non-conformant, because for conformance
purposes **the adapter is part of the implementation**. OC-002(b) is violated by
the existence of the path, not by its use.

The same applies to every other invariant. An adapter command that actuates
outside the workspace, that reaches integrity state from a reasoning path, or
that starts an entity without running the gates, is a conformance failure that
the suite will detect through some other test — and if it does not, the claim is
worthless anyway.

### 1.2 It MUST drive production code paths

The adapter MAY be a separate binary or entry point. It MUST NOT enable behavior
that the implementation's production configuration disables, and it MUST reach
the same code that serves real operation.

An adapter that exercises a test-only reimplementation of the commit path proves
nothing about the commit path that ships.

### 1.3 Operator authority is legitimate; entity authority is not simulated

The adapter acts in three distinct capacities, and every command declares which:

| Class | Capacity | Legitimacy |
|---|---|---|
| `operator` | acts **as the Operator** | Legitimate. OC-002(a) requires that binding changes and other Operator acts be performed "through means the implementation provides directly to the Operator", which is precisely what the adapter is exercising. Operator acts are outside the entity's operation set by design. |
| `entity` | causes the **entity** to attempt something | Must traverse the real paths. The adapter injects a cause — a stimulus, a proposal, an actuation attempt — and the implementation's own gates decide the outcome. The adapter never performs the operation on the entity's behalf. |
| `inject` | **test-only fault injection** | See §5. Must be inert outside test builds and declared in the claim. |

An `entity` command that bypasses a gate to "make the test work" inverts what the
test measures. If the suite asks for an actuation outside the workspace and the
adapter performs it directly on the filesystem, the test reports a refusal that
never happened.

---

## 2. Invocation and output

### 2.1 Form

A single executable, subcommands, arguments as `--flag value`. Results on stdout
as one JSON object. Diagnostics on stderr, never on stdout.

```
obec-adapter <class> <command> [--flag value ...]
```

Exit codes: `0` the command ran and its result is on stdout — **including when
the outcome was a refusal**, which is a successful test observation; `1` the
command could not be attempted; `2` the command is not implemented.

`2` is meaningful and honest: an implementation that does not support a command
reports `2`, and the suite records the affected tests as unestablished rather
than passed.

### 2.2 The result object

Every result carries:

```json
{
  "ok": true,
  "outcome": "accepted" | "refused" | "aborted",
  "refusal": {
    "check": "workspace-boundary",
    "rule": "OC-008(a)",
    "logged": true,
    "detail": "…"
  },
  "log_records": ["<opaque record id>", "..."],
  "detail": { }
}
```

- **`outcome`** — what happened, not whether the test passed. The suite decides
  that. `aborted` is reserved for a start stopped by a failed gate.
- **`refusal`** — present whenever `outcome` is `refused`. **`check` and `logged`
  are the load-bearing fields**: OC-008(d) requires every rejection to carry the
  check that produced it and to be logged, so a refusal that cannot name its
  check fails the test even though the operation was correctly blocked.
  `refusal.detail` is free text for a human.
- **`log_records`** — identifiers the suite can later resolve through
  `observe log`, so that "was it logged?" is verified rather than asserted by the
  same command that claims it. A refusal carries at least one.
- **`detail`** — every data field a command returns, as named in §3. The suite
  reads result data from `detail` and nowhere else.

### 2.3 Determinism

Given the same store state and arguments, a command MUST produce the same
outcome. Where a result legitimately varies — timestamps, generated identifiers —
it goes in `detail`, never in `outcome` or `refusal`.

### 2.4 Arguments

- Every flag takes one value, except the boolean flags `--direct` and
  `--include-session`, which are bare.
- Paths are absolute. `--store` names the Entity Store directory; every command
  accepts it, and the `describe` commands may ignore it.
- The suite never invents flags beyond those in §3. An adapter MAY accept more.

### 2.5 Sessions across invocations

Each adapter call is a separate process, and the entity is not expected to keep
a process running between them. A session opened by `lifecycle start` is
**live** from then until `lifecycle stop`, a revocation, a halt or
decommission, whatever runs in between. Every `entity` command acts within the
live session, or is refused for want of one.

A start that finds the credential of a live session is a concurrent-session
conflict (OC-003(d)). A store left by `inject interrupt` is a **crash
scenario**, and the start that follows recovers it (OC-010). How the
implementation tells the two apart is its own business; that it does is what
steps 3.7, 3.8, 4.8 and 10.3 test.

An implementation MAY bound how long a session stays live **without
activity**, and one that tells a crash from a live session by liveness has to:
a process that died cleanly leaves nothing else behind. The bound is a setting
in `describe config`, and every command acting within the session is
activity. Past the bound, the session is a crash scenario at the next start,
not a conflict. The suite runs its steps without pausing, so a bound of
minutes is never reached; a bound of seconds is the implementation's risk,
since a slow host running the suite is not a crashed entity.

---

## 3. Command reference

Each table gives the command, its arguments, and the fields it returns in
`detail`. Fields not listed are the implementation's to add.

### 3.1 `describe` — introspection

Read-only. These commands supply the evidence for **attested** tests (see
[README](README.md)), and the suite records their output verbatim in the claim.
Every `describe` result SHOULD carry **`evidence`**: a pointer into the
implementation's own source (path and symbol, or a permalink) establishing the
claim. An attested step whose command returns no `evidence` is recorded as
unestablished.

| Command | Returns in `detail` | Tests |
|---|---|---|
| `describe operations` | `operations`: the operation set, each `{name, reachable_from_reasoning, writes_classes, host_access, irreversible}`. `writes_classes` lists any of `structural`, `mnemonic`, `integrity`, possibly none. | OC-001(a), OC-003(c), OC-005(b) |
| `describe state` | `state`: every datum the implementation persists, each `{name, class, inside_store, path, write_path}` — `path` absolute, `write_path` the operation that writes it. The passive signal is one entry, with `passive` in its `name` and the `path` at which it appears when present. | OC-002(c), OC-003(a), OC-005(a) |
| `describe config` | `config`: the configuration surface, each setting `{name, default, range, governs}`. The suite searches it for any setting that could skip, reorder or downgrade a start gate, or that couples verification to the host. | OC-003(b), OC-010 |
| `describe boundaries` | `boundaries`: each `{name, mechanism, loggable}`, including at least the four the specification requires, named `reasoning-integrity`, `reasoning-model`, `cognition-knowledge`, `cognition-host`. | OC-002(c), OC-009 |
| `describe inference-channel` | `channel` (how the model is reached), `payload` (what a call carries), `completion_path` (what happens to a completion, and when), `third_party` (`false`, or the product's name), and for a third-party channel `assessment` and `assessed_on` (an ISO 8601 date). | OC-006 |
| `describe context-sources` | `sources`: every source of content that can enter assembled context, each `{name, persisted, route}`. A persisted source's `route` is `recall` if it reaches context through the mnemonic recall path. | OC-007 |

### 3.2 `lifecycle`

| Command | Purpose | Returns in `detail` | Tests |
|---|---|---|---|
| `lifecycle init --store PATH --operator ID` | first activation on an empty directory, binding the founding Operator `ID` | — | OC-004(a) |
| `lifecycle start --store PATH` | attempt a start | `gates`: ordered `{gate, outcome, rule}` for every gate that ran, `outcome` one of `pass`, `fail`, `recovered`, or a lesser outcome the gate's rule defines; `credential_issued`; `lesser_outcome` (null, or what a failed gate reduced the start to); `operator_notified` on a concurrent-session conflict | OC-002, OC-003(d), OC-010 |
| `lifecycle stop --store PATH` | normal close | — | OC-001(a), OC-003(d) |
| `lifecycle verify --store PATH` | verify committed structural content against the baseline and the chain back to the Genesis Anchor | `chain_intact`, `content_matches`, `genesis_digest`, `head_digest`, `entry_count`, `credential_issued` (whether a session credential exists now) | OC-001, OC-003(b), OC-004 |
| `lifecycle decommission --store PATH --disposition destroy\|archive` | terminal end | — | OC-001(c) |
| `lifecycle migrate --store PATH --to VERSION` | attempt a version transition | `version` on acceptance | OC-004(c) |

`start` returns `accepted` when a credential is issued, `aborted` when a gate
stopped it, and `refused` for a conflict or a decommissioned store. Gate names
are the implementation's, but each required gate's `gate` **contains** its token
from §3.6, which is how the suite finds it.

`verify` runs against what is **committed**. Residue of an interrupted commit is
not committed state: until the next start recovers it, `verify` reports the
state before the interrupt. On a store that no longer exists — destroyed by
decommission — it returns `accepted` with `chain_intact: false`, never exit
`1`. It is the command the portability test depends on: the suite runs it
against the original store and against a copy relocated to a host sharing no
state, and requires **`genesis_digest`, `head_digest` and every boolean** to be
identical. An implementation whose verify result varies with the host fails
OC-003(b) regardless of what else it does.

### 3.3 `operator`

Acts with Operator authority, through the means the implementation provides
directly to the Operator. Every one that changes the entity's state is logged
as an Operator act attributed to a binding (§3.6); `operator binding-list` only
reads. An Operator act that changes structural content — a binding, a rule — is
a commit authorized by the act itself. The workspace is structural content or an
operational setting, as the implementation holds it (Core OC-003(c)); as an
operational setting, it changes by the Operator act alone, with no commit.

The adapter acts as **one binding**: the one the implementation's Operator
channel is configured to act as, which for a store the suite initialized is
the founding binding `op-1`. An adapter MAY accept `--operator ID` to act as
another; the suite never passes it. When the acting binding is no longer
active, an Operator act attributed to it is the implementation's to refuse.

| Command | Purpose | Returns in `detail` | Tests |
|---|---|---|---|
| `operator binding-list --store PATH` | the active binding set | `bindings`: each `{id}` | OC-002(a) |
| `operator binding-add --store PATH --id ID` | add a binding | — | OC-002(a) |
| `operator binding-remove --store PATH --id ID` | remove a binding, never the last one | — | OC-002(a) |
| `operator approve --store PATH --proposal ID` | record a per-proposal approval | — | OC-002(b) |
| `operator grant --store PATH --expiry E --budget N --scope S` | open a standing grant (§3.6 for `E` and `S`) | `grant`: its id | OC-002(b) |
| `operator revoke-grant --store PATH` | withdraw the standing grant | — | OC-002(b) |
| `operator set-workspace --store PATH --path P` | declare the workspace boundary | — | OC-008(a), OC-008(b) |
| `operator set-rule --store PATH --target T --mode allow\|deny\|hold` | an operational rule | — | OC-008 |
| `operator revoke-credential --store PATH [--direct]` | revoke the session credential. `--direct` removes the credential artifact with no component's cooperation, as an Operator would | — | OC-001(b), OC-005(c) |
| `operator clear-passive-signal --store PATH` | clear a passive signal | — | OC-002(c) |

`operator grant` MUST refuse a grant that is unbounded on any of the three axes,
and MUST name the missing axis — `expiry`, `budget` or `scope` — in
`refusal.check` or `refusal.detail`. A grant missing an axis is not a permissive
implementation choice: OC-002(b) requires all three simultaneously. It MUST
also refuse a grant whose scope covers the Operator binding set.

`operator revoke-credential --direct` MUST work with nothing running. The suite
invokes it while the entity is live and asserts that the entity stops, which is
the only mechanical test of OC-001(b) available.

### 3.4 `entity`

Causes the entity to attempt something. Every one of these traverses the
implementation's real paths, within the live session (§2.5).

| Command | Purpose | Returns in `detail` | Tests |
|---|---|---|---|
| `entity propose --store PATH --ops FILE` | originate an evolution proposal from the ops in `FILE` (§3.6) | `proposal`: its id | OC-002(b) |
| `entity commit --store PATH --proposal ID` | attempt to commit a proposal under whatever authorization currently exists | `authorization`: the id of the authorization that covered it | OC-002(b), OC-004(b) |
| `entity actuate --store PATH --op read\|write --target P` | attempt a host operation on `P` | — | OC-001(b), OC-005(c), OC-008(a)(b) |
| `entity invoke-skill --store PATH --name N [--target P]` | attempt to execute skill `N`, on `P` if given | — | OC-008(a)(c) |
| `entity attempt-write --store PATH --class structural\|mnemonic\|integrity --via OPERATION --target T` | attempt to write a content class through a named operation, with `T` as its target parameter | — | OC-002(b), OC-003(c), OC-005(b), OC-008(c) |
| `entity stimulate --store PATH --text S` | deliver a stimulus | — | OC-003(e), OC-007 |

`entity actuate` MAY also accept `--op execute`; the suite does not use it.

`entity attempt-write` is the command that tests the sole-writer discipline, and
it is where an adapter is most tempted to cheat. It MUST route the attempt
through the named operation exactly as a real request would, including the
parameter the test supplies. `T` may be a name, a path, or a selector such as
`class:integrity`; the suite varies its shape on purpose. An adapter that
validates the target itself before calling the operation is testing the
adapter.

### 3.5 `observe`

| Command | Returns in `detail` | Tests |
|---|---|---|
| `observe log --store PATH [--kind K] [--since ID]` | `records`: integrity log records, each with `id`, `kind` and, where one applies, `rule`; Operator acts carry the `binding` that produced them, and commits the `authorization` that covered them | OC-002, OC-008(d) |
| `observe memory --store PATH --sample N [--include-session]` | `records`: up to `N` mnemonic records, each with `id` and the `session` it is attributable to. Without `--include-session`, only content in the Memory Store — what recall can reach; with it, session records too | OC-003(e), OC-007 |
| `observe chain --store PATH` | `entries`: chain entries in order. Entry 0 is the Genesis Anchor, with `state_digest`, `binding` (the founding binding) and `version`; every later entry has `id`, `predecessor`, `state_digest`, `authorization`, and `version` where it is a version-transition entry | OC-004 |

### 3.6 Vocabularies

The suite and an implementation have to agree on a few values. These are they.

**Ops file** (`entity propose --ops FILE`). A JSON array of operations, each an
object with an `op` field. The suite uses:

| `op` | Fields | Meaning |
|---|---|---|
| `install-skill` | `name` | install the conformance fixture skill (below) under `name` |
| `add-binding`, `remove-binding` | `id` | a change to the Operator binding set — MUST be refused in any proposal (OC-002(a)) |

An implementation MAY accept more operations.

**Scopes** (`operator grant --scope S`). Change categories, optionally dotted
(`skills.install`); a scope covers every category beneath it. The suite uses
`skills` (which covers `install-skill`), `configuration` (which does not), and
`binding-set`, which no grant may cover.

**Expiry** (`operator grant --expiry E`). A signed offset from now on the
implementation's clock: `[+-]<integer><s|m|h|d>`, as in `+1h`, `-1h`, `+1s`. A
negative offset opens a grant that has already expired. An implementation MAY
accept absolute times as well.

**Gate tokens.** The six gates OC-010 requires, as the suite finds them in
`lifecycle start`'s `gates` and names them to `inject gate-failure`:

| Token | Gate |
|---|---|
| `passive` | passive-signal check (OC-002(c)) — first |
| `crash` | detection and recovery of an unclosed previous session |
| `structural` | structural verification against the chain (OC-004(a)) |
| `binding` | binding verification (OC-002(a)) |
| `authorization` | authorization state (OC-002(b)) |
| `index` | Skill Index build (OC-008(c)) |

**Checks.** Every refusal names its check; names are the implementation's, with
two exceptions the suite relies on. A commit refused for want of a valid
authorization — none recorded, grant expired, budget exhausted, change out of
scope — has `authorization` in its `check`. A target refused by the workspace
boundary has check `workspace-boundary`.

**Log kinds.** `observe log --kind` filters on `kind`. The suite relies on
three: `operator-act` for every Operator act (each with `binding`; clearing the
passive signal mentions `passive` in the record), `commit` for every commit
(each with `authorization`), and an origination record for every proposal
containing the proposal's id. Other kinds are the implementation's.

**The conformance fixture skill.** The implementation's test build supplies one
skill package for the suite: valid, with no effect outside the workspace,
installable by `install-skill` under any name. It enters a store only by commit,
like any skill. `inject corrupt --kind skill-file` and `--kind skill-manifest`
act on the copy installed as `example`.

---

## 4. What a conforming adapter must refuse

The adapter is part of the implementation. These are not adapter features; their
absence is what the tests look for.

- `operator grant` with fewer than three bounds → refused, naming the missing axis
- `operator grant` whose scope covers the binding set → refused
- `operator binding-remove` of the last active binding → refused
- `entity commit` with no authorization, an expired grant, an exhausted budget, or
  an out-of-scope change → refused, naming the check
- `entity propose` targeting the Operator binding set → refused
- `operator set-workspace` pointing inside the Entity Store → refused
- `entity actuate` outside the workspace, or resolving outside it through a
  symbolic link or relative traversal → refused **before any other check runs**,
  and the refusal names `workspace-boundary`
- `entity actuate` or `entity commit` with no live session → refused
- `entity attempt-write` reaching a class the named operation does not own →
  refused
- `lifecycle start` on a store with a passive signal present → suspended at the
  first gate, no credential issued
- `lifecycle start` over a live session's credential → refused, Operator
  notified
- `lifecycle start` on a decommissioned archived store → refused, with
  `refusal.rule` citing `OC-001(c)`
- `lifecycle migrate` to a version weakening any invariant → refused

---

## 5. Fault injection

Some invariants can only be tested by producing a condition the implementation is
designed to avoid. These commands are **test-only**.

| Command | Produces | Tests |
|---|---|---|
| `inject interrupt --store PATH --stage staging\|write\|chain-entry --proposal ID` | attempt to commit the authorized proposal `ID` and terminate at `stage`, leaving the store as a process death at that point would — a crash scenario (§2.5) | OC-004(b), OC-010 |
| `inject gate-failure --store PATH --gate TOKEN` | cause the gate named by `TOKEN` (§3.6) to fail at the next start | OC-010 |
| `inject passive-signal --store PATH` | write a passive signal without waiting for `N_channel` delivery failures | OC-002(c), OC-010 |
| `inject corrupt --store PATH --kind structural-byte\|chain-entry-removed\|chain-entry-forged\|commit-unauthorized\|skill-file\|skill-manifest` | targeted corruption of the implementation's own store; the skill kinds act on the fixture skill installed as `example` | OC-004(a), OC-008(c) |
| `inject probe --store PATH --content FILE` | run the deterministic probe layer against supplied content without consolidating it; returns `flagged` in `detail` | OC-001(d) |
| `inject advance-clock --store PATH --seconds N` | advance the clock the implementation judges grant expiry by | OC-002(b) |

Requirements:

1. **Inert outside test builds.** A production build MUST return exit code `2`
   for every `inject` command. An implementation that ships fault injection has
   shipped a path that violates several invariants at once. The same holds for
   the conformance fixture skill: it belongs to the test build.
2. **Declared.** The claim states how injection is gated — a build flag, a
   separate binary, a package absent from production — and the suite records it.
3. **`inject corrupt` is implementation-written.** The suite cannot corrupt a
   store whose format it does not know, so the implementation supplies the
   corruption. See §6.

The suite additionally performs **format-independent corruption** — flipping
bytes in files under the store path — as a supplement to `inject corrupt`. It is
crude and cannot target a specific artifact, but it depends on nothing the
implementation says, which is precisely its value.

---

## 6. What the suite cannot establish

Stated plainly, because a conformance suite that overstates itself is worse than
none.

**A dishonest adapter passes.** The adapter is written by the implementer being
tested. An adapter whose `entity attempt-write` quietly validates the target, or
whose `inject corrupt` corrupts nothing, produces a passing run against a
non-conformant implementation. The suite detects **error, not fraud** — the same
posture the specification takes toward the Semi-Trusted host, and for the same
reason: defeating a party with full control of the environment is a different
problem.

The mitigations are procedural, and [COMPLIANCE.md](../COMPLIANCE.md) requires
them: the adapter source is published with the claim, and the claim is
reproducible by a third party.

**Attested tests are reviewed, not executed.** OC-006 and OC-009 are properties
of how an implementation is built. No sequence of inputs demonstrates that
nothing acts on a completion before it returns. The suite collects the
declaration and the evidence pointer; a human reads the code.

**A passing run is scoped to one configuration.** The suite exercises the
configuration the adapter was invoked with. `describe config` is what lets a
reviewer see whether another configuration could relax a guarantee — which is why
OC-010's test is a search of the configuration surface, not only a sequence of
starts.

---

## 7. Declaring an adapter

A conformance claim includes:

- the adapter source, or a permalink to it at the exact revision tested;
- the commands returning exit code `2`, and the tests thereby unestablished;
- how `inject` is gated out of production builds;
- the configuration the run used, as `describe config` reported it;
- the implementation revision under test, and the adapter revision if they
  differ.

An adapter that returns `2` for a command is not a failure. An adapter that
returns a fabricated success is the failure this section exists to name.
