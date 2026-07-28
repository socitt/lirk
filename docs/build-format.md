---
layout: default
title: BUILD.lirk format
---

# BUILD.lirk format

Every package declares its targets in a `BUILD.lirk` file, written in
TOML.

```toml
[[target]]
name = "mylib"
type = "library"       # "library" or "test"
srcs = ["mylib.py"]
deps = ["//other/pkg:othertarget", ":sibling_in_same_pkg"]

[[target]]
name = "mylib_test"
type = "test"
srcs = ["test_mylib.py"]
deps = [":mylib"]
```

- **`name`** — required, non-empty string, unique within the file.
- **`type`** — required, one of `"library"` or `"test"` (v1 scope
  only).
- **`srcs`** — list of source file paths relative to the package
  directory. Defaults to `[]`.
- **`deps`** — list of target labels this target depends on. Defaults
  to `[]`. Label resolution (`//path:name` vs `:name`) happens when
  the dependency graph is built across all packages, not at parse
  time.
- **`data`** — list of file paths relative to the package directory,
  for files the target depends on that are not Python source (e.g. a
  `.txt` fixture read at runtime). Defaults to `[]`. Fingerprinted the
  same way as `srcs` so changes invalidate the cache, but files listed
  here are not syntax-checked — putting a non-Python file in `srcs`
  instead produces a bogus syntax error.

Unknown keys in a `[[target]]` table are rejected, and a `test`
target with no `srcs` is rejected — both fail at parse time rather
than silently doing nothing.

Filename is `BUILD.lirk` rather than `BUILD.toml` to keep it visually
distinctive when grepping/`ls`-ing a package directory, mirroring the
convention (if not the syntax) of Bazel/Please `BUILD` files.

## Why TOML

Three formats were considered. A Python file (à la Bazel's Starlark
BUILD files) gives the most flexibility — loops, conditionals, shared
helpers — but reading target metadata would mean either `exec()`-ing
arbitrary user code or building a restricted-exec sandbox, exactly the
kind of extra process/execution-model complexity this project exists
to avoid, so it was ruled out for v1. YAML is a familiar,
human-friendly choice for this kind of config, but Python's standard
library has no YAML parser — using it would mean depending on PyYAML,
an external package to install on a device where that's more friction
than usual. TOML won because Python 3.11+ ships a standard-library
parser (`tomllib`, read-only, but that's all a config format needs),
its syntax has little of YAML's whitespace/type ambiguity (relevant
when typing on an iOS on-screen keyboard, where a stray space is easy
to miss), and its array-of-tables syntax (`[[target]]`) maps directly
onto "an ordered list of target declarations."

## Repo setup

A repo with `BUILD.lirk` files should gitignore the artifacts lirk
generates alongside your source:

```
.lirk-cache.json
__pycache__/
*.pyc
```

lirk needs to know your repo root to scope its target search and
resolve `//`-prefixed labels. By default it uses the current
directory, walking upward for a `.lirk-root` marker file first — drop
an empty `.lirk-root` at your repo's top level and `lirk build`/`lirk
test` will find it correctly even when run from a subdirectory.
Without the marker, lirk silently scopes to whatever directory it was
invoked from, which can make targets outside that subtree look
"missing" rather than out of scope. `--root <path>` overrides
discovery entirely.
