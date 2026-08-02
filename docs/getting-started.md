---
layout: default
title: Getting started
---

# Getting started

This page takes you from nothing to a working lirk setup, then covers
adopting lirk in a repo that already exists. Every command and every
block of output below is a real transcript, not an illustration.

For the target schema in full, see
[BUILD.lirk format](https://socitt.github.io/lirk/build-format.html).
For what lirk does internally and why, see
[How it works](https://socitt.github.io/lirk/how-it-works.html).

## Requirements

Python 3.11 or newer. Nothing else — lirk has no third-party
dependencies.

```sh
pip install git+https://github.com/socitt/lirk.git
```

That puts a `lirk` console script on your `PATH`. To check:

```sh
lirk build --help
```

---

## Part 1 — a worked example from zero

We'll build a two-package repo where one package depends on the other.
Start with an empty directory.

### 1. Mark the repo root

```sh
touch .lirk-root
```

lirk resolves `//`-prefixed labels relative to the repo root, and finds
that root by walking up from your current directory looking for this
marker. **Create it before anything else.** Without it lirk silently
treats whatever directory you happen to be standing in as the root,
which produces confusing "does not exist" errors rather than an honest
"you're in the wrong place" — see [Troubleshooting](#troubleshooting).

The file can stay empty. Later it can also carry an `ignore` list; see
[Part 2](#excluding-directories-that-arent-yours).

### 2. Write the source files

```
.lirk-root
greeting/
    greet.py
    test_greet.py
    BUILD.lirk
app/
    cli.py
    test_cli.py
    BUILD.lirk
```

`greeting/greet.py`:

```python
def greet(name):
    return f"Hello, {name}!"
```

`greeting/test_greet.py`:

```python
import unittest

from greeting.greet import greet


class GreetTest(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet("world"), "Hello, world!")
```

`app/cli.py`, which depends on the other package:

```python
from greeting.greet import greet


def banner(name):
    return greet(name).upper()
```

`app/test_cli.py`:

```python
import unittest

from app.cli import banner


class BannerTest(unittest.TestCase):
    def test_banner(self):
        self.assertEqual(banner("world"), "HELLO, WORLD!")
```

Plain `unittest`. lirk imposes no test framework of its own and needs
no `if __name__ == "__main__"` block — it runs each src through
`python3 -m unittest`.

### 3. Declare the targets

One `BUILD.lirk` per package directory. `greeting/BUILD.lirk`:

```toml
[[target]]
name = "greeting"
type = "library"
srcs = ["greet.py"]

[[target]]
name = "greeting_test"
type = "test"
srcs = ["test_greet.py"]
deps = [":greeting"]
```

`app/BUILD.lirk`:

```toml
[[target]]
name = "app"
type = "library"
srcs = ["cli.py"]
deps = ["//greeting:greeting"]

[[target]]
name = "app_test"
type = "test"
srcs = ["test_cli.py"]
deps = [":app"]
```

Two label forms appear here: `:greeting` for a sibling in the same
package, and `//greeting:greeting` for a target in another one. A
target's `name` need not match its package or its filenames — `app`
and `app_test` both live in package `app`, so their labels are
`//app:app` and `//app:app_test`.

### 4. Build and test

`build` validates: every declared file exists, and every src parses as
Python. There is no compilation and no artifact output.

```
$ lirk build //...
  built  //greeting:greeting
  built  //app:app
  built  //app:app_test
  built  //greeting:greeting_test
lirk: 4 built, 0 cached, 0 failed, 0 skipped
lirk: OK
```

`test` runs the test targets, building their dependencies first:

```
$ lirk test //...
  built  //greeting:greeting
  built  //app:app
  PASS   //app:app_test
  PASS   //greeting:greeting_test
lirk: 2/2 tests passed
lirk: OK
```

Run it again and nothing re-runs — every fingerprint still matches:

```
$ lirk test //...
  cached  //greeting:greeting
  cached  //app:app
  cached  //app:app_test
  cached  //greeting:greeting_test
lirk: 2/2 tests passed
lirk: OK
```

### 5. Watch a change propagate

Append a function to `greeting/greet.py` and re-run. Note that
`//app:app` rebuilds too, even though nothing in `app/` was touched —
it depends on `//greeting:greeting`, and a dependency's fingerprint is
folded into its dependents':

```
$ lirk test //...
  built  //greeting:greeting
  built  //app:app
  PASS   //app:app_test
  PASS   //greeting:greeting_test
lirk: 2/2 tests passed
lirk: OK
```

Invalidation is by **file content**, not timestamp. `touch` changes
nothing; a fresh clone doesn't rebuild the world; reverting an edit
returns you to the cached result.

### 6. Gitignore lirk's artifacts

```
.lirk-cache.json
.lirk-cache.json.*.tmp
__pycache__/
*.pyc
```

`.lirk-cache.json` lives at the repo root and is purely local state.
Don't commit it and don't share it between machines.

That's the whole workflow.

---

## Part 2 — adopting lirk in an existing repo

Work through these in order; each is a place a real repo tends to
stumble.

### Deciding what a package is

A **package** is any directory with a `BUILD.lirk` in it. Packages
don't nest meaningfully — a `BUILD.lirk` describes the files in its own
directory, and every path inside it (`srcs`, `data`) is relative to
that directory.

Start coarse: one `library` target per directory holding the `.py`
files that belong together, plus one `test` target per directory
holding its test files. Split further only when you want finer
invalidation, since a target is the unit of caching — a 20-src library
re-validates in full when any one of the 20 changes.

`srcs` may name a file in a subdirectory (`sub/helper.py`), so a
package need not be flat. Test srcs in subdirectories run as their
dotted module path and need no `__init__.py`.

### Getting the imports right

This is where real repos actually stumble. Each test src is run with:

- **`cwd` set to the package directory**, so the package directory is
  `sys.path[0]`, and
- **the repo root prepended to `PYTHONPATH`**.

Two import styles therefore work, and you can mix them:

```python
from greet import greet                # sibling in the same package
from greeting.greet import greet       # root-relative, any package
```

Root-relative is the convention Bazel and Please encourage, and it's
what makes cross-package imports work at all.

**The one trap: don't give a module the same name as its own package
directory.** A file `greeting/greeting.py` shadows the package
`greeting` whenever a test in that same directory runs, because the
package directory is searched first:

```
ModuleNotFoundError: No module named 'greeting.greeting'; 'greeting' is not a package
```

The fix is a rename, not a lirk setting. This bites only inside the
directory that owns the colliding name — the same import from another
package resolves fine, which is what makes it confusing when it hits.

### Declaring non-Python inputs as `data`

Anything a target reads at runtime but which isn't Python — a fixture
file, a testdata tree, a golden file — belongs in `data`, not `srcs`.
`data` entries are fingerprinted exactly like srcs but never parsed:

```toml
[[target]]
name = "parser_test"
type = "test"
srcs = ["test_parser.py"]
deps = [":parser"]
data = ["testdata"]
```

Getting this wrong fails in two directions. A non-Python file in
`srcs` gets a bogus syntax error:

```
  FAIL   //greeting:greeting: fixture.txt: syntax error: invalid syntax (fixture.txt, line 1)
```

Leaving it undeclared entirely is worse and silent: edits to it never
invalidate anything, so you get a cached PASS against inputs that
changed. A `data` entry may name a **directory**, fingerprinted
recursively — prefer that over listing files by hand, which goes stale
the first time someone adds a file and forgets.

### Excluding directories that aren't yours

Directories starting with `.` are skipped automatically. For anything
else that contains `BUILD.lirk` files which aren't your targets — a
vendored dependency, a nested checkout, a fixture tree — list it in
`.lirk-root`, which doubles as repo config:

```toml
ignore = ["tests/fixtures", "vendor"]
```

Paths are relative to the repo root, and each entry excludes the
directory and everything under it.

### Verifying the migration honestly

Run your existing test command and `lirk test //...`, and confirm they
agree on what passes. Keep the existing runner around at least through
the trial; lirk's own repo runs both permanently, on the grounds that
an independent runner is the only thing that would catch lirk
reporting a false green about itself.

---

## Command reference

The entire CLI is two subcommands:

| Command | Effect |
|---|---|
| `lirk build <label>` | Check every declared file exists and every src parses as Python, for the target and its transitive deps. |
| `lirk test <label>` | Run each test src via `python3 -m unittest`, after building its deps. |

| Flag | Applies to | Effect |
|---|---|---|
| `--force` | both | Ignore cached results and re-do everything in scope. Doesn't delete the cache file. |
| `--rebuild` | `build` | Alias for `--force`. |
| `--rerun` | `test` | Alias for `--force`. |
| `--root <path>` | both | Use this repo root, overriding `.lirk-root` discovery entirely. |

Labels:

| Form | Meaning |
|---|---|
| `//pkg:name` | One target in package `pkg`. |
| `//:name` | A target in the root package. |
| `:name` | A sibling target — **valid inside `deps` only**, not on the command line. |
| `//...` | Every target in the repo. |

`//...` is the only wildcard. `//app/...` is *not* supported and
reports `unknown target: //app/...`.

## Reading the output

One line per target, in dependency order:

| Line | Meaning |
|---|---|
| `built  <label>` | Validated (or re-validated) just now. |
| `PASS   <label>` | Test target ran, all srcs passed. |
| `cached <label>` | Fingerprint unchanged since the last success; nothing ran. |
| `FAIL   <label>: <reason>` | Failed, with the raw test output printed beneath. |
| `SKIP   <label>: dependency <dep> failed` | Not attempted, because something it depends on failed. |

Then a summary and `lirk: OK` or `lirk: FAILED`. Exit status is **0**
on OK, **1** on any failure or usage error.

Two behaviours worth knowing up front:

- **Only successes are cached.** A failure is always retried next run,
  even if nothing changed.
- **`SKIP` is not a pass.** A target whose dependency failed is never
  run and never counted as passing, so a broken library can't produce a
  green test run beneath it.

Test output is passed through raw — lirk never summarizes or reformats
what `unittest` printed.

## Troubleshooting

**`lirk: //:app: dependency '//greeting:greeting' does not exist`, and
the target obviously does exist.** You're in a subdirectory and there's
no `.lirk-root` above you, so lirk took the subdirectory as the repo
root and can't see anything outside it. Create the marker at your real
root, or pass `--root`.

**`lirk: unknown target: //app`.** A label needs both parts —
`//package:name`. `//app` names no target. The same message appears for
`//app/...`, which isn't supported wildcard syntax.

**`lirk: circular dependency: //app:app -> //greeting:greeting ->
//app:app`.** The full cycle path is in the message; break any edge in
it.

**`lirk: <file> (target #2): unknown key(s): dpes`.** A typo'd or
unsupported key in a `[[target]]` table. Rejected deliberately: a
transposed `dpes` would otherwise silently produce a target with no
dependency edges, which then never invalidates when its real
dependency changes.

**`FAIL ...: missing source file(s): greet.py`.** A declared src or
data path doesn't exist. Only that target fails; unrelated targets
still build, and its dependents report `SKIP`.

**`FAIL ...: fixture.txt: syntax error: invalid syntax`.** A
non-Python file is in `srcs`. Move it to `data`.

**`FAIL ...: 1 of 2 src files failed: test_empty -- contained no
tests: test_empty`.** A src in a `test` target defined no tests. That's
a failure, not a pass — a file that tests nothing is nearly always a
mistake (a bad rename, a lost import) rather than an intention.

**`ModuleNotFoundError: No module named 'greeting.greeting'; 'greeting'
is not a package`.** A module named the same as its own package
directory. See [Getting the imports
right](#getting-the-imports-right).

**`lirk: //greeting:greeting is type 'library', not 'test'`.** `lirk
test` needs a `test` target. Use `lirk build` for a library, or
`//...` to run everything.

**A test hangs.** Test subprocesses get `stdin` connected to
`/dev/null`, so a test reading stdin fails fast rather than silently
eating your keystrokes. There's also a 600-second per-src timeout.

## If you're trialling lirk

lirk's [v1 stability
criteria](https://github.com/socitt/lirk/blob/main/docs/TASKS.md)
require a track record across at least three distinct real repos, and
what makes a trial useful is evidence rather than an impression. If
you're willing, keep a note of:

- **Roughly how many `lirk build` / `lirk test` invocations** you ran.
- **Any `signal: hangup`**, or any other failure that isn't your code's
  fault. This is the exact failure mode lirk was built to avoid, and
  it has never been observed — a single occurrence is a significant
  finding.
- **Any cache-correctness disagreement:** a `cached` result that
  differs from what `--force` produces on the same tree. Spot-check
  this occasionally with `lirk test //... --force`. One such bug has
  been found so far (an undeclared fixture directory producing a stale
  PASS), and it was found exactly this way.
- **Anything in this guide that turned out to be wrong or missing.**

Issues and observations: <https://github.com/socitt/lirk/issues>.
