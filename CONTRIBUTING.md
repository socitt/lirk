# Contributing to lirk

## Before changing code

Read [`docs/dev/DESIGN.md`](docs/dev/DESIGN.md). It describes lirk as
it is now, and why. Its **settled decisions** section lists ideas
that have already been weighed and rejected, so a change doesn't
reopen one of them without new evidence.

Some constraints are not negotiable, because they are the reason lirk
exists (DESIGN §1):

- Each test file runs as **one direct `subprocess.run()` call**: no
  process groups or sessions, no pseudo-terminals, no `shell=True`, and
  no "write results to a file, read them back" step.
- **Serial execution.** No parallel workers.
- **No runtime dependencies.** Standard library only, Python 3.11+.

If a fix seems to need one of those, raise it in an issue rather than
working around it.

**Never let a cached result go stale.** Any change to what a target's
check or test run *means* must bump `ACTION_VERSION` in
`lirk/cache.py`, so old cached passes are discarded rather than
trusted.

## Running the tests

Both of these must pass. They aren't redundant: the second is lirk
testing itself, and the first is the independent check that catches
lirk wrongly reporting itself green.

```sh
python3 -m unittest discover -s tests -t .
python3 -m lirk test //...
```

CI runs both on Python 3.11, 3.12 and 3.13 and on macOS, plus
`lirk verify` and an install check.

Tests use real subprocesses on purpose: mocking them would undercut the
thing lirk exists to prove. Each directory under `tests/fixtures/` is a
small repo that isolates one behaviour.

## Where things live

| Path | What |
|---|---|
| `lirk/` | The code. `docs/dev/DESIGN.md` §7 maps each module. |
| `docs/*.md` | User documentation, published at <https://socitt.github.io/lirk/>. |
| `docs/dev/` | Maintainer docs: [DESIGN](docs/dev/DESIGN.md), [TASKS](docs/dev/TASKS.md) (backlog and roadmap), [KNOWN_ISSUES](docs/dev/KNOWN_ISSUES.md), [RELEASING](docs/dev/RELEASING.md). |
| `docs/archive/` | History: the original docs and early dogfooding reports. |

## Releasing

See [`docs/dev/RELEASING.md`](docs/dev/RELEASING.md). Publishing a
GitHub release uploads the package to PyPI automatically.
