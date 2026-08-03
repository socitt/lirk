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

  **`deps` is enforced against what the srcs actually import.** If a
  src imports a module belonging to a target outside this one's
  dependency closure, the build fails:

  ```
  FAIL //cli:cli: render.py imports 'orrery.camera' (//orrery:orrery), not in deps
  ```

  This is a correctness check, not style policing. Targets run with the
  repo root importable, so Python resolves a cross-package import
  whether or not you declared it — and an undeclared edge is missing
  from the fingerprint, so editing the imported package invalidates
  nothing and you get a cached PASS against changed inputs. Declaring
  the dep is the fix.

  Checked against the **transitive closure**, so an import satisfied by
  a dep-of-a-dep is fine; the fingerprint covers it either way.
  Imports of the stdlib, of installed packages, and of files under the
  repo root that no target declares as a src are not reported.
- **`data`** — list of paths relative to the package directory, for
  things the target depends on that are not Python source (e.g. a
  `.txt` fixture read at runtime). Defaults to `[]`. Fingerprinted the
  same way as `srcs` so changes invalidate the cache, but entries here
  are not syntax-checked — putting a non-Python file in `srcs` instead
  produces a bogus syntax error.

  An entry may name a **directory**, which is fingerprinted
  recursively: editing, adding, or removing any file beneath it
  invalidates the target. Use this for a fixture tree rather than
  listing files individually — a hand-maintained list goes stale
  silently, and a fixture you forgot to declare gives you a cached
  PASS against inputs that changed. Two kinds of path are skipped
  inside a data directory, because they are generated rather than
  declared: dot-prefixed names, and `__pycache__`. Without that, a
  fixture tree containing Python would accumulate `.pyc` files as a
  side effect of running the very tests whose fingerprint it feeds,
  and nothing would ever stay cached.

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

### Excluding directories from the scan

`.lirk-root` may be empty, or may carry repo-level config as TOML. The
one key it accepts is `ignore`:

```toml
ignore = ["tests/fixtures", "vendor"]
```

Each entry is a directory path relative to the repo root; it and
everything beneath it are excluded from the `BUILD.lirk` scan. Entries
must stay inside the repo — an absolute path or one containing `..` is
rejected rather than quietly clamped. Unknown keys are rejected, as in
`BUILD.lirk`.

Directories whose name starts with `.` are always skipped and need no
entry. `ignore` is for the rest: a vendored dependency, a nested
checkout, or a test-fixture tree whose `BUILD.lirk` files are inputs to
your tests rather than targets of your repo. lirk's own repo is the
motivating case — `tests/fixtures/` holds deliberately broken
`BUILD.lirk` files (cycles, dangling deps) that would otherwise make
the graph fail to load before anything ran.

Note that `ignore` and `data` are independent. `ignore` governs which
`BUILD.lirk` files are *scanned*; `data` governs what gets
*fingerprinted*. A fixture directory is legitimately both — not your
targets, but still your inputs.
