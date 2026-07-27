# Target config format

Every package declares its targets in a `BUILD.lirk` file, written in
TOML.

**Tradeoff**: three formats were considered. A Python file (à la
Bazel's Starlark BUILD files) gives the most flexibility — loops,
conditionals, shared helpers — but reading target metadata would mean
either `exec()`-ing arbitrary user code or building a restricted-exec
sandbox, which is exactly the kind of extra process/execution-model
complexity this project exists to avoid, so it was ruled out for v1.
YAML is a familiar, human-friendly choice for this kind of config, but
Python's standard library has no YAML parser — using it would mean
depending on PyYAML, an external package to install on a device where
that's more friction than usual. TOML won because Python 3.11+ ships
a standard-library parser (`tomllib`, read-only, but that's all a
config format needs), its syntax has little of YAML's
whitespace/type ambiguity (relevant when typing on an iOS on-screen
keyboard, where a stray space is easy to miss), and its array-of-tables
syntax (`[[target]]`) maps directly onto "an ordered list of target
declarations."

## Schema

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

- `name` — required, non-empty string, unique within the file.
- `type` — required, one of `"library"` or `"test"` (v1 scope only).
- `srcs` — list of source file paths relative to the package
  directory. Defaults to `[]`.
- `deps` — list of target labels this target depends on. Defaults to
  `[]`. Label resolution (`//path:name` vs `:name`) happens when the
  dependency graph is built across all packages, not at this parsing
  stage.
- `data` — list of file paths relative to the package directory, for
  files the target depends on that are not Python source (e.g. a
  `.txt` fixture read at runtime). Defaults to `[]`. Fingerprinted the
  same way as `srcs` so changes invalidate the cache, but files listed
  here are not syntax-checked — putting a non-Python file in `srcs`
  instead produces a bogus syntax error.

Filename is `BUILD.lirk` rather than `BUILD.toml` to keep it visually
distinctive when grepping/`ls`-ing a package directory, mirroring the
convention (if not the syntax) of Bazel/Please `BUILD` files.
