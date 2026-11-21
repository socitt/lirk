# lirk

[![CI](https://github.com/socitt/lirk/actions/workflows/ci.yml/badge.svg)](https://github.com/socitt/lirk/actions/workflows/ci.yml)

**A small build and test tool for Python monorepos.** It reruns only
what your change affected, and it's built so that a green result is
never a stale one.

```sh
pip install lirk
cd your-repo
lirk init          # draft BUILD files from your code's real imports
lirk test //...    # run everything; next time, only what changed
```

**[Documentation →](https://socitt.github.io/lirk/)**

## Why lirk

- **Only reruns what changed.** Targets are fingerprinted by content.
  Edit one module and only the tests that depend on it run again.
- **Green means green.** Imports are checked against declared deps, so
  the dependency graph can't silently drift. Your Python version,
  installed packages and pytest config are part of every fingerprint.
  `lirk verify` audits cached results against fresh runs.
- **Minutes to adopt.** `lirk init` writes your BUILD files, and
  `lirk fix` keeps their deps correct as the code changes.
- **Your tests, unchanged.** Plain `unittest` or `pytest`, with output
  passed through exactly as your runner printed it.
- **Runs anywhere Python 3.11 does.** No dependencies, no daemon, no
  JVM. Tested on Linux and macOS, and built to run on an iPhone under
  iSH.

## What it looks like

One `BUILD.lirk` per package directory, in plain TOML:

```toml
[[target]]
name = "physics"
type = "library"
srcs = ["gravity.py", "integrators.py"]
deps = ["//vecmath:vecmath"]

[[target]]
name = "physics_test"
type = "test"
runner = "pytest"
srcs = ["test_gravity.py", "test_integrators.py"]
deps = [":physics"]
```

```
$ lirk test //...
  cached  //vecmath:vecmath
  built  //physics:physics
  PASS   //physics:physics_test (3.1s)
  cached  //render:render_test
lirk: 2/2 tests passed
lirk: OK
```

## Commands

| | |
|---|---|
| `lirk test <label>...` | Run tests, and check what they depend on |
| `lirk build <label>...` | Check targets without running tests |
| `lirk init` | Draft BUILD files for an existing repo |
| `lirk fix` | Add missing deps from your imports |
| `lirk verify` | Recheck cached results against fresh runs |
| `lirk clean` | Delete the cache |

Labels: `//...` (everything), `//app/...` (a directory and below),
`//app:all` (one directory), `//app:app_test` (one target).

## Documentation

- [Getting started](https://socitt.github.io/lirk/getting-started.html):
  a new repo in five minutes
- [Existing repos](https://socitt.github.io/lirk/adopting.html):
  `lirk init` and what to review
- [BUILD files](https://socitt.github.io/lirk/build-format.html) and
  [Commands](https://socitt.github.io/lirk/commands.html): reference
- [How it works](https://socitt.github.io/lirk/how-it-works.html):
  why a cached result can be trusted
- [Troubleshooting](https://socitt.github.io/lirk/troubleshooting.html)

## Background

lirk was written after a Bazel-style build tool kept failing
intermittently on iSH (a Linux environment for iPhone), in a way traced
to how it managed processes. So lirk does the opposite: each test file
is one plain, direct subprocess, run one at a time, with no daemon,
sandbox or process groups. It has since been used across several real
repos, including itself, without that class of failure. The original
write-up lives in [`docs/archive/`](docs/archive/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
