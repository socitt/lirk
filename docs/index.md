---
layout: default
title: Overview
---

# lirk

A minimal, Bazel/Please-inspired build tool for Python monorepos.

## Why this exists

lirk exists because of a bug that couldn't be fully root-caused in
[Please](https://please.build), a Bazel-alike build tool, while using
it on iSH-AOK (a Linux userland running natively on iOS). Build and
test actions would intermittently fail with `signal: hangup` —
non-deterministically, with no problem in the underlying build/test
logic itself. Debugging narrowed the likely cause to something in
Please's process-group/session-control handling around subprocess
execution.

Rather than keep chasing a bug in someone else's process model, lirk
takes the opposite approach: use the simplest possible subprocess
invocation model available, and avoid every pattern suspected of
contributing to the original failure. Concretely, lirk:

- Never creates new process groups or sessions for spawned actions.
- Never uses pseudo-terminals to spawn build/test commands.
- Runs every action via a single, direct `subprocess.run()` call.
- Does no process-tree sandboxing or isolation of build actions.
- Never splits test execution into a "run, write results to a file,
  read the file back" sequence.
- Runs builds serially in v1 — no per-action process groups, no
  parallelism, until the v1 stability criteria below are met.

That's a narrower, more conservative subprocess model than a
general-purpose build tool needs — that's the point. See
[How it works](how-it-works.html) for the target model and execution
pipeline this trades in for.

## Installation

Requires Python 3.11 or newer and nothing else — no third-party
dependencies.

```sh
pip install git+https://github.com/socitt/lirk.git
```

Or from a clone, for development:

```sh
git clone https://github.com/socitt/lirk.git
cd lirk
pip install -e .
```

## Quick start

```sh
# at your repo root
touch .lirk-root

# describe a target in path/to/pkg/BUILD.lirk
lirk build //path/to/pkg:mytarget
lirk test  //path/to/pkg:mytarget_test

# whole repo
lirk build //...
lirk test  //...
```

A target declares `srcs`, `deps`, and `data` — the last for inputs that
are not Python source, such as a fixture file or a whole fixture
directory, which are fingerprinted so edits invalidate the cache but
are never syntax-checked:

```toml
[[target]]
name = "parser_test"
type = "test"
srcs = ["test_parser.py"]
deps = [":parser"]
data = ["testdata"]
```

`.lirk-root` can stay empty, or carry an `ignore` list for directories
holding `BUILD.lirk` files that are not your targets — a vendored
dependency, or a fixture tree:

```toml
ignore = ["tests/fixtures", "vendor"]
```

See [BUILD.lirk format](build-format.html) for the full target schema.

## Scope (v1)

lirk currently only supports Python targets: `library` and `test`.
No binaries, no genrules, no other languages yet. The goal is to
prove the core approach (dependency graph, incremental builds via
content hashing, direct subprocess execution) works reliably before
expanding scope.

## Status

Early development, not yet stable. Parallelism work and any scope
expansion are on hold until *all three* v1 criteria hold:

1. **Self-hosting** — lirk builds and tests its own source through its
   own `BUILD.lirk` files. **Met.** `lirk build //...` builds 13
   targets and `lirk test //...` runs the suite through lirk. It runs
   alongside the plain `unittest` invocation rather than replacing it:
   an independent runner is what would catch lirk reporting a false
   green about itself.
2. **Track record on real repos** — at least 200 cumulative
   `lirk build`/`lirk test` invocations across at least 3 distinct real
   repos, with zero `signal: hangup` occurrences and zero
   cache-correctness bugs. **Not met**, and the only outstanding
   criterion. The invocation count and both failure-mode clauses are
   satisfied; self-hosting supplies a second repo; one more distinct
   consumer is what remains.
3. **Known issues clear** — no open entries beyond ones explicitly
   marked cosmetic-only. **Met.**

These are deliberately non-subjective, replacing the vaguer "proven
stable" language they grew out of. Current status is tracked in
[TASKS.md](https://github.com/socitt/lirk/blob/main/docs/TASKS.md), and
[DESIGN.md](https://github.com/socitt/lirk/blob/main/docs/DESIGN.md)
carries the architecture. The
[known issues log](https://github.com/socitt/lirk/blob/main/docs/KNOWN_ISSUES.md)
and
[dated assessments](https://github.com/socitt/lirk/tree/main/docs/assessments)
track real bugs found (and fixed) through actual usage.

MIT licensed — see
[LICENSE](https://github.com/socitt/lirk/blob/main/LICENSE).
