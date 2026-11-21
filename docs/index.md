---
layout: default
title: Overview
---

# lirk

A small build and test tool for Python monorepos. It reruns only what
your change affected, and it is built so that a green result is never
a stale one.
{: .lead}

```sh
pip install lirk
cd your-repo
lirk init          # draft BUILD files from your code's real imports
lirk test //...    # run everything; next time, only what changed
```

<div class="cards">
  <div class="card"><strong>Only reruns what changed</strong>
  <p>Every target is fingerprinted by content. Edit one file and only
  the tests that depend on it run again.</p></div>
  <div class="card"><strong>Green means green</strong>
  <p>Imports are checked against declared deps, and your Python and
  installed packages are part of the fingerprint. <code>lirk
  verify</code> audits the cache against fresh runs.</p></div>
  <div class="card"><strong>Minutes to adopt</strong>
  <p><code>lirk init</code> writes your BUILD files.
  <code>lirk fix</code> keeps their deps right as code changes.</p></div>
  <div class="card"><strong>Runs anywhere Python does</strong>
  <p>Zero dependencies, standard library only. Tested on Linux and
  macOS, and built to run on an iPhone under iSH.</p></div>
</div>

## What it looks like

Each package directory gets a small `BUILD.lirk` file:

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

and a run shows exactly what happened to each target:

```
$ lirk test //...
  cached  //vecmath:vecmath
  built  //physics:physics
  PASS   //physics:physics_test (3.1s)
  cached  //render:render_test
lirk: 2/2 tests passed
lirk: OK
```

Here `physics` changed, so it and its tests ran. `vecmath` and `render`
didn't, so they were skipped. No configuration made that happen: it
follows from the dependency graph.

## Why not just run pytest?

Running your test runner directly works until the repo grows. Then
you either rerun everything on every change, or you guess which
tests matter and sometimes guess wrong. lirk knows which tests matter
because it knows what depends on what, and it proves the dependency
graph is accurate rather than trusting it:

- **An import you forgot to declare fails the build.** Otherwise
  editing that module would skip tests that use it.
- **Files your tests read at runtime** (fixtures, golden output) are
  declared as `data` and fingerprinted too.
- **Upgrading Python or a package** reruns everything once, because a
  pass on the old versions proves nothing about the new ones.
- **pytest's `conftest.py` and config files** count as inputs.

Your tests themselves don't change. lirk runs them with plain
`unittest` or `pytest` and prints their output untouched.

## Why not Bazel or Pants?

They are excellent at huge, multi-language repos, and they ask a lot
in return: a JVM or a daemon, a new build language, sandboxing and
remote-execution machinery. lirk is for the much more common case of a
Python repo that has outgrown "run all the tests", on any machine that
has Python 3.11. Its BUILD files are plain TOML, it has no daemon, and
it runs each test file with one plain, direct subprocess. That last
point matters: lirk began as a replacement for a build tool whose
process handling kept failing on a phone, and the simple process model
is why it doesn't.

## Where to next

- **[Getting started](getting-started.html)**: a new repo, from zero
  to cached tests in five minutes.
- **[Existing repos](adopting.html)**: `lirk init` and how to review
  what it writes.
- **[BUILD files](build-format.html)** and
  **[Commands](commands.html)**: the reference.
- **[How it works](how-it-works.html)**: what's fingerprinted, and why
  you can trust a cached result.
- **[Troubleshooting](troubleshooting.html)**: every error message,
  and what to do about it.

lirk is at version 1.0, MIT licensed, and developed in the open at
[github.com/socitt/lirk](https://github.com/socitt/lirk).
