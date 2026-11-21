---
layout: default
title: BUILD files
---

# BUILD files

Each package directory has a `BUILD.lirk` file, written in
[TOML](https://toml.io), that lists its targets. The repo root has a
`.lirk-root` file, which is usually empty.

## A complete example

```toml
# shapes/BUILD.lirk

[[target]]
name = "shapes"
type = "library"
srcs = ["__init__.py", "circle.py", "square.py"]
deps = ["//geometry:geometry"]

[[target]]
name = "shapes_test"
type = "test"
runner = "pytest"
srcs = ["test_circle.py", "test_square.py"]
deps = [":shapes"]
data = ["testdata"]
timeout = 60
```

## Target fields

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | The target's name, unique within the file. Together with the directory it forms the label, e.g. `//shapes:shapes`. |
| `type` | yes | `"library"` (code other targets use) or `"test"` (code lirk runs). |
| `srcs` | for tests | Python files, relative to this directory. Subdirectories are fine (`"sub/helper.py"`). Only `.py` files are allowed. |
| `deps` | no | Labels of targets this one uses. Must cover what the srcs import from elsewhere in the repo; `lirk fix` maintains it for you. |
| `data` | no | Non-Python files the target reads at runtime: fixtures, templates, golden output. A directory counts as everything inside it. |
| `runner` | no | Tests only: `"unittest"` (default) or `"pytest"`. |
| `timeout` | no | Tests only: seconds each test file may run before it's stopped and reported as timed out. Default 600. |

Anything else is an error, so a typo like `dpes` is caught rather than
silently ignored. Repeating an entry within `srcs`, `deps` or `data` is
an error too.

### `srcs`

Every src is parsed as Python, and its imports are checked against
`deps` (see [How it works](how-it-works.html#imports-are-checked)). A
`test` target runs each of its srcs as a separate test module.

### `deps`

Two forms:

| Form | Means |
|---|---|
| `"//pkg/path:name"` | A target in another package, by its path from the repo root. `"//:name"` is a target in the root directory. |
| `":name"` | A target in this same `BUILD.lirk`. |

You only list what a target uses directly: a dependency's own
dependencies come along automatically.

### `data`

Declare anything a target reads that isn't Python. lirk fingerprints
it, so editing a fixture reruns the tests that read it. This matters:
an undeclared fixture can change without lirk noticing, and the test's
old pass stays cached. Prefer naming a directory over listing files,
so new files are covered automatically. Hidden files and `__pycache__`
inside a data directory are ignored.

### `runner`

With `"pytest"`, lirk runs `python3 -m pytest <file>` for each src, with
the repo root as pytest's root directory. Your `conftest.py` files and
pytest config files between the package and the repo root are treated
as inputs automatically, and a conftest's imports need `deps` like any
other file's. pytest must be installed for the Python that runs lirk.

### `timeout`

A positive whole number of seconds. Set it on anything that could hang:
a wedged test otherwise costs the full 600 seconds. Changing it reruns
the target. lirk can only stop the test process itself, so if your test
starts subprocesses of its own, give those their own timeouts.

## `.lirk-root`

Put this file at the top of your repo. lirk finds the repo root by
looking for it in the current directory and its parents, so commands
work from any subdirectory. It's usually empty. It has two optional
settings:

```toml
ignore = ["vendor", "tests/fixtures"]
timeout = 120
```

**`timeout`** is the default time limit, in seconds, for every test
target that doesn't set its own (otherwise 600). Changing it reruns the
tests it applies to.

**`ignore`** lists directories, relative to the repo root, whose
`BUILD.lirk` files (and everything beneath them) lirk should skip. An
entry that matches no directory prints a warning, since it's almost
always a typo. Use it
for vendored code, nested checkouts, or test fixtures that contain
BUILD files of their own. Hidden directories (starting with `.`) are
always skipped.

`ignore` only affects which BUILD files are found. A test can still
read files from an ignored directory, and should declare them in `data`.

## Files to gitignore

```
.lirk-cache.json
.lirk-cache.json.*.tmp
__pycache__/
*.pyc
```

`.lirk-cache.json` is lirk's record of what has passed, kept at the
repo root. It's specific to your machine and Python environment, so
don't commit it.
