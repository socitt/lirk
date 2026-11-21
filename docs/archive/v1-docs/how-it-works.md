---
layout: default
title: How it works
---

# How it works

A repo declares targets in `BUILD.lirk` files (TOML), one per package
directory. Each target is a `library` (a set of `.py` srcs other
targets can depend on) or a `test` (srcs run via `python3 -m
unittest`). Deps are expressed as `//package:name` labels (or
`:name` for a same-package sibling), and can cross package
directories freely:

<pre class="mermaid">
graph LR
    a_test["//a:a_test (test)"] --> a_lib["//a:a_lib (library)"]
    a_lib --> b_lib["//b:b_lib (library)"]
    b_lib --> c_lib["//c:c_lib (library)"]
</pre>

`lirk build //...` or `lirk test //pkg:name` then runs this pipeline:

<pre class="mermaid">
flowchart TD
    A["lirk build/test //label"] --> B["find repo root\n(.lirk-root marker, else cwd)"]
    B --> C["scan for BUILD.lirk files,\nparse targets"]
    C --> D["build dependency graph,\ntopological sort"]
    D --> E["narrow to the requested target's\ntransitive closure"]
    E --> F["content-hash fingerprint\neach target (srcs + dep fingerprints)"]
    F --> G{"fingerprint matches\n.lirk-cache.json?"}
    G -- yes --> H["skip: report cached"]
    G -- no --> I["build: validate srcs exist + parse as Python\ntest: subprocess.run() per src\n(one direct call, no pty/process group)"]
    I --> J["write result to\n.lirk-cache.json (atomic)"]
</pre>

Only successful results are cached, so a failure is retried on the
next run even with an unchanged fingerprint.

## The incremental cache

`.lirk-cache.json`, written at the repo root, maps `"<mode>:<label>"`
(`build:` and `test:` never share an entry for the same target — a
`build` validating a test target's files must not count as `lirk
test` having actually run it) to a content fingerprint: a hash of the
target's own name/type, its `srcs`/`data` file contents, and the
fingerprints of its dependencies, recursively. Any change anywhere in
a target's dependency chain propagates forward and invalidates every
dependent target's cached result.

The cache is local, gitignored state — see
[Using lirk in a repo](index.html#quick-start) — not something to
commit or share between machines.

## The subprocess model

Every build/test action runs through exactly one direct
`subprocess.run()` call: no new process group or session, no
pseudo-terminal, no shell, and no "run then read a results file back"
indirection — output and exit code come straight off that same call.
See [Overview](index.html#why-this-exists) for why that constraint
exists in the first place.
