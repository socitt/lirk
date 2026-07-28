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
  parallelism, until serial execution is proven stable.

That's a narrower, more conservative subprocess model than a
general-purpose build tool needs — that's the point. See
[How it works](how-it-works.html) for the target model and execution
pipeline this trades in for.

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

See [BUILD.lirk format](build-format.html) for the target schema.

## Scope (v1)

lirk currently only supports Python targets: `library` and `test`.
No binaries, no genrules, no other languages yet. The goal is to
prove the core approach (dependency graph, incremental builds via
content hashing, direct subprocess execution) works reliably before
expanding scope.

## Status

Early development. Not yet self-hosting — lirk is tested with plain
`unittest`, not with itself. The
[known issues log](https://github.com/socitt/lirk/blob/main/docs/KNOWN_ISSUES.md)
and
[dated assessments](https://github.com/socitt/lirk/tree/main/docs/assessments)
track real bugs found (and fixed) through actual usage.

MIT licensed — see
[LICENSE](https://github.com/socitt/lirk/blob/main/LICENSE).
