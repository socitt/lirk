# TASKS

Actionable items from the architecture review at
`docs/reviews/2026-07-26-architecture-review.md`. Each task cites the
review finding it comes from — read that finding before starting, it
contains the reproduction.

Each task is written to be executable without re-deriving the
reasoning. Do them one at a time, run the full suite after each
(`python3 -m unittest discover -s tests -t .`, expect 56 passing plus
whatever you add, ~35s), and commit separately.

---

## Read this before changing anything

**The process-model constraints are not negotiable.** lirk exists
because Please hit an unresolved SIGHUP bug under iSH-AOK, and lirk
avoids every pattern suspected of causing it. When implementing any
task below, do not introduce:

- a new process group or session (`os.setpgrp`, `start_new_session`,
  `setsid`)
- a pseudo-terminal
- `shell=True`
- a "write results to a file, then read the file back" step
- parallel execution of actions

There must remain exactly **one direct `subprocess.run()` call per test
source file**, with output and exit code read from that same call.
Adding keyword arguments to that call (`stdin=`, `timeout=`) is fine —
that is not a change to the process model. **If a task seems to require
one of the forbidden patterns, stop and report it rather than doing
it.** See review section 5.

---

## HIGH priority

### 1. Add an action-version component to the cache fingerprint

**Why:** the fingerprint has no notion of what lirk *does*, so changing
lirk's validation or execution logic leaves every already-cached target
green forever — a stale cache hit reported as a real pass. This has
already happened silently twice (`3658ff0`, `428c517`). Review: **C1**.

**What to change:**
- In `lirk/cache.py`, add a module-level constant, e.g.
  `ACTION_VERSION = 1`, with a comment saying: *bump this whenever the
  behaviour of `validate_target` or `run_test` changes, so existing
  caches are invalidated.*
- In `compute_fingerprints`, fold it into every target's hash — e.g.
  `h.update(str(ACTION_VERSION).encode())` right after the existing
  `h.update(target.type.encode())`.

**Do this task first.** Several tasks below change what a successful
build/test means, and each of them must bump `ACTION_VERSION` in the
same commit. Without this task in place they would each ship the same
stale-cache bug.

**Acceptance:** a test in `tests/test_cache.py` asserting that
fingerprints computed with two different `ACTION_VERSION` values differ
for the same unchanged repo (patch the constant with
`unittest.mock.patch`). Existing cache tests still pass.

---

### 2. Add a `data` field for non-Python inputs

**Why:** any file a target depends on that isn't Python cannot be
declared — putting it in `srcs` fails with a bogus syntax error, and
leaving it out means edits to it never invalidate the cache, so a
genuinely failing test reports `cached` / `OK` indefinitely.
`adventure-engine` and `world-events-tracker` are both data-driven and
will hit this immediately. Review: **C2** (see Probe J and Probe K for
the exact reproduction).

**What to change:**
- `lirk/targets.py`: add `data: tuple[str, ...]` to the `Target`
  dataclass; parse it in `_parse_target` with the existing
  `_string_list` helper, defaulting to `[]`, exactly like `srcs`.
- `lirk/cache.py`, `compute_fingerprints`: hash `data` files the same
  way `srcs` files are hashed (sorted, name + `_hash_file` digest), in
  a separate loop after the `srcs` loop.
- `lirk/actions.py`, `validate_target`: check that `data` files exist
  (same `is_file()` check as `srcs`) but **do not** `ast.parse()` them.
- `docs/design/target-format.md`: document the field — "files the
  target depends on that are not Python source; fingerprinted so
  changes invalidate the cache, but not syntax-checked."
- Bump `ACTION_VERSION` (task 1).

**Acceptance:** a new fixture repo (e.g.
`tests/fixtures/data_dep_repo/`) with a library that reads a `.txt`
file declared in `data`, and a test target asserting on its contents.
Test: run `lirk test`, edit the `.txt` so the assertion becomes false,
run again, assert the output contains `FAIL` and **not** `cached` for
the test target. That test must fail before the change and pass after.

---

### 3. Turn missing / unreadable source files into clean failures instead of tracebacks

**Why:** `compute_fingerprints` runs before validation and reads every
source file unguarded, so a missing file produces a raw
`FileNotFoundError` traceback and a non-UTF-8 file produces a raw
`UnicodeDecodeError`. The good error message that already exists in
`validate_target` ("missing source file(s): ...") is unreachable from
the CLI. Review: **C3** (Probe A, Probe L).

**What to change:**
- `lirk/cache.py`, `_hash_file`: on `OSError`, raise a new
  `CacheError` (or reuse `lirk.targets.ConfigError`) naming the path
  and the target — do **not** return a placeholder hash, which would
  make a missing file cacheable.
- `lirk/cli.py`, `_execute`: wrap the `compute_fingerprints` call so
  that error is reported as `lirk: <message>` on stderr with a return
  of `(False, summary)` rather than a traceback. Alternatively, and
  preferably if it's straightforward, have `_execute` validate the
  existence of every target's srcs before fingerprinting so the
  existing per-target `FAIL ... missing source file(s)` message from
  `validate_target` is what the user actually sees.
- `lirk/actions.py`, `validate_target`: catch `UnicodeDecodeError` and
  `ValueError` alongside `SyntaxError` on the `read_text()` /
  `ast.parse()` call, reporting e.g. `<src>: not readable as Python
  source: <e>`.

**Acceptance:** a CLI-level test using the existing
`tests/fixtures/missing_src_repo` fixture asserting exit code 1 and
`missing.py` in the output with no traceback (this closes review gap
**T4**). Plus a test for a binary file in `srcs` producing a clean
`FAIL` line.

---

### 4. Skip targets whose dependencies failed, and don't cache their results

**Why:** a failed dependency neither blocks nor invalidates its
dependents. A test sitting on top of a broken library can pass, be
cached, and report `cached` / `1/1 tests passed` forever while the
build is failing. It also produces contradictory output (`lirk: 1/1
tests passed` directly above `lirk: FAILED`). Review: **C4** (Probe F).

**What to change:**
- `lirk/cli.py`, `_execute`: keep a `failed: set[str]` alongside the
  loop. Before acting on `label`, check whether any of
  `graph.edges[label]` is in `failed`. If so: print
  `  SKIP   {label}: dependency {dep} failed`, add `label` to `failed`
  too (so the skip propagates up the chain — the topological order
  guarantees dependencies are processed first, so one level of
  checking is enough as long as skipped targets are also marked), set
  `ok = False`, and `continue` **without writing a cache entry**.
- Add a `skipped` counter to `ExecutionSummary` and include it in the
  `cmd_build` summary line (`N built, M cached, K failed, S skipped`).
  For `cmd_test`, skipped test targets must count toward the
  denominator but not toward `passed`.
- Bump `ACTION_VERSION` is **not** needed here — this changes which
  targets run, not what "success" means for a target that does run.

**Acceptance:** a new fixture with a syntactically broken library and a
test target depending on it that would otherwise pass. Assert the test
target prints `SKIP`, that `.lirk-cache.json` contains no entry for it,
and that a second run also prints `SKIP` (not `cached`). Closes review
gap **T6**.

---

### 5. Regression-test the PYTHONPATH fix (root-relative imports)

**Why:** removing the `env=env` argument from `run_test` — i.e.
reverting `428c517`, the only production bug lirk has ever had —
currently leaves the suite at **56/56 passing**. Every fixture uses a
flat sibling import, so nothing exercises the root-relative import form
the bug was about. `docs/KNOWN_ISSUES.md` names this exact gap as the
reason the bug escaped; the fix shipped but the gap never closed.
Review: **T1**.

**What to change:** add a fixture repo, e.g.
`tests/fixtures/rootimport_repo/`, laid out so the test module uses the
root-relative form:

```
rootimport_repo/
  pkg/
    __init__.py        # empty
    thing.py           # def value(): return 42
    test_thing.py      # from pkg.thing import value   <-- root-relative
    BUILD.lirk         # library :thing, test :thing_test deps [":thing"]
```

The import **must** be `from pkg.thing import value` (or
`from pkg import thing`), not `from thing import value` — the whole
point is that it can only resolve if the repo root is on `PYTHONPATH`.

Add a test in `tests/test_actions.py` (or `test_cli.py`) running that
target and asserting it passes.

**Acceptance:** verify the test is actually load-bearing — temporarily
delete `env=env` from the `subprocess.run` call in
`lirk/actions.py:run_test`, confirm the new test **fails**, then put it
back. Do not commit the deletion.

---

### 6. Add a permanent multi-src fixture and test

**Why:** every fixture target has exactly one `srcs` entry. A mutant
making `run_test` execute only `target.srcs[:1]` — silently ignoring
every source file after the first in a multi-src test target — leaves
the suite at 56/56 passing. `c43a787` verified multi-src behaviour in a
throwaway scratch repo outside this project, leaving no regression
test. This is exactly the shape chess is expected to use. Review:
**T2**.

**What to change:** add a fixture (e.g.
`tests/fixtures/multisrc_repo/`) with:
- a `library` target declaring 3 srcs, one of which has a syntax error
  in a variant used by a validation test (or use two fixtures);
- a `test` target declaring 2 srcs where the **second** one fails.

Add tests asserting: all srcs of a library are syntax-checked (not just
the first), and a failure in the second src of a test target is
reported.

**Acceptance:** applying `target.srcs[:1]` to either loop in
`lirk/actions.py` must make at least one new test fail.

---

### 7. Add an end-to-end incremental-rebuild test

**Why:** `test_cache.py` verifies that *fingerprints* change after an
edit, but nothing verifies the CLI acts on it — no test runs
`lirk test`, edits a transitive dependency's source, runs again, and
asserts the dependent actually re-ran rather than printing `cached`.
That is the invariant every user depends on, and it is only covered one
layer below where it's observable. Review: **T3**.

**What to change:** in `tests/test_cli.py`, using the existing
`sample_repo` fixture (which is a linear `//a:a_lib → //b:b_lib →
//c:c_lib` chain):
1. `_run(["test", "//..."], self.root)` — everything runs.
2. Edit `self.root / "c" / "c.py"`.
3. `_run(["test", "//..."], self.root)` again.
4. Assert `//c:c_test`, `//b:b_test` and `//a:a_test` all show `PASS`
   (re-ran) and **not** `cached  //a:a_test` etc.

Add the mirror case: edit `a/a.py` and assert `//c:c_test` and
`//b:b_test` **are** `cached` while `//a:a_test` re-runs. That pins
both directions — invalidation propagates upward, and unrelated
targets are not needlessly rebuilt.

**Acceptance:** both tests pass; removing the dep-fingerprint folding
in `lirk/cache.py` (`h.update(fingerprints[dep].encode())`) makes the
first one fail.

---

## MEDIUM priority

### 8. Reject unknown keys in `[[target]]`

**Why:** a typo'd key is silently ignored. Writing `dpes = [":lib"]`
instead of `deps` produces a target with no dependency edges, which
means the real dependency never enters its fingerprint and changes to
it never invalidate the cache — a permanently stale `cached` result
from one transposed character. The project's own design doc cites
on-screen-keyboard typos as a format-selection criterion. Review:
**C6** (Probe D).

**What to change:** `lirk/targets.py`, `_parse_target`: define
`KNOWN_KEYS = {"name", "type", "srcs", "deps"}` (add `"data"` if task 2
is done first) and raise `ConfigError(f"{where}: unknown key(s): ...")`
for `set(raw) - KNOWN_KEYS`, sorted for a stable message.

**Acceptance:** a test in `tests/test_targets.py` asserting
`ConfigError` mentioning the unknown key. Check no existing fixture
`BUILD.lirk` uses an undeclared key before committing.

---

### 9. Reject a `test` target with no srcs

**Why:** `run_test` loops over zero source files and falls through to
returning success, so a `test` target with `srcs = []` reports `PASS`
and `1/1 tests passed` without spawning a single process or checking a
single assertion — and that false pass is cached. Realistic trigger: a
typo'd key (task 8) or a stale entry after a file rename. Review:
**C5** (Probe B).

**What to change:** `lirk/targets.py`, `_parse_target`: after parsing,
raise `ConfigError(f"{where}: a 'test' target must declare at least one
src")` when `type_ == "test"` and `srcs` is empty.

Optionally also make `run_test` defensive (return a failure rather than
success if it somehow gets an empty `srcs`), since it's a two-line
belt-and-braces guard on a silent-pass path.

**Acceptance:** a test in `tests/test_targets.py`. Note the related
finding recorded in review C5: a test *module* containing zero tests is
already handled correctly on Python 3.12 (`unittest` exits 5), but
would exit 0 on 3.11 — out of scope for this task, mentioned so nobody
re-derives it.

---

### 10. Pass `stdin=subprocess.DEVNULL` to test subprocesses

**Why:** test subprocesses currently inherit lirk's stdin. A test that
reads stdin consumes the user's terminal input, and on an interactive
terminal blocks forever with no timeout and no output. `terminal-projects`
is a repo of interactive terminal games with four `main_test.py`
targets already piping stdin into game entrypoints. Review: **C7**
(Probe E).

**What to change:** `lirk/actions.py`, `run_test`: add
`stdin=subprocess.DEVNULL` to the existing `subprocess.run(...)` call.
That's the whole change — one keyword argument, no process-model
implications. Bump `ACTION_VERSION` (task 1).

**Acceptance:** a fixture test module that reads `sys.stdin.readline()`
and asserts it gets `""` (EOF). Verify manually that
`printf 'x\n' | ./bin/lirk test <target>` no longer lets the child read
`x`.

---

### 11. Add a timeout to test subprocesses

**Why:** a hung test hangs lirk indefinitely. Review: **C8**.

**What to change:** `lirk/actions.py`, `run_test`: add
`timeout=TEST_TIMEOUT_SECONDS` (module constant, default 600 — chosen
so it does not trip the known ~12s `backgammon:main_test`), wrap the
call in `try/except subprocess.TimeoutExpired`, and return
`ActionResult(target.label, False, f"{module} timed out after Ns")`.
Bump `ACTION_VERSION` (task 1).

**Known limitation to document in a comment, not to fix:**
`subprocess.run`'s timeout kills only the direct child, so a
`main_test.py` that has itself spawned `main.py` may leave that
grandchild running. Killing the whole tree needs a process group, which
is forbidden (see the constraints at the top of this file). Accept the
partial cleanup.

**Acceptance:** a fixture test that sleeps, run with a patched-low
timeout constant, asserting a clean `FAIL ... timed out` rather than a
hang.

---

### 12. Save the cache incrementally and atomically

**Why:** `save_cache` is called once, after the whole run, so
interrupting a run discards every result already computed — verified:
SIGTERM 6s into a two-target run left no cache file at all and the
already-passed target re-ran from scratch. `lirk test //...` is ~42s
today and growing, on a device whose crash behaviour is the stated
reason `docs/ACTIVE_SESSION.md` exists. Review: **D1** (Probe P).

**What to change:**
- `lirk/cache.py`, `save_cache`: write to a sibling temp file then
  `os.replace()` it onto the target path, so an interrupted write can
  never leave a truncated cache.
- `lirk/cli.py`, `_execute`: call `save_cache` after each successful
  target rather than only after the loop. Keep the final call too (it's
  harmless and covers the all-cached path).
- **Preserve `load_cache`'s fail-open-to-`{}` behaviour on corrupt
  JSON** (`cache.py:61-65`) — that is deliberate and correct; it fails
  toward rebuilding, never toward a false pass.

**Acceptance:** existing cache tests still pass; add a test that
`save_cache` leaves no temp file behind. A full interruption test is
awkward to automate — manual verification is acceptable, note the
result in `docs/ACTIVE_SESSION.md`.

Small related fix, do it in the same commit: add `flush=True` to the
per-target `print()` calls in `_execute` (`cli.py` lines ~98, ~113,
~123). Python block-buffers stdout when it isn't a tty, so a redirected
run — the exact pattern both assessments' verification batches used —
loses its whole progress log if interrupted.

---

### 13. Skip dot-directories when scanning for BUILD.lirk files

**Why:** `find_build_files` is an unconditional `root.rglob()`. A
`BUILD.lirk` under `.venv/`, `node_modules/`, or a nested checkout —
including a checkout of lirk itself inside the consuming repo — is
picked up and can break an unrelated repo-wide build. Verified: a
vendored `BUILD.lirk` with a missing src crashed `lirk build //...`.
Review: **D2** (Probe O).

**What to change:** `lirk/graph.py`, `find_build_files`: filter out any
path with a component starting with `.` (relative to `root`, so a repo
root that itself lives under a dotted directory still works). Keep the
`sorted()` for deterministic ordering.

**Acceptance:** a test placing a `BUILD.lirk` under a `.hidden/`
subdirectory of a fixture and asserting `build_graph` does not load it.

---

### 14. Run all srcs of a test target, don't stop at the first failure

**Why:** `run_test` returns immediately on the first non-zero exit, so
the remaining source files of a multi-src test target never run. That
was invisible when every target had one src; `c43a787` explicitly
endorsed multi-src as the pattern for chess, so a failing
`test_moves.py` will now silently hide `test_castling.py`. Review:
**D4**.

**What to change:** `lirk/actions.py`, `run_test`: continue the loop
after a failure, collecting failed module names, and return a single
`ActionResult` at the end listing all of them (e.g.
`"2 of 3 src files failed: test_moves, test_castling"`) with the
accumulated stdout/stderr. Still one `subprocess.run` per src file.
Bump `ACTION_VERSION` (task 1).

**Do task 6 first** — it provides the multi-src fixture this needs.

**Acceptance:** a multi-src test target where srcs 1 and 3 fail reports
both, and src 2 is shown to have run.

---

## LOW priority

### 15. Add fixture coverage for multi-dep and diamond dependency shapes

**Why:** `sample_repo` is a linear chain where every target has at most
one dep. So `compute_fingerprints`' sorting of deps (which exists
specifically to make fingerprints independent of declaration order) and
`transitive_closure`'s handling of a dependency reached by two paths
are both untested. Review: **T5**.

**What to change:** add a fixture with a diamond (`d → b`, `d → c`,
both `b` and `c` → `a`). Test that `transitive_closure` returns all
four exactly once, that the topological order is valid, and that
swapping the declaration order of `d`'s two deps in `BUILD.lirk`
produces an identical fingerprint for `d`.

---

### 16. Validate label syntax in `resolve_label`

**Why:** `resolve_label` accepts any string starting with `//`, so a
malformed dep like `//a` (no colon) is reported downstream as
`dependency '//a' does not exist` — loud, but it sends the reader
hunting for a missing target instead of a typo. Review: **D7**.

**What to change:** `lirk/graph.py`, `resolve_label`: after the `//`
branch, require exactly one `:` with a non-empty package-and-name on
either side; raise `GraphError` naming the malformed label otherwise.
Remember `//:name` (root package) is valid — the package part may be
empty, the name part may not.

**Acceptance:** a test asserting the error message says the label is
malformed, not missing. Check the `//:name` form still resolves.

---

### 17. Add a root-package fixture

**Why:** `targets.py` and `graph.py:package_for` both have explicit
handling for a package at the repo root (`""` → `//:name`), and
`test_targets.py` covers the label form at the parser level, but no
fixture repo has a `BUILD.lirk` at its root, so the graph and CLI paths
are unexercised. Review: **T7**.

**What to change:** add a `BUILD.lirk` at the root of a new fixture
repo (not `sample_repo` — changing it would perturb several existing
count assertions such as `lirk: 6 built`) and test that
`lirk build //:name` works.

---

### 18. Add a BUILD.lirk-edit invalidation test

**Why:** editing a `BUILD.lirk` to add a dep or a src correctly
invalidates the affected targets today (the srcs list and resolved dep
labels are both hashed), but nothing protects that behaviour. Review:
**T8**, **D5**.

**What to change:** a test in `tests/test_cli.py` that runs a build,
adds a dep to a fixture copy's `BUILD.lirk`, runs again, and asserts
the affected target re-runs rather than printing `cached`.

---

## Explicitly not tasks

Recorded so a later session doesn't re-open them:

- **Parallel execution, remote caching, sandboxing, `lirk query`.**
  Deferred by both prior assessments on good evidence; this review
  agrees at 20→26 targets. Review section 4, item 5.
- **Mocking `subprocess.run` to speed up the 35s test suite.** It would
  undercut the one thing this tool exists to prove. Review **T9**.
- **`lirk run` / a `binary` target type.** Confirmed off the roadmap in
  `d5a7b25`; the need is fully met by `test` targets that subprocess
  the entrypoint.
- **Adding a summarising or reformatting layer over test output.** Both
  assessments identified the raw passthrough as a practical strength.
  Review section 5.
