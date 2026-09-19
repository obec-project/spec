# fsp-ref

**Filesystem Substrate Platform** — a reference implementation of
OBEC-Core 0.9.1 over a filesystem and POSIX primitives: atomic rename,
append-only files, `fsync`, `flock`.

**Status: in progress. Not conformant, and not usable as an entity yet.**
The store, the integrity document, the chain back to the Genesis Anchor, and
first activation are in place. Sessions, commits, the start gates and
everything cognitive are not.

Python 3.9+, standard library only, Linux or macOS.

```sh
python3 -m unittest discover -s tests          # the implementation's own tests
./obec-adapter lifecycle init --store /tmp/S --operator op-1
./obec-adapter lifecycle verify --store /tmp/S
```

The adapter implements the [conformance adapter contract](../../conformance/ADAPTER.md)
and returns exit code `2` for every command not built yet. `fsp_testing/`
holds fault injection and exists only in test builds: without it, every
`inject` command exits `2`.

## Layout

| | |
|---|---|
| `fsp/store.py` | the store layout, the two write forms, the content-class guard |
| `fsp/digest.py` | canonical JSON, the integrity document, digests |
| `fsp/chain.py` | the Genesis Anchor, chain entries, `HEAD` |
| `fsp/verify.py` | verification, returning findings |
| `fsp/sil.py` | the integrity log, scaffolding, first activation |
| `fsp/adapter.py`, `obec-adapter` | the conformance adapter |
| `fsp_testing/` | test builds only: fault injection |
