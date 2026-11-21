---
layout: default
title: How it works
---

# How it works

lirk's job is to answer one question for every target: *has anything
it depends on changed since it last passed?* If not, the target is
`cached`, and skipping it is safe. Everything on this page exists to
make that answer trustworthy.

## The dependency graph

Targets name what they use in `deps`, and lirk follows those edges:

<pre class="mermaid">
graph LR
    app_test["//app:app_test"] --> app["//app:app"]
    app --> greeting["//greeting:greeting"]
    greeting_test["//greeting:greeting_test"] --> greeting
</pre>

An edit to `greeting` affects everything that points at it, directly
or indirectly. An edit to `app` affects only `app` and `app_test`.

## Fingerprints

Every target gets a fingerprint: a hash of

- the contents of its `srcs` and `data` files,
- its settings (type, test runner, timeout),
- the fingerprints of everything in its `deps`,
- your Python version and the installed packages, and
- for pytest targets, the `conftest.py` and pytest config files above
  them.

Because each fingerprint includes its dependencies' fingerprints, a
change anywhere flows forward to everything downstream, and nowhere
else.

When a target passes, lirk records its fingerprint in
`.lirk-cache.json`. Next time, if the fingerprint is the same, the
target is `cached` and doesn't run. Some consequences:

- **Contents, not timestamps.** Touching a file, checking out another
  branch and back, or cloning fresh doesn't cause reruns. Reverting an
  edit brings back the cached result.
- **Only passes are recorded.** A failing test always runs again.
- **A changed environment reruns everything once.** After a Python
  upgrade or a `pip install`, earlier passes no longer prove anything,
  so they're discarded.
- **A dependency failing means `SKIP`, never a pass.** A test above a
  broken library doesn't run and doesn't count as passing.

## Imports are checked

A fingerprint only covers what a target declares. If a test imports a
package that isn't in its `deps`, Python still finds it (the whole repo
is importable), but lirk wouldn't know to rerun the test when that
package changes. The cached pass would quietly go stale.

So when lirk checks a target, it reads every import in its source files
(plus any module a test runs with `python -m`) and confirms each one is
covered by `deps`. An import that isn't fails
the build, naming exactly what to add, and `lirk fix` can add it for
you. Imports from the standard library and installed packages are
ignored.

This is the difference between lirk and tools that trust the
dependency graph as written: lirk verifies it on every change.

## Data files

The import check can't see files a test opens at runtime. Those must be
declared in `data` to be fingerprinted. That is the one thing you have
to get right by hand, so lirk gives you a way to check it:
`lirk verify` reruns cached results from scratch, and anything that
fails where the cache said it passed is reported as `STALE`. That
almost always means an undeclared data file.

## Running tests

Each test file runs in its own fresh Python process:

```
python3 -m unittest <module>            # runner = "unittest"
python3 -m pytest <file>                # runner = "pytest"
```

with the package directory as the working directory and the repo root
on `PYTHONPATH`. Standard input is empty, so a test that waits for
input fails immediately instead of hanging. Each file has a time limit
(`timeout`, 600 seconds by default). Output is printed exactly as your
test runner wrote it.

A file that defines no tests counts as a failure, not a pass: it's
almost always a mistake, such as a renamed test class.

## Why so simple?

lirk runs targets one at a time, each test file as one plain
subprocess: no daemon, no process groups, no sandbox, no parallel
workers. That's deliberate. lirk was created after a more complex
build tool kept failing intermittently on iSH, a Linux environment for
iPhone, and the cause was traced to its process handling. A simple,
direct process model is easy to reason about, and has not produced
that kind of failure in any repo lirk has been used on.

The trade-off is speed on very large repos, where parallelism would
help. In practice, skipping everything that hasn't changed matters far
more than running the rest in parallel.

## The full pipeline

<pre class="mermaid">
flowchart TD
    A["lirk test //..."] --> B["find the repo root (.lirk-root)"]
    B --> C["read every BUILD.lirk"]
    C --> D["build the dependency graph"]
    D --> E["select the requested targets\nand everything they depend on"]
    E --> F["fingerprint each target"]
    F --> G{"same as last pass?"}
    G -- yes --> H["cached: skip"]
    G -- no --> I["check files, syntax and imports;\nrun tests"]
    I -- pass --> J["record fingerprint"]
    I -- fail --> K["report; dependents SKIP"]
</pre>

For the full design, including every decision and its reasoning, see
[`docs/dev/DESIGN.md`](https://github.com/socitt/lirk/blob/main/docs/dev/DESIGN.md).
