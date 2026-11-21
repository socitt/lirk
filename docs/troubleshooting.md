---
layout: default
title: Troubleshooting
---

# Troubleshooting

Each entry starts with the message you'll see.

## Setup and labels

**`dependency '//greeting:greeting' does not exist`, but it does.**
You're probably in a subdirectory with no `.lirk-root` above it, so
lirk treated that subdirectory as the whole repo. Check the `lirk: repo
root is ...` line under the error. Create `.lirk-root` at your real
repo root, or pass `--root`.

**`no .lirk-root found in any parent directory; using the current
directory as the repo root`.** A note, not an error. If that directory
is your repo root, `touch .lirk-root` there and the note goes away.

**`malformed label '//app'`.** A label has two parts,
`//package:name`. You probably want `//app:app` (one target),
`//app:all` (that directory) or `//app/...` (that directory and below).

**`invalid label ':app': command-line labels must be absolute`.**
`:name` only works inside `deps`. On the command line, write
`//package:name`.

**`pattern //nope/... matches no targets`.** Usually a typo in the
path.

**`//lib:lib is type 'library', not 'test'`.** `lirk test` runs test
targets. Use `lirk build` for a library, or a pattern like `//lib/...`,
which selects just the tests.

## BUILD files

**`unknown key(s): dpes`.** A typo in a field name. See
[BUILD files](build-format.html) for the valid fields.

**`src 'fixture.txt' is not a .py file`.** Only Python goes in `srcs`.
Move the file to `data`.

**`circular dependency: //a:a -> //b:b -> //a:a`.** Two targets depend
on each other. Break any edge in the cycle, usually by moving the
shared code into a third target that both depend on.

**`duplicate srcs entry: x.py`.** The same file is listed twice.

## Build failures

**`render.py imports 'orrery.camera' (//orrery:orrery), not in deps`.**
Add `//orrery:orrery` to that target's `deps`, or run `lirk fix`. This
check is what keeps cached results honest; see
[How it works](how-it-works.html#imports-are-checked).

**`orphan_user.py imports 'orphan.thing' -- no target declares
orphan/thing.py`.** The imported file isn't in any target. Add it to a
target's `srcs` (often it's an `__init__.py`), then depend on that
target.

**`missing source file(s): greet.py`.** A file listed in `srcs` or
`data` doesn't exist. Only that target fails; others carry on, and
anything depending on it shows `SKIP`.

**`syntax error`** or **`not readable as Python source`.** The file
isn't valid Python, or isn't Python at all.

**`MANUAL ...` from `lirk fix` or `lirk init`.** lirk won't guess: the
imported file belongs to more than one target, or adding the dep would
create a cycle. The message says which. Decide and edit by hand.

## Test failures

**`contained no tests: test_empty`.** That test file defines no tests.
It's treated as a failure because it's almost always a mistake, such as
a renamed class or a lost import.

**`ModuleNotFoundError: No module named 'greeting.greeting';
'greeting' is not a package`.** A module has the same name as its own
directory (`greeting/greeting.py`). Rename the file.

**`timed out after 600s`.** A test file ran past its time limit. Set a
shorter `timeout` on the target so a hang fails sooner, and give any
subprocesses your test starts their own timeouts.

**`pytest is not installed for /usr/bin/python3`.** Install pytest for
that Python (`python3 -m pip install pytest`), the same one that runs
lirk.

**A fixture from `conftest.py` isn't found.** Check that the
`conftest.py` is inside the repo (at or below the directory holding
`.lirk-root`) and on the path between the repo root and the test.
lirk tells pytest the repo root is its root directory, so conftests
outside the repo are never loaded.

## Cache surprises

**`STALE //x:x_test (tests): cached as passing, fails when re-run`**
(from `lirk verify`). The test depends on something lirk doesn't
fingerprint, almost always a file it reads at runtime. Add that file or
its directory to the target's `data`. The stale entry has already been
removed, so the next `lirk test` shows the real result.

**Everything reran and I didn't change anything.** Your Python version
or installed packages changed (a `pip install` counts), or you upgraded
to a lirk release that changes how targets are checked or run. Earlier
passes don't carry over, by design.

**I want a clean slate.** `lirk clean` deletes the cache. To rerun
without deleting it, use `--force`.

## Still stuck?

Open an issue at
[github.com/socitt/lirk/issues](https://github.com/socitt/lirk/issues)
with the command you ran and its full output.
