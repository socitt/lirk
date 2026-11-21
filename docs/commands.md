---
layout: default
title: Commands
---

# Commands

```
lirk test   <label>...   run tests (and check what they depend on)
lirk build  <label>...   check targets without running tests
lirk init                draft BUILD files for an existing repo
lirk fix    [label...]   add missing deps from your imports
lirk verify [label...]   recheck cached results against fresh runs
lirk clean               delete the cache
lirk --version
```

Every command works from any directory inside the repo. `--root
<path>` overrides where lirk thinks the repo root is.

## Choosing targets

| Label | Selects |
|---|---|
| `//...` | Everything in the repo. |
| `//app/...` | Everything in `app/` and the directories beneath it. |
| `//app:all` | Everything in `app/` itself. |
| `//app:app_test` | One target. |
| `//:tool` | A target in the root directory. |

Give as many as you like: `lirk test //app/... //lib:lib_test`.

With `lirk test`, a pattern selects only the test targets it covers,
and covering none isn't an error. Naming a non-test target explicitly
*is* an error. A pattern that matches nothing at all is reported,
since that's usually a typo.

## `lirk test`

Runs the selected test targets, after checking everything they depend
on. Each test file runs in its own process, with output passed through
exactly as your test runner printed it.

| Option | Effect |
|---|---|
| `--force` (or `--rerun`) | Ignore the cache and run everything selected. The cache is kept. |
| `--fail-fast` | Stop at the first failure instead of running the rest. |

## `lirk build`

Checks the selected targets and everything they depend on: every file
exists, every src is valid Python, and every import is covered by
`deps`. Tests are not run. This is a fast way to catch a broken import
or a missing file.

| Option | Effect |
|---|---|
| `--force` (or `--rebuild`) | Ignore the cache and recheck everything selected. |
| `--fail-fast` | Stop at the first failure. |

## `lirk init`

Writes a `BUILD.lirk` for every directory of Python files that doesn't
have one, then fills in deps from the imports. Creates `.lirk-root` if
needed. Never changes an existing `BUILD.lirk`. See
[Existing repos](adopting.html).

| Option | Effect |
|---|---|
| `--dry-run` | List the files it would write, and write nothing. |

## `lirk fix`

Adds every missing `deps` entry that the import check finds (default:
whole repo). Edits keep your comments and layout, and each edited file
is re-read to confirm it says exactly what was intended before being
saved. Anything ambiguous is listed as `MANUAL` instead of guessed:
a file listed by two targets, or an edge that would create a cycle.
The command fails if anything is left for you to fix.

| Option | Effect |
|---|---|
| `--dry-run` | Show what it would add, and change nothing. |

## `lirk verify`

Reruns cached results from scratch (default: whole repo) and compares.
If something cached as passing now fails, lirk reports it as `STALE`,
removes it from the cache, and fails. A stale result means a target
depends on something it doesn't declare, usually a data file.

| Option | Effect |
|---|---|
| `--sample N` | Recheck a random N results instead of all of them. |
| `--seed S` | Reproduce a previous sample. |

## `lirk clean`

Deletes `.lirk-cache.json`, so the next run does everything again.
(You rarely need it: entries for targets you delete are dropped
automatically.)

## Reading the output

Each target gets one line, in dependency order:

| Line | Meaning |
|---|---|
| `built  //lib:lib` | Checked just now. |
| `PASS   //lib:lib_test (2.4s)` | Tests ran and passed, in that much time. |
| `cached  //lib:lib` | Unchanged since it last passed; nothing ran. |
| `FAIL   //lib:lib_test: ...` | Failed; the test output follows. |
| `SKIP   //app:app: dependency //lib:lib failed` | Not attempted, because something it needs failed. |

At the end, long runs list their slowest tests, failing runs list what
failed (so you don't have to scroll back), and the last line is
`lirk: OK` or `lirk: FAILED`. The exit status is 0 for OK and 1
otherwise.

Only passes are cached: a failure always runs again next time, even if
nothing changed.
