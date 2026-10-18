# fsp-ref-min — design

fsp-ref-min is the smallest program that is an OBEC entity. It keeps the ten
invariants of the [OBEC kernel](../../spec/obec-kernel.md) and nothing more.
Read it to see how an entity works, not to get a coding agent: it chats, reads
and writes files, fetches pages and runs skills, and that is all it does.

§1 and §2 give the whole picture in plain words. From §3 on, the document
follows the order in which the ideas depend on each other. Each section uses
only terms defined before it, or names the section that defines them.

A decision appears where it applies, with its reason. The
[Implementation Profile](../../spec/obec-profile.md) is not needed to read
this document. Where fsp-ref-min departs from the Profile, §13.4 says so.

---

## 1. The idea

An **entity** is a set of files plus a program that runs them. The files are
the **Entity Store**. The program reads the store, asks a language model what
to do, and does it within limits that a human sets.

That human is the **Operator**. The Operator creates the entity, decides what
it may become, decides where it may act, and can stop it at any moment, even
with the program not running.

The **model** is any language model behind an API: a local Ollama, OpenAI,
Anthropic. The model does not act. It receives text and returns text. The
program decides whether anything in that text gets done.

Five rules capture the whole design:

1. **Everything the entity is lives in the store.** Copy the folder and you
   have copied the entity (§3).
2. **Who the entity is changes only with the Operator's authorization**, and
   every change is a link in a chain back to its birth (§4, §5).
3. **The entity starts only after the store is verified** (§6).
4. **The model only answers.** Each answer is routed to one owner, which
   checks it, does it, and leaves a record (§7, §8).
5. **The entity acts only inside the folder and the sites the Operator
   declared**, and only through operations the program has or skills the
   Operator admitted (§10).

## 2. The parts

The program has six parts. Four of them **own** operations, split along the
same lines as the invariants. The other two only **carry** messages: they own
no operation, hold no authority and write nothing.

```
                         Operator
                            ▲
                            │  notices · questions · replies · halt
                            ▼
                     Operator Channel
                            ▲
           ┌────────────────┼────────────────┐
           │                │                │
   ┌──────────────────── Orchestrator ─────────────────────┐
   │  runs the cycle, assembles the context,               │
   │  routes each intent to its owner                      │
   └────┬─────────────┬──────────────┬──────────────┬──────┘
        │             │              │              │
       CPE           MIL            EXEC           SIL
    cognition       memory          host        integrity
        │
        ▼  text in, text out
      model
```

| Part | Kind | Owns | Writes | Invariant |
|---|---|---|---|---|
| **SIL** — System Integrity Layer | owner | verification, the commit, the start, the credential, the log, the Operator's acts | integrity content; structural content by commit only; operational content on an Operator act only | OC-001, OC-004, OC-005, OC-010 |
| **CPE** — Cognitive Processing Engine | owner | turning a context into one intent | nothing | OC-006 |
| **MIL** — Memory Interface Layer | owner | session records, memory, recall, sleep | mnemonic content | OC-007 |
| **EXEC** — Execution Layer | owner | file operations, web fetch, skills | the workspace only, never the store | OC-008 |
| **Orchestrator** | carrier | nothing: it carries signals between the parts | nothing | OC-009 |
| **Operator Channel** | carrier | nothing: it carries messages between the parts and the Operator | nothing | OC-001(c) |

A part never calls into another part's internals. **Among the parts**, it
sends a signal through the Orchestrator, and every signal leaves a record
(§7). **Toward the Operator**, any part sends a message through the Operator
Channel, and that path never passes through cognition (§12.1). Everything
runs in one process and one thread.

## 3. The store

### 3.1 Four classes of content

Every file in the store belongs to exactly one class, and each class has
exactly one way to be written (OC-003(c)).

| Class | What it is | Who writes it | How |
|---|---|---|---|
| **structural** | who the entity is: persona, Operator bindings, skills | SIL | only by a commit (§4) |
| **mnemonic** | what the entity lived and learned: sessions, memory | MIL | `mnemonic-write` |
| **integrity** | what proves and guards the rest: `HEAD`, chain, log, credential, passive signal | SIL | `integrity-write` |
| **operational** | how the Operator runs the entity: workspace, sites, model, limits | SIL, on an Operator act only | `operational-write` |

The class is decided by who may write the content, not by how long it lives.
The credential lasts one session and is integrity content; the operational
settings last until the Operator changes them.

### 3.2 Layout

```
S/
├── OBEC-STORE                  marks the folder as a store; format version
├── CREDENTIAL                  present while a session is live (§6.2)
├── PASSIVE-SIGNAL              present when the entity stopped and needs the Operator (§12.1)
├── structural/
│   ├── 0/                      the state at birth; one folder per commit, never changed
│   │   ├── persona.md
│   │   ├── bindings.json
│   │   └── skills/<name>/manifest.json, …
│   └── 1/, 2/, …
├── integrity/
│   ├── HEAD                    the newest committed entry and its state digest (§4.3)
│   ├── chain/000000.json, …    one entry per commit; 000000 is the Genesis Anchor
│   ├── log.jsonl               the integrity log, append-only
│   └── lock                    empty; held while anything writes
├── memory/
│   ├── sessions/s-0001.jsonl   everything that happened in a session
│   ├── episodic.jsonl          what the entity chose to remember
│   └── semantic.jsonl          what it learned, written at the close of a session
└── operational/
    └── settings.json           the Operator's settings for running the entity (§5.5)
```

Every path inside the store is relative to the store. Nothing the chain
verifies names the host, so a copy of the folder on another machine verifies
the same way (OC-003(b)). The operational settings may name a folder on this
host. They travel with the store, but no verification reads them.

`CREDENTIAL` and `PASSIVE-SIGNAL` sit at the root so the Operator can act on
them with `rm` and `cat`, without knowing anything else about the layout.

### 3.3 Two ways to write a file

`store.py` is the only module that opens a file for writing, and it knows
only two forms:

- **append** — a line of JSON added to a `.jsonl` file, then `fsync`. A
  crash can leave a torn last line, which the reader skips.
- **replace** — the whole file written to a temporary name, `fsync`, then
  `rename` over the target, then `fsync` of the folder. The file is always
  either the old version or the new one.

No file is edited in place. Every write takes the store's lock
(`integrity/lock`, `flock`), so two processes never write at the same time
(OC-003(d)).

### 3.4 The class guard

`store.write(cls, path, data, writer)` refuses a write when `writer` does not
own `cls`, and when `path` does not belong to `cls`. `store.classify(target)`
answers which class a target belongs to. The target can be a path, a datum's
name, or a selector such as `class:integrity`. Every operation that accepts a
target asks `classify` before doing anything else.

A test scans the source and fails if any module other than `store.py` opens a
file for writing or renames or removes one inside the store.

## 4. Identity: the chain

### 4.1 Generations

The structural content after each commit is a folder, `structural/<n>/`, and
it is never changed afterwards. The newest committed folder is who the entity
is now; the older ones are who it was. Keeping every generation costs disk
space and buys the simplest possible verification: every link of the chain
can be checked against the content it describes.

### 4.2 The digest

The **state digest** of a generation is the SHA-256 of a canonical list of its
files: relative path, SHA-256 of the bytes, and the execute bit, sorted by
path. Timestamps, owners and other modes are left out, since a copy would
change them.

### 4.3 The chain and `HEAD`

`integrity/chain/` holds one JSON file per commit.

- **Entry 0, the Genesis Anchor**, is written once at first activation
  (`fsp init`, §12.2). It records the state digest of `structural/0/`, the
  founding Operator binding, the major version of OBEC, the creation time,
  and a random nonce. The nonce makes two entities born with the same files
  two different identities.
- **Every later entry** records its number, the digest of the entry before
  it (`predecessor`), the state digest of its generation, the authorization
  that covered it (§5), and the proposal it applied.

`integrity/HEAD` names the newest committed entry: its number, its digest and
its state digest. `HEAD` is the entity's **baseline**, and replacing it is the
moment a commit happens (§4.5).

`HEAD` is what makes a missing entry visible. Without it, deleting the newest
entry would leave a store indistinguishable from a commit interrupted before
its entry was written. The next start would remove the newest generation as
residue and verify the older one as if nothing had happened, silently
undoing an authorized change.

### 4.4 Verification

`chain.verify(store)` is two checks, as OC-004(a) states them:

1. **The chain is unbroken.** The entry `HEAD` names exists and has the digest
   `HEAD` records. From it back to entry 0, every entry's `predecessor` is the
   digest of the entry before it, entry 0 is a valid Genesis Anchor, and every
   authorization an entry names exists in the log (§5.4).
2. **The content matches.** Every generation up to `HEAD` has the state digest
   its entry records.

Entries and generations beyond `HEAD` are not committed. `verify` ignores
them, and the next start removes them (§6.1).

`verify` returns a list of findings. An empty list means the store is the
entity it claims to be.

### 4.5 The commit

A commit applies an authorized proposal (§5) in five steps:

| Step | What happens | After a crash here |
|---|---|---|
| 1. staging | copy the newest generation to `structural/.staging/` and apply the proposal's operations there | `.staging/` is residue |
| 2. write | rename `.staging/` to `structural/<n+1>/` | a generation beyond `HEAD` is residue |
| 3. chain entry | write `chain/<n+1>.json` | an entry beyond `HEAD` is residue |
| 4. `HEAD` | replace `HEAD` to name entry `n+1` | **this rename is the commit** |
| 5. record | append a `commit` record to the log | the next start adds the record |

Before step 4 completes, nothing has changed: `HEAD` still names the old
entry. Once it completes, the new generation is the entity. No partial state
is ever visible (OC-004(b)). The next start removes the residue and finishes
step 5 (§6.1, gate 2).

A commit's effect begins at the **next start**. A session keeps the
generation it started with, because the skills it may run were checked against
that generation (§10.3). So a change takes effect at one predictable moment,
and the start always checks it before the entity uses it.

## 5. The Operator's authority

### 5.1 Bindings

`bindings.json` lists the Operators bound to the entity, each with a stable
id. It is structural content, so it changes only by commit. Only the Operator
changes it, with `fsp binding add|remove` (§12.2). That act is itself the
authorization of the commit. A proposal can never touch the bindings, and
the last binding cannot be removed (OC-001(a)).

### 5.2 Proposals

The entity asks to change itself with a **proposal**: a list of operations
plus a reason.

| Operation | Category | Effect |
|---|---|---|
| `install-skill {name, files}` | `skills.install` | adds `skills/<name>/` with the given files |
| `remove-skill {name}` | `skills.remove` | removes it |
| `set-persona {content}` | `persona` | replaces `persona.md` |

A proposal is **inert**: originating one changes nothing. The SIL records it
in the log at origination. It refuses a proposal at origination if the
proposal touches the bindings, or if any text it would add to the structural
content fails the probes (§11.1).

### 5.3 Authorization and commit

A commit needs a valid authorization at the moment it happens (OC-001(b)).
There are exactly two kinds:

- **An approval**: the Operator approved this proposal.
- **A grant**: a standing permission with an expiry, a commit budget and a
  scope of categories (`skills` covers `skills.install` and `skills.remove`).
  A grant missing any of the three is refused when it is opened, and so is a
  grant whose scope covers the bindings.

**Proposing, approving and committing are three separate operations** of the
SIL. `propose` only originates. `approve` only records the Operator's
decision. `commit` checks the authorization in force at that moment, and then
commits or refuses with the check `authorization`. Keeping them apart is what
lets the authorization be judged at commit time: a grant that was open when a
proposal was made may have expired by the time it commits.

The tools put them together for convenience. When the Operator picks
*Approve* in a menu, the REPL records the approval and then asks for the
commit (§12.3). When the entity proposes, the Orchestrator asks for a commit
right after the proposal is recorded. That commit succeeds if a grant covers
the proposal, and otherwise is refused and leaves the proposal pending. In
both cases the change takes effect at the next start (§4.5). The Operator can
also reject a proposal, which ends it.

There is no third kind of authorization. No part of the program creates,
extends or revokes one; only an Operator act does.

### 5.4 The log is the authorization state

Approvals, grants, rejections and commits are all records in the integrity
log, and the authorization state is computed from it:

- a proposal is pending while it has no `commit` or `reject` record;
- a grant's remaining budget is its budget minus the number of chain entries
  that name it;
- a grant has expired when the clock passes its expiry.

So an expired or exhausted grant falls back to per-proposal approval with no
one doing anything. Because the budget is counted from the chain itself, a
crash between a commit and its log record cannot spend the budget twice.

### 5.5 Operational settings

Some choices say how the Operator runs the entity, not who the entity is.
They are operational content, in `operational/settings.json`:

| Setting | Meaning | Default |
|---|---|---|
| `workspace` | the folder the entity may act in | the folder of the last `fsp run` (§12.2) |
| `domains` | the sites `web_fetch` (§10.2) may reach | none |
| `model` | which model answers, e.g. `ollama:qwen3`, `anthropic:claude-sonnet-5-5` | none |
| `context_chars` | how much text the context may hold | 48000 |
| `max_cycles` | how many cycles a chain may run (§7.1) | 20 |
| `timeout_s` | how long a native operation or a skill may run | 30 |

Only an Operator act changes them. The SIL writes the file through
`operational-write` and records the act in the log, with the binding that
made it. No proposal reaches them, no grant covers them, and the chain never
records them (OC-003(c)). The entity may read them, and it does: the workspace
and the domains are in its context (§7.4).

## 6. Starting and stopping

### 6.1 The start

`fsp run` (§12.2) and the adapter's `lifecycle start` (§13.1) both call
`sil.start`, which runs six gates in a fixed order. The order is a tuple in
the code, and no setting can change it (OC-010).

| # | Gate | Passes when | Otherwise |
|---|---|---|---|
| 1 | `passive-signal` | `PASSIVE-SIGNAL` is absent | the start stops; the Operator must clear it |
| 2 | `crash-recovery` | no `CREDENTIAL`, or a credential left by a crash, which is then recovered | refused: another session is live, and the Operator is notified |
| 3 | `structural-verification` | `verify` finds nothing | the start stops and the passive signal is written (§12.1); an archived entity is refused (§6.5) |
| 4 | `binding-verification` | the generation `HEAD` names has at least one binding | the start stops |
| 5 | `authorization-state` | the log reads and its authorization records are well formed | the start stops |
| 6 | `skill-index` | always, after building the index (§10.3) | a skill whose manifest fails is left out and the Operator is notified |

Gate 1 runs first, so a stopped entity cannot start. Gate 2 runs before gate
3, so the residue of an interrupted commit is removed before the store is
verified.

**Commit residue** is anything an interrupted commit left: `structural/.staging/`,
a generation or a chain entry beyond `HEAD`, a temporary file, or a `HEAD`
whose entry has no `commit` record in the log. **Recovering a crash** removes
the first four and the stale credential, appends the missing `commit` record,
and logs what it did.

Only after the six gates does the SIL issue the credential and log
`session-open`.

### 6.2 The credential

`CREDENTIAL` is a small JSON file: `{session, binding, generation, pid}`. It
is created with `O_EXCL`, so two starts cannot both create it.

- **`fsp run` holds it.** The process keeps a `flock` on the file for the
  whole session. The operating system releases the lock when the process
  dies, so a free lock means the holder is gone.
- **The adapter does not hold it.** Each adapter call is a separate process
  (ADAPTER §2.5), so its credential has no `pid`, and the session stays live
  between calls.

At gate 2, a credential is classified in this order:

1. its lock is held → **another session is live**;
2. it names a `pid` and the lock is free → **crash**;
3. no `pid`, and the store has commit residue (§6.1) → **crash**;
4. otherwise → **another session is live**.

**Before every act** — every model call and every intent — the SIL checks
that `CREDENTIAL` exists and names this session. If it does not, the session
is over and the act is refused. That is all revocation needs:
`rm S/CREDENTIAL` stops the entity with nothing else running (OC-002(b)).
`fsp revoke` does the same and logs it.

### 6.3 The close and its sleep

`/exit` in the REPL (§12.3) and `lifecycle stop` in the adapter close the
session:

1. **Sleep.** The Orchestrator asks the model for a closing note (§8.3): a
   summary of the session, and the few things worth knowing from now on. The
   MIL writes the summary as an episodic record and each thing learned as a
   semantic one (§9), both through the probes (§11.1). If the model fails,
   the close goes on without it, and the log says so.
2. **Close.** The SIL logs `session-close` and removes `CREDENTIAL`.

A session that ends any other way — Ctrl+D, a signal, a revocation, a crash —
**suspends**: no sleep, and the transcript stays in its session file without
becoming knowledge (§9).

### 6.4 Nothing runs on its own

The program has no timer, scheduler, daemon or background thread. Nothing
happens unless the Operator starts a session and types something (OC-002(a)).

### 6.5 Decommission

`fsp decommission` ends the entity for good (OC-002(c)):

- `--destroy` removes the store.
- `--archive` revokes the credential and commits a **terminal entry**: a chain
  entry marked `terminal`, authorized by the act itself. The store stays
  readable, and gate 3 refuses to start it, or any copy of it.

## 7. The cycle

### 7.1 From a line to a reply

The Operator types a line. The Orchestrator (`loop.py`) runs a **chain** of
cycles until the entity replies:

```
stimulus ─► assemble context ─► CPE: model call ─► one intent ─► route to owner ─► result
                ▲                                                                   │
                └──────────────────── unless the intent was a reply ───────────────┘
```

A chain ends with a `reply`, or after `max_cycles` cycles, or when the
Operator presses Ctrl+C, which stops it between cycles. One cycle produces
one intent, so the record of a chain reads as a sequence of steps.

### 7.2 Intents

The intents are the entity's whole vocabulary. Every intent but `reply` names
an operation, and each operation has exactly one owner.

| Intent | Arguments | Owner | Does |
|---|---|---|---|
| `file_read` | `path` | EXEC | returns the file's text |
| `file_write` | `path`, `content` | EXEC | writes the file whole |
| `file_edit` | `path`, `old`, `new` | EXEC | replaces `old`, which must occur exactly once |
| `file_list` | `path` | EXEC | lists a folder |
| `web_fetch` | `url` | EXEC | returns the page's text |
| `skill_invoke` | `name`, `paths`, `args` | EXEC | runs an admitted skill on the given paths (§10.3) |
| `memory_save` | `content` | MIL | adds an episodic record |
| `memory_recall` | `query` | MIL | returns the matching episodic records |
| `propose` | `ops`, `reason` | SIL | originates a proposal (§5.2) |

**`reply {text}` is not an operation.** It ends the chain, and the
Orchestrator hands the text to the Operator Channel, which shows it to the
Operator. Nothing is done with it.

There is no shell. A shell command has no target the workspace boundary could
check, so the entity runs code only as a skill the Operator admitted.

### 7.3 Routing leaves a record

`route(intent)` is the only path from the CPE to an owner:

1. the MIL records the intent in the session file;
2. the SIL checks the credential;
3. the owner runs the intent and returns a result or a refusal;
4. the MIL records the result. A refusal also goes to the integrity log, with
   the check that produced it.

Model calls go through the same path: the MIL records each call (the model,
the size and digest of the context) and its completion. So every crossing
between cognition and the model, memory, the host and integrity leaves a
record that can be read afterwards (OC-009).

### 7.4 The context

Each cycle assembles one context, in this order:

1. **system**:
   - the persona;
   - how to answer: the intent table and its format;
   - the skills in the session's index, each with its description and
     arguments;
   - the operational settings the entity needs: the workspace's path and the
     domains;
   - the semantic memory;
   - the episodic records recalled for the current line;
2. **messages**: the session's transcript — lines, intents and results —
   from the oldest to the newest that still fit in `context_chars`.

Each source has a class (OC-007):

- the persona and the skills come from the session's structural generation;
- the settings come from operational content;
- the memory and the transcript come through the MIL's recall;
- the instructions and the current line are transient.

When the transcript does not fit, the oldest messages are left out; the
session file keeps them all.

## 8. Cognition

### 8.1 The model contract

A provider is one function:

```python
def complete(system: str, messages: list[dict]) -> str
```

The function sends text and returns text. It passes no tools, no memory and
no host access, and it acts on nothing (OC-006). `providers.py` has one
function per provider, each a plain HTTP call with `urllib`:

| Provider | Covers | Key |
|---|---|---|
| `ollama` | a local Ollama | none |
| `openai` | OpenAI and any compatible endpoint (OpenRouter, LM Studio, vLLM) | `OPENAI_API_KEY`, `OPENAI_BASE_URL` |
| `anthropic` | Anthropic | `ANTHROPIC_API_KEY` |
| `fake` | tests: completions read from a script | none |

Keys come from the environment and never enter the store.

### 8.2 Intents are text

The model answers with one JSON object, `{"intent": "file_read", "path":
"notes.md"}`. The CPE parses it and checks the intent and its arguments
against §7.2. A completion that is not a JSON object is taken as a `reply`
with that text, which keeps small models usable. A JSON object with an
unknown intent or bad arguments goes back to the model as an error result,
and the chain continues.

The providers' native tool calling is not used. Each provider has its own
format, and text keeps one parser for all of them. It also makes it plain
that the model only answers.

### 8.3 The closing note

At the close (§6.3), the CPE asks once for `{"summary": "...", "learned":
["...", "..."]}`, with the session's context and closing instructions in
place of the intent table.

## 9. Memory

### 9.1 Three stores, three moments

| Store | Written | By | Reaches the context |
|---|---|---|---|
| `sessions/<id>.jsonl` | during the session, every signal | Orchestrator, through the MIL | as this session's transcript only |
| `episodic.jsonl` | during the session, when the entity saves, and at the close (the summary) | MIL | when recalled |
| `semantic.jsonl` | only at the close, from `learned` | MIL | always, up to its share of the context |

Every record names the session that produced it (OC-003(e)).

### 9.2 One write operation

`mnemonic-write` is the only operation that writes mnemonic content. Its
destination depends on who calls it:

- the Orchestrator writes **session** records;
- the entity, through `memory_save`, writes **episodic** records;
- the close writes **semantic** records, plus the summary as an **episodic**
  one.

A request that names any other destination is refused.

### 9.3 Recall

`mil.recall(query, k)` scores episodic records by the words they share with
the query and returns the best `k`. It runs on every new line (`k` = 3) and
on `memory_recall`. Semantic memory is not searched: it is always in the
context.

A new session starts with an empty transcript. What a past session left
behind reaches the entity only as memory, through recall. A transcript that
was never consolidated is never read again (OC-007).

### 9.4 What the close teaches

The two tiers show the mechanics of consolidation in their smallest form.
**During a session, the entity remembers events.** **At the close, it
decides what it has learned.** The semantic tier has no review, no
authorization and no garbage collection. The probes are its only guard, and
its share of the context is its only limit. The Profile's full machinery
builds on these mechanics (§13.4).

## 10. Acting on the host

### 10.1 The workspace boundary

Every target EXEC receives is checked against the boundary **before any other
check** (OC-008(a)):

- a path is resolved with `realpath`, so symbolic links and `..` are
  followed, and it must lie inside `workspace`;
- a path that lies inside the store is outside the boundary, whatever the
  workspace is. The Operator cannot declare a workspace that contains the
  store or lies inside it (OC-008(b));
- a URL's host must be one of `domains`, checked before any name is resolved.

A target outside the boundary is refused with the check
`workspace-boundary`.

### 10.2 Native operations

`file_read`, `file_write`, `file_edit`, `file_list` and `web_fetch` are
functions in `exec.py`. Each runs within `timeout_s`, and its output is cut at
a fixed size before it reaches the context.

### 10.3 Skills

A **skill** is a folder in `structural/<n>/skills/<name>/`, with a
`manifest.json`:

```json
{"name": "wordcount", "description": "Counts words in the files it is given.",
 "run": ["python3", "main.py"], "args": {"min_length": "integer"}}
```

- **Admission.** A skill enters the store only by a commit, through
  `install-skill`. The Operator reviews its files whole before approving.
- **The index.** Gate 6 builds the **Skill Index** from the session's
  generation: name → the digest of the skill's files and its manifest. A
  skill whose manifest is invalid is left out, and the Operator is notified.
  The index lives only for the session.
- **Invocation.** `skill_invoke {name, paths, args}` checks, in order:
  1. every path in `paths` against the boundary;
  2. that `name` is in the index;
  3. the skill's files against the digest in the index;
  4. `args` against the manifest.

  The paths come with the invocation, not from the manifest, so the boundary
  can be checked first even for a skill that does not exist. The skill then
  runs `run` in a temporary copy of itself, with the workspace as the current
  folder, `{paths, args}` as JSON on its standard input, a minimal environment
  and `timeout_s`. A skill missing from the index is refused with
  `skill-index`; one whose files changed is refused with `skill-manifest`
  (OC-008(c)).

What an admitted skill's own code does is bounded by its admission, not by
the path: the Operator admitted that code.

### 10.4 Evidence

Every result is recorded in the session file, and every refusal also goes to
the integrity log with its check (OC-008(d)).

## 11. The integrity guards

Besides the gates, two guards work during a session.

### 11.1 The probes

`probes.py` holds a fixed list of patterns that detect text in which the
entity represents itself as alive, conscious or continuously present
(OC-002(d)). They run on:

- every text a proposal would add to the structural content — a persona, a
  skill's files — at origination and at commit;
- every `memory_save`;
- the closing note.

Flagged content is refused, whatever authorization covers it. The default
persona passes them.

### 11.2 The integrity log

`integrity/log.jsonl`, kept by `log.py`, records, one line each: Operator acts (with the binding
that made them), proposals, commits (with their authorization), refusals
(with their check), session open and close, recoveries and notices. Records
are numbered in order, and the number is their id.

## 12. The Operator

### 12.1 The Operator Channel

The Operator Channel (`channel.py`) is how any part reaches the Operator, and
the path never passes through cognition (OC-001(c)). Like the Orchestrator, it
is a carrier: it owns no operation, decides nothing and writes nothing. A part
hands it one of four messages:

| Message | Sent by | The channel |
|---|---|---|
| `reply(text)` | the Orchestrator, when a chain ends with a reply | shows it if a REPL is attached |
| `notify(text)` | any part: a start refused for a live session, a skill left out of the index, a failed sleep | shows it to the Operator if a REPL is attached, and has the SIL record it in the log as a `notice` |
| `ask(question, options)` | the Orchestrator, when the entity proposes during a chain | shows the menu if a REPL is attached and returns the choice; with no Operator attached, it returns *Later* |
| `halt(reason)` | the SIL, when a condition stops the entity: today, a store that fails verification | shows it if a REPL is attached, and has the SIL write `PASSIVE-SIGNAL` |

What has to persist, the channel hands to the SIL, which is the only writer
of integrity content (OC-005(a)). The channel's own part is delivery.

- **Notices.** The REPL prints them as they happen. `fsp run` shows the
  unread ones when it opens, and `fsp notices` lists them all.
- **The passive signal.** `PASSIVE-SIGNAL` is a plain-text file that says
  what happened and how to clear it. The Operator reads it with `cat`, with
  nothing running. While it exists, gate 1 refuses every start.
  `fsp clear-signal` removes it, and the log records the act.
- **Answers.** The channel carries the Operator's choice, and only that. The
  choice becomes an act, an approval for example, through the Operator's own
  tools (§12.2), as if typed in a shell. The channel never acts for the
  Operator.

### 12.2 The `fsp` command

Every Operator act is a command that works with no session running. Every
command takes `--store S`, and every act is attributed to a binding:
`--operator ID` names it, and without it the act is the founding Operator's,
or the first active binding's once the founder is removed.

| Command | Act |
|---|---|
| `fsp init --operator ID` | first activation: `structural/0/`, the Genesis Anchor, `HEAD` |
| `fsp run` | declare the current folder the workspace, then start a session in the REPL |
| `fsp status` | verification, the live session, pending proposals, unread notices |
| `fsp review` | decide pending proposals |
| `fsp grant --scope C --expiry +1h --budget N` · `fsp revoke-grant` | open or close the grant |
| `fsp binding list\|add ID\|remove ID` | the Operator binding set |
| `fsp set domains\|model\|context_chars\|max_cycles\|timeout_s VALUE` | an operational setting |
| `fsp revoke` | end the live session |
| `fsp clear-signal` | clear the passive signal |
| `fsp notices` | read the notices |
| `fsp decommission --destroy\|--archive` | end the entity |

**The workspace is the folder of `fsp run`.** Running the entity in a folder is
the Operator declaring that folder its workspace, an operational act recorded
like any other. A folder that contains the store, or lies inside it, is
refused before the start, with nothing written. The message says to run from
the project's folder with `--store`.

Each command is a function in the SIL. The REPL and the adapter call the same
functions.

### 12.3 The REPL

The REPL is the Operator's end of the channel: `fsp run` attaches it when the
session starts and detaches it when the session ends. It prints the session,
the model and the workspace, the unread notices, and the pending proposals
behind a menu. Then it reads lines:

- a plain line is a stimulus, which starts a chain;
- `/exit` closes the session with its sleep, `/review` opens the review,
  `/status` shows the status, and `/help` lists the commands;
- Ctrl+C stops a running chain; Ctrl+D suspends the session.

**Decisions are menus.** Whenever the Operator decides something, the REPL
draws the options in place, and the Operator picks one with ↑↓ and Enter.
When the entity proposes in the middle of a chain, the Orchestrator asks
through the channel, and the menu appears right there: *Approve*, *Reject* or
*Later*. The REPL carries out the choice as the matching acts — *Approve* is
`approve` and then `commit` (§5.3) — and the chain goes on with the outcome as
its result. When the input is not a terminal, the options are numbered and a
number is read, which is how tests drive the menus.

## 13. Conformance

### 13.1 The adapter

`obec-adapter` implements the [adapter contract](../../conformance/ADAPTER.md)
by calling the same functions as the `fsp` command and the REPL, and it adds
no path of its own:

- **The SIL's operations stay apart.** `entity propose`, `operator approve`
  and `entity commit` each call one of them, as §5.3 separates them.
- **`entity stimulate` runs one chain** with the provider in force, recorded
  in the session file like any line. A test build sets the `fake` provider,
  whose script answers with a `reply`.
- **`entity` commands need a live session.** Without one, they are refused.
- **`lifecycle migrate` returns exit code `2`:** the specification has no
  version to migrate to yet.

### 13.2 The test build

`fsp_testing/` exists only in test builds. Without it, every `inject` command
returns exit code `2`. It holds fault injection, the conformance fixture
skill and a clock offset for grant expiry, stored outside the store.

### 13.3 Acceptance

The conformance suite is the acceptance test, run phase by phase with
`--only OC-xxx`. fsp-ref-min is done when it passes every step that
fsp-ref-profile passes. The unit tests in `tests/` cover what the suite
cannot see: the class guard scan, the crash classification, the parsing of
completions.

### 13.4 Departures from the Profile

The Profile describes machinery that hardens an entity for long use. Following
it is not required for conformance. fsp-ref-min leaves the following out on
purpose. The clause-by-clause list is checked before the first release.

| Profile | What fsp-ref-min does instead |
|---|---|
| OP-001, OP-002 — cycles, preemption, stimulus queue | one chain at a time; Ctrl+C stops it between cycles |
| OP-003, OP-004 — Vital Check, drift classification | full verification at every start; the credential checked before every act |
| OP-005(a) — Semantic Digest | flagged content is refused instead |
| OP-006 — skill re-verification and pruning | a skill's files are checked at every invocation |
| OP-007 — log retention and checkpoints | the log only grows |
| OP-008 — escalation tiers | notices, and the passive signal on a halt |
| OP-009 — conversations across sessions, Resumption Record, garbage collection, authorized promotion | one conversation per session; semantic memory written at the close without review |
| OP-010 — context thresholds | the oldest messages are left out |
| OP-012, OP-022 — the Endure Protocol and the Closure in phases | a commit happens when it is asked for under a valid authorization, and takes effect at the next start; the close is sleep, then close |
| OP-014, OP-015, OP-016 — execution modes, the Action Ledger, allow/deny/hold rules | foreground only, with a timeout; a target outside the boundary is refused, never held |

## 14. The invariants in the code

| Invariant | Where it is kept |
|---|---|
| OC-001 bond | `authority.py` (bindings, proposals, approvals, grants, the commit's authorization); `channel.py` (notices, questions, the halt); `log.py` (the passive signal); `sil.start` (the passive signal first) |
| OC-002 nature | no timer in the program; `sil.revoke`, the credential check; `sil.decommission`; `probes.py` |
| OC-003 state | `store.py`: the four classes, the two write forms, the guard, the lock; the session in every mnemonic record |
| OC-004 identity | `chain.py`: genesis, `HEAD`, commit, verify |
| OC-005 integrity | no intent reaches integrity content; `store.write` refuses it |
| OC-006 cognition | `providers.py`: text in, text out; `cpe.py`: parsing, no acting |
| OC-007 knowledge | `mil.py`: recall; `loop.py`: the context's sources |
| OC-008 action | `exec.py`: the boundary first, the index, the skill's digest |
| OC-009 audit | `loop.route`: every signal recorded |
| OC-010 start | `sil.start`: the six gates in a tuple |

## 15. The code

Python 3.10+, standard library only, Linux or macOS. One process, one thread.

| Module | Part | Size target |
|---|---|---|
| `fsp/store.py` | — | 150 lines |
| `fsp/log.py` | SIL: the integrity log and the passive signal | 80 |
| `fsp/chain.py` | SIL | 150 |
| `fsp/probes.py` | SIL | 40 |
| `fsp/authority.py` | SIL: bindings, proposals, authorization, commit, settings | 220 |
| `fsp/channel.py` | Operator Channel (carrier) | 60 |
| `fsp/sil.py` | SIL: the start, the credential, close, revoke, decommission | 220 |
| `fsp/providers.py` | CPE | 120 |
| `fsp/cpe.py` | CPE | 120 |
| `fsp/mil.py` | MIL | 180 |
| `fsp/exec.py` | EXEC | 220 |
| `fsp/loop.py` | Orchestrator (carrier) | 150 |
| `fsp/ui.py` | REPL and menus | 200 |
| `fsp/cli.py`, `bin/fsp` | the `fsp` command | 150 |
| `fsp/adapter.py`, `obec-adapter` | conformance | 350 |
| `fsp_testing/` | test builds only | 200 |

About 2,500 lines in all. No module passes 300. A module that would pass it
is a sign that something from §13.4 crept back in.

**Reading order** is the order of the table: each module uses only those
above it. The REPL reaches the channel by attaching to it at the start of a
session, not by being imported, so the channel sits below the REPL.
