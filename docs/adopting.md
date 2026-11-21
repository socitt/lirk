---
layout: default
title: Existing repos
---

# Using lirk in an existing repo

Most repos can be converted in a few minutes: `lirk init` writes the
BUILD files, and you review what it couldn't know. This page covers
that review, and the handful of rules that decide whether a repo
converts cleanly.

## 1. Run `lirk init`

From the top of your repo:

```
$ lirk init
  created app/BUILD.lirk: library :app (1 srcs); test :app_test (1 srcs, unittest)
  created lib/BUILD.lirk: library :lib (2 srcs)
  deps   //app:app: //lib:lib
  deps   //app:app_test: :app
lirk: drafted 2 BUILD.lirk file(s), 3 target(s); 0 need a hand fix
lirk: next: review the files, declare runtime-read files as `data`, then `lirk test //...`
```

For each directory containing Python files, `init` writes a
`BUILD.lirk` with:

- one `library` target for the ordinary `.py` files, and
- one `test` target for `test_*.py` and `*_test.py`, using pytest if
  the tests are written in pytest style.

It then adds every dependency by reading your imports. Nothing about
the dependency graph is guessed. It also creates `.lirk-root` if you
don't have one.

`init` is safe to run again. It never touches a directory that already
has a `BUILD.lirk`, so after adding a package, just rerun it. It skips
hidden directories, `node_modules/`, virtualenvs (recognised by their
`pyvenv.cfg`, whatever they're called) and `build/` and `dist/`, and it
says when it skips one of the last three, in case that was your code.
It also points out subdirectories that hold no Python, which are often
test data to declare. Use `lirk init --dry-run` to see what it would
write first.

## 2. Review what it couldn't know

**Files your code reads at runtime.** Fixtures, templates, golden
output and config files are invisible to an import scan. Declare them
as `data` on the targets that read them, or edits to them won't cause
reruns:

```toml
[[target]]
name = "parser_test"
type = "test"
srcs = ["test_parser.py"]
deps = [":parser"]
data = ["testdata"]      # a directory is fine; everything in it counts
```

If you miss one, `lirk verify` will catch it the first time it matters
(see step 4, below).

**`MANUAL` lines.** `init` (and `fix`) refuse to guess in two cases:

- **A file listed in two targets:** depending on either would work,
  so you choose.
- **Packages that import each other:** adding both edges would create
  a cycle. Usually this means some shared code wants to move into a
  third package that both can depend on.

**Sharing a data directory between packages.** Give the directory
its own target, and depend on that target wherever it's read:

```toml
# tests/golden/BUILD.lirk
[[target]]
name = "golden_data"
type = "library"
data = ["data"]
```

Any test that depends on `//tests/golden:golden_data` reruns when a file
in `tests/golden/data/` changes. (A `data` path may also point into
another package directly, like `"../tests/golden/data"`. It may not
point outside the repo.)

**Target boundaries.** One library per directory is a starting point,
not a rule. A target is the unit of caching: a 20-file library is
rechecked whenever any of its 20 files changes, so split large ones if
that matters to you.

## 3. Run it

```sh
lirk test //...
```

The first run does everything. After that, only what changed.

## 4. Check the result

Keep running your old test command alongside lirk for a while, and
check that the two agree. Then run:

```sh
lirk verify
```

`verify` reruns every cached result from scratch and fails loudly if a
cached pass turns out to be wrong. That happens when a target reads a
file nobody declared. Running `lirk verify --sample 5` now and then is
a cheap ongoing check.

---

## The rules that matter

### Imports and `deps` must agree

lirk runs your tests with **the repo root on `PYTHONPATH`** and the
package's own directory as the working directory. Both import styles
work:

```python
from greeting.greet import greet    # from the repo root (recommended)
from greet import greet             # a sibling in the same package
```

Because the whole repo is importable, an import of another package
works even if `deps` doesn't mention it. That is a problem for caching:
lirk would not know to rerun your tests when that package changes. So
lirk checks every import against `deps` and fails the build when they
disagree:

```
  FAIL   //cli:cli: render.py imports 'orrery.camera' (//orrery:orrery), not in deps
```

`lirk fix` adds missing deps for you, with comments and formatting
left intact. A dependency of a dependency counts, so you never need to
list everything you reach indirectly. Imports of the standard library
and installed packages are ignored.

The same goes for importing one of your own files that no target lists:

```
  FAIL   //leaf:orphan_user: orphan_user.py imports 'orphan.thing' -- no target declares orphan/thing.py
```

Add the file to some target's `srcs` and depend on that target. The
usual culprit is an `__init__.py`.

### Don't name a module after its own package

A file `greeting/greeting.py` hides the package `greeting` from tests
in that same directory:

```
ModuleNotFoundError: No module named 'greeting.greeting'; 'greeting' is not a package
```

Rename the file. It's a Python import rule, not something lirk can
change.

### Using pytest

Add `runner = "pytest"` to a test target, or let `init` do it. pytest
must be installed for the same Python that runs lirk. Fixtures,
`conftest.py` and assertion rewriting all work as usual. lirk runs
pytest with your repo root as its root directory, so a repo-level
`conftest.py` is always loaded.

Your `conftest.py` files and pytest config (`pytest.ini`,
`pyproject.toml`, `tox.ini`, `setup.cfg`) count as inputs: edit one and
the affected tests rerun. A conftest's imports need `deps` like any
other file's.

### Testing your entry point

lirk has no "run my app" command. Instead, cover your entry point with
a test that runs it, so a broken `main()` can't hide behind passing
library tests:

```python
# cli/test_main.py
import subprocess, sys, unittest

class EntryPointTest(unittest.TestCase):
    def test_starts_and_prints(self):
        proc = subprocess.run(
            [sys.executable, "-m", "cli.main", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.strip())
```

```toml
[[target]]
name = "main_test"
type = "test"
srcs = ["test_main.py"]
deps = [":main"]          # the entry point's own target
```

The test imports nothing from your app; it *runs* it. lirk still
treats `"-m", "cli.main"` in an argument list (and
`runpy.run_module("cli.main")`) as a dependency on `cli.main`, so the
build fails until that dep is declared, and `lirk fix` adds it for
you. That matters: without the dep, editing your entry point would
leave this test cached and green.

If your test starts the program another way, for example by running a
script by its file path, or your code loads modules by path with
`importlib`, lirk can't see the connection. Add the dep yourself, and
run `lirk verify --mutate` now and then: it finds any dependency like
this that nothing declares.

Check the output as well as the exit code. A program whose `main()` is
never called exits 0 too.

### Directories that aren't yours

Hidden directories are always skipped. To exclude others that contain
`BUILD.lirk` files which aren't your targets, such as vendored code or
test fixtures, list them in `.lirk-root`:

```toml
ignore = ["vendor", "tests/fixtures"]
```
