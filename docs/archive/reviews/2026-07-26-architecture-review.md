# lirk architecture review (2026-07-27)

Filed at `docs/reviews/2026-07-26-architecture-review.md` because that
path was specified explicitly in the review request; the work was
actually done on 2026-07-27. Noting the discrepancy here rather than
silently renaming the file, since the two existing files in
`docs/assessments/` are dated by content and a mismatch would otherwise
be confusing later.

Scope: architecture and design review of `lirk` at commit `611dd23`, at
the request of the repo owner. Review and task-planning only — **no
source code was modified**. Every claim below was verified empirically
against throwaway repos in a session scratchpad, or against a *copy* of
this repo (for mutation testing); the working tree was clean before and
after.

Baseline: `python3 -m unittest discover -s tests -t .` → **56 tests, 35s,
OK**.

This review assumes the two prior dogfooding assessments
(`docs/assessments/2026-07-26-assessment.md`,
`docs/assessments/2026-07-27-post-go-assessment.md`) as background and
does not repeat their findings. Those were written from the *consumer*
side (does lirk work when I use it); this one is written from the
*implementation* side (where is it wrong, and what breaks next).

Headline: the process model — the entire reason this project exists —
is sound and should not be touched. The problems are all in the
**cache/fingerprint layer**, and they share one root cause: the
fingerprint describes what lirk *reads*, but nothing about what lirk
*does* or about inputs lirk can't express. That produces exactly the
failure mode the review request prioritized — a stale cache hit
reported as a real pass.

---

## Reproduction key

Findings cite probes by letter. Each was a fresh throwaway repo under
the session scratchpad, driven by `python3 /root/git/lirk/bin/lirk ...
--root .`. They are described inline so they can be re-run.

---

## 1. Correctness risks

### C1 — The fingerprint has no notion of lirk's own behaviour, so upgrading lirk leaves stale green results *(HIGH — silent wrong pass)*

`cache.py:compute_fingerprints` hashes exactly four things: the
target's `name`, its `type`, the name+SHA256 of each `srcs` file, and
the label+fingerprint of each dependency. It contains nothing about
what a "successful build" or "successful test" *means* in this version
of lirk.

So when the definition of success changes, every previously-cached
target keeps its green result forever.

This is not hypothetical — it has already happened twice in this
repo's short history:

- `3658ff0` added `ast.parse()` validation to `validate_target`.
  Targets already cached as `built` under the old (existence-only)
  rule were never re-validated.
- `428c517` changed the test subprocess environment (PYTHONPATH). Any
  test cached as passing before that change would not have re-run
  after it.

**Probe G.** A library target with a syntactically broken `broken.py`.
I computed its fingerprint using lirk's own `compute_fingerprints` and
wrote a single `build://a:lib` entry — byte-for-byte what pre-`3658ff0`
lirk would have written, since the fingerprint inputs are unchanged
between those versions. Then ran current lirk:

```
  cached  //a:lib
lirk: 0 built, 1 cached, 0 failed
lirk: OK
```

A file that current lirk *fails* on reports `OK` because an older lirk
had blessed it. Nothing in the tool can detect this.

Fix direction: a module-level `ACTION_VERSION` constant folded into
every fingerprint (or stored as a header in `.lirk-cache.json` and
compared on load, discarding the cache on mismatch). Bump it in the
same commit as any change to what `validate_target` / `run_test`
actually do. One line of hashing, permanent protection.

### C2 — Non-Python inputs cannot be declared, so edits to them never invalidate anything *(HIGH — silent wrong pass; directly blocks the roadmap)*

`validate_target` (`actions.py:41-48`) `ast.parse()`s **every** entry in
`srcs`. There is no other input field — no `data`, no `resources`.

That leaves two options for a target that reads a data file, and both
are wrong:

**Option A — declare it in `srcs`.** *(Probe J)* A one-line
`story.txt` containing `You are in a maze of twisty passages.`:

```
  FAIL   //a:lib: story.txt: syntax error: invalid syntax (story.txt, line 1)
```

**Option B — leave it out of `srcs`.** *(Probe K)* An `engine.py` that
reads `story.txt`, and a test asserting on its contents:

```
# run 1 — passes, gets cached
  PASS   //a:story_test
lirk: 1/1 tests passed
lirk: OK

# now edit story.txt so the assertion is genuinely false
  cached  //a:story_test
lirk: 1/1 tests passed
lirk: OK

# same thing with --force, i.e. what is actually true
FAILED (failures=1)
lirk: 0/1 tests passed
lirk: FAILED
```

That middle block is the exact failure this review was asked to hunt
for: a broken repo reporting a clean pass, indefinitely, with no
warning.

This is not a corner case for the roadmap ahead. `adventure-engine`
and `world-events-tracker` are data-driven by name; the first story
file or event fixture written will land on this.

Fix direction (smallest sufficient change): add a `data` field to the
target schema, hashed into the fingerprint by `compute_fingerprints`
but never `ast.parse`d by `validate_target`. Alternatively, restrict
`ast.parse` to files ending in `.py` and fingerprint all of `srcs` —
smaller diff, but conflates "source" and "data" in a way that will
want undoing later.

### C3 — A missing (or non-UTF-8) source file crashes with a raw traceback, and the intended error message is unreachable *(HIGH — crash where a clean failure exists)*

`cli.py:87` calls `compute_fingerprints` for **every** target in scope
*before* the validation loop at `cli.py:91` runs. `cache.py:22`
`_hash_file` does an unguarded `path.read_bytes()`.

**Probe A.** A target declaring `srcs = ["nope.py"]`:

```
  File "/root/git/lirk/lirk/cache.py", line 45, in compute_fingerprints
    h.update(_hash_file(src_path).encode())
  File "/root/git/lirk/lirk/cache.py", line 22, in _hash_file
    return hashlib.sha256(path.read_bytes()).hexdigest()
FileNotFoundError: [Errno 2] No such file or directory: 'a/nope.py'
```

Meanwhile `actions.py:35-39` contains a perfectly good
`missing source file(s): nope.py` failure — **it can never be reached
from the CLI**. It is only reachable by calling `validate_target`
directly, which is exactly what `test_actions.py:19` does, which is why
this was never noticed. There is no CLI-level test using
`missing_src_repo` (see T4).

Same shape, second path: **Probe L**, a binary file in `srcs` →
`validate_target`'s `src_path.read_text()` raises an uncaught
`UnicodeDecodeError` (a `ValueError`, not the `SyntaxError` the `except`
clause catches).

Fix direction: guard `_hash_file` and `validate_target`'s read, and
convert both to target-level failures. Note the ordering constraint —
because fingerprinting runs first, the guard in `cache.py` is the one
that decides whether the user sees a traceback.

### C4 — A failed dependency neither blocks nor invalidates its dependents, and the dependent's green result is cached *(HIGH)*

`cli.py:_execute` walks `order` and treats every target independently.
Nothing records that a dependency failed.

**Probe F.** `//a:broken_lib` has a syntax error. `//a:indep_test`
depends on it but doesn't import it (a lazy import, a partial refactor,
or an entrypoint not yet wired up — all realistic):

```
# run 1
  FAIL   //a:broken_lib: broken.py: syntax error: invalid syntax
  PASS   //a:indep_test
lirk: 1/1 tests passed
lirk: FAILED

# run 2
  FAIL   //a:broken_lib: broken.py: syntax error: invalid syntax
  cached  //a:indep_test
lirk: 1/1 tests passed
lirk: FAILED
```

Two problems. First, the green result of a target sitting on top of a
broken dependency is written to the cache and trusted from then on
(`.lirk-cache.json` afterwards contains only `test://a:indep_test`).
Second, the summary lines directly contradict each other:
`lirk: 1/1 tests passed` immediately above `lirk: FAILED`. The exit
code is right (1), so this doesn't escape CI-style checking, but a
human skimming a phone terminal reads the passed line.

Bazel and Please both mark dependents of a failed target as skipped.
lirk should too.

Fix direction: `_execute` keeps a `failed: set[str]`; before acting on
a label, check whether any of `graph.edges[label]` is in `failed` (the
topological order guarantees deps were processed first, so a single
level of checking transitively covers the whole subtree if skipped
targets are also added to `failed`). Print `  SKIP   <label>: dependency
<dep> failed`, do not cache, do not count as passed.

### C5 — A `test` target with no `srcs` reports PASS without executing anything *(MEDIUM-HIGH — silent wrong pass)*

`actions.py:run_test` loops over `target.srcs`; with an empty list the
loop body never runs and control falls through to
`return ActionResult(target.label, True, "passed", ...)`.

**Probe B.** `name = "empty_test"`, `type = "test"`, `srcs = []`:

```
  PASS   //a:empty_test
lirk: 1/1 tests passed
lirk: OK
```

Zero processes spawned, zero assertions checked, reported as a passing
test and cached as one. The realistic trigger is a typo'd key (C6:
writing `src = [...]` silently yields `srcs = []`) or a file rename
that leaves the BUILD entry stale.

Worth recording what is *not* broken here: a test module that exists
but contains no tests is handled correctly on this Python.
**Probe C** — `python3 -m unittest` exits 5 (`NO TESTS RAN`) on
Python 3.12, so lirk reports `FAIL ... (exit 5)`. That exit code was
only introduced in 3.12; on 3.11 (which `tomllib` also supports, so
it's a plausible runtime) the same case exits 0 and would report a
false PASS. Worth a guard, but it's a smaller problem than the
empty-`srcs` case, which spawns nothing at all on any version.

Fix direction: reject `type = "test"` with empty `srcs` in
`targets.py:_parse_target` as a `ConfigError`. It is never a valid
declaration.

### C6 — Unknown keys in `[[target]]` are silently ignored, which silently drops dependency edges *(MEDIUM-HIGH — silent wrong result)*

`targets.py:_parse_target` reads `name`, `type`, `srcs`, `deps` and
ignores everything else.

**Probe D.** A target declaring `dpes = [":something"]` and
`bogus_key = 42`:

```
  built  //a:typo_lib
lirk: 1 built, 0 cached, 0 failed
lirk: OK
```

The interesting consequence is not the missing error message — it's
downstream. A target whose `deps` were silently dropped has no
dependency edges, so `compute_fingerprints` (`cache.py:47`) folds
nothing from the real dependency into its fingerprint. **Changes to the
dependency will never invalidate it**, and it reports `cached` forever.
A single transposed character converts a correct incremental build into
a permanently stale one.

This repo's own design doc explains that TOML was chosen partly because
"a stray space is easy to miss" when "typing on an iOS on-screen
keyboard" (`docs/design/target-format.md`). That reasoning applies with
equal force to a transposed key name, and the format's strictness is
currently not being used.

Fix direction: in `_parse_target`, compare `set(raw) - KNOWN_KEYS` and
raise `ConfigError` naming the unknown key. Five lines.

### C7 — Test subprocesses inherit lirk's stdin *(MEDIUM)*

`actions.py:74-80` calls `subprocess.run` with `capture_output=True`
but no `stdin=`, so the child inherits the parent's stdin.

**Probe E.** A test that does `sys.stdin.readline()`, with lirk invoked
as `printf 'secret-from-parent-terminal\n' | lirk test ...`:

```
AssertionError: 'secret-from-parent-terminal' != 'NOT-WHAT-THE-PARENT-SENT'
 : child read: 'secret-from-parent-terminal\n'
```

The child read straight from lirk's own stdin. On an interactive
terminal — the actual deployment target — a test that reads stdin
blocks forever waiting for the user, with no timeout (C8) and no output
(the run is still buffering). It also consumes keystrokes intended for
the shell.

`terminal-projects` is a repo of *interactive terminal games* with four
`main_test.py` targets that already pipe stdin into game entrypoints.
The distance between "a test that pipes input" and "a test that
accidentally reads the real stdin" is one refactor.

Fix direction: `stdin=subprocess.DEVNULL`. A stdin-reading test then
gets a clean `EOFError` and fails fast instead of hanging — verified as
the behaviour when stdin is closed (Probe E2:
`FAILED (errors=1)` / `lirk: FAILED`).

**This does not violate any process-model constraint**: it is one more
keyword argument to the same single `subprocess.run` call. No process
group, no session, no pty, no shell, no results file.

### C8 — No timeout on test subprocesses *(MEDIUM)*

Same call site. A hung test hangs lirk indefinitely.

Fix direction: an optional `timeout=` with a generous default (600s
would not have tripped on the ~12s `backgammon:main_test`), reported as
a target failure via `subprocess.TimeoutExpired`.

State the limitation honestly when implementing: `subprocess.run`'s
timeout kills only the direct child. A `main_test.py` that has itself
spawned `main.py` would leave that grandchild running. Killing the
whole tree requires a process group, which this project explicitly
forbids — so accept the partial cleanup rather than reaching for
`start_new_session`. A partially-cleaned timeout is still far better
than an unbounded hang.

---

## 2. Design debt

### D1 — The cache is written once, at the end of the run *(MEDIUM)*

`cli.py:128` — `save_cache` is called after the loop completes. Every
result computed before an interruption is discarded.

**Probe P.** A two-target `lirk test //...` (one fast, one 20s), SIGTERM
at t+6s:

```
--- cache file after interrupt ---
ls: .lirk-cache.json: No such file or directory
--- rerun //a:fast_test: was its PASS remembered? ---
  PASS   //a:fast_test
```

The already-completed target re-ran from scratch.

This is in direct tension with the project's own stated posture.
`docs/ACTIVE_SESSION.md` opens by explaining that the whole logging
convention exists because "iSH-AOK has crashed before, wiping
uncommitted work." A `lirk test //...` run is now ~42s and growing;
chess adds roughly 4-6 targets. Losing the whole run's results to a
crash or a Ctrl-C is the same category of problem the doc discipline
was built to avoid.

Two related observations from the same probe:

- Nothing was written *at all*, not even a partial file — so today's
  behaviour is at least safe, just wasteful. Any fix must preserve
  that: write to a temp file and `os.replace()` it, so a crash
  mid-write cannot leave a truncated cache. (`load_cache` already fails
  open on corrupt JSON, so even that would be recoverable — but atomic
  replace makes it a non-question.)
- The progress lines printed before the interrupt were also lost:
  Python block-buffers stdout when it isn't a tty, so a redirected run
  (`lirk test //... > log.txt`, exactly the pattern the verification
  batches in both assessments used) loses its log on interruption.
  `print(..., flush=True)` at `cli.py:98/113/123` fixes it.

### D2 — The repo scan is unconditional and unbounded *(MEDIUM)*

`graph.py:25` — `find_build_files` is `sorted(root.rglob(BUILD_FILENAME))`
with no exclusions.

**Probe O.** A `BUILD.lirk` placed under `.venv/lib/pkg/` was picked up
by `lirk build //...` and its missing source file crashed the entire
repo-wide build (via C3). Any vendored dependency, hidden directory, or
nested checkout — including a checkout of lirk itself inside the
consuming repo — can break an unrelated build.

The `.lirk-root` marker (`fac0d0c`) fixed the *upward* scoping problem
well. The *downward* scoping problem is untouched.

Fix direction: skip directories starting with `.` by default, and
optionally honour an ignore list. Low risk, and it also speeds up the
scan on a device where filesystem traversal is not free.

### D3 — `Path(src).stem` as the module name couples test execution to flat package layouts *(MEDIUM)*

`actions.py:73-79` derives the module name from the file stem and runs
`python3 -m unittest <stem>` with `cwd=pkg_dir`.

**Probe I.** A src in a package *subdirectory* (`sub/helper.py`,
`sub/test_helper.py`):

```
# library target — fine
  built  //a:subdir_lib

# test target — fails
ERROR: test_helper (unittest.loader._FailedTest.test_helper)
ModuleNotFoundError: No module named 'test_helper'
```

The failure is loud, which is the important thing. But the asymmetry is
surprising: the same path is valid in a `library` target and broken in
a `test` target, with an error message that says nothing about why.
A second consequence: two srcs with the same stem in different
subdirectories collide silently on the same module name.

This is the piece most likely to strain if chess organises into
subdirectories rather than flat files.

### D4 — `run_test` stops at the first failing src *(MEDIUM)*

`actions.py:83-90` returns immediately on a non-zero exit, so the
remaining src files in a multi-src test target never run.

That was invisible while every target had exactly one src. It stops
being invisible now: `c43a787` explicitly endorsed multi-src targets as
the pattern for chess. A failing `test_moves.py` will hide
`test_castling.py` entirely, and the summary line will say
`0/1 tests passed` regardless of how many files were actually skipped.

Fix direction: run all srcs, accumulate failures, report which files
failed. Preserves the process model exactly (still one
`subprocess.run` per file).

### D5 — No expression of non-source inputs *(covered by C2)*

Worth recording what *is* correct here, so it doesn't get reworked: a
target's own BUILD declaration is already partially fingerprinted —
`name`, `type`, the `srcs` list (filenames, not just contents), and the
resolved dep labels all feed the hash (`cache.py:38-49`). So adding,
removing, or renaming a src or a dep *does* correctly invalidate.
Comments and formatting in `BUILD.lirk` correctly do not. That part of
the design is right; the gap is purely the missing input *category*.

### D6 — Serial execution, no parallelism, no `lirk query` — correctly deferred *(LOW)*

Both prior assessments deferred these and both were right. Nothing in
this review changes that at 20→26 targets.

One forward-looking note for whoever revisits it: the pressure will
not come from target count. It will come from `main_test`-style targets
that pipe a whole game through a subprocess — `backgammon:main_test`
alone is ~9-12s of the ~42s whole-repo run. If chess adds a comparable
one, the whole-repo test heads toward a minute. Still not a reason to
build a scheduler; just the number to watch.

### D7 — Weak label validation *(LOW)*

`graph.py:45` `resolve_label` accepts anything starting with `//`.
**Probe N**: a dep of `"//a"` (no colon) is reported as
`dependency '//a' does not exist` — loud, but it sends the reader
looking for a missing target instead of a malformed label.

### D8 — Concurrent invocations clobber the cache *(LOW)*

`load_cache` / `save_cache` are an unlocked read-modify-write
(`cache.py:56-69`). Two overlapping lirk runs lose one run's entries.
The failure mode is a redundant rebuild, not a wrong result, and the
single-device workflow makes overlap unlikely. Noted for completeness;
not worth fixing now.

---

## 3. Test coverage gaps

Method: I copied the repo to a scratchpad, applied one small mutation
at a time, and ran the full suite. The repo itself was never modified.
Baseline 56/56 in 35s.

### What is genuinely well covered (mutants killed)

This is not a formality — these are the invariants that matter most,
and they hold up:

| Mutation | Result |
|---|---|
| `compute_fingerprints` no longer folds in `fingerprints[dep]` (dependents stop invalidating) | **killed** — 1 failure |
| `topological_sort` returns `order[::-1]` (dependents before deps) | **killed** — 1 failure, 20 errors |
| `compute_fingerprints` no longer folds in source contents | **killed** — 2 failures |
| `_execute` caches failures as well as successes | **killed** — 3 failures |

Plus the build/test cache-key namespacing has a real, well-commented
regression test at `test_cli.py:106`, guarding a bug that actually
shipped.

### T1 — The only production bug lirk has ever had is not regression-protected *(HIGH)*

Removing the `env=env` argument from `run_test` — i.e. reverting
`428c517`, the PYTHONPATH fix, the single real bug ever found in this
tool — leaves the suite at **56/56 OK**.

The reason is visible in the fixtures: every test module uses a flat
sibling import (`sample_repo/a/test_a.py:3` → `from a import greet`,
resolved by `cwd` being `sys.path[0]`). Nothing exercises the
root-relative `from <package> import <module>` form that the bug was
about.

`docs/KNOWN_ISSUES.md` identified this exact gap as the reason the bug
escaped in the first place ("every fixture ... used a flat import, so
this path was never exercised end-to-end"). The fix shipped; the gap
did not close.

### T2 — Multi-src targets are entirely untested *(HIGH)*

Every fixture target in the repo has exactly one `srcs` entry. A mutant
making `run_test` iterate `target.srcs[:1]` — executing only the first
file of a multi-src test target and silently ignoring the rest — leaves
the suite at **56/56 OK**. The equivalent mutation in `validate_target`
is uncovered by construction, for the same reason.

`c43a787` verified multi-src behaviour thoroughly, but in a scratch
repo outside this project, leaving no permanent artifact. That
verification is exactly the thing chess is expected to rely on, and
nothing currently protects it.

### T3 — No end-to-end incremental-rebuild test *(HIGH)*

`test_cache.py:38`
(`test_editing_a_source_file_changes_its_own_and_dependents`) verifies
that *fingerprints* change after an edit. Nothing verifies that the
*CLI* acts on that: no test runs `lirk test`, edits a transitive
dependency's source, runs again, and asserts the dependent actually
re-executed rather than printing `cached`.

That is the single invariant every user depends on, and it is only
covered one layer below where it's actually observable.

### T4 — `missing_src_repo` has no CLI-level test *(MEDIUM)*

It is used only in `test_actions.py:19` and `test_actions.py:59`, both
calling `validate_target` / `run_test` directly and therefore both
bypassing `compute_fingerprints`. That is precisely why C3 (the
traceback) went unnoticed.

### T5 — No target with more than one dependency, and no diamond *(MEDIUM)*

`sample_repo` is a linear `a → b → c` chain where every target has at
most one dep. Consequences:

- `compute_fingerprints` sorts deps (`cache.py:47`) specifically so
  fingerprints don't depend on declaration order. Untested.
- `transitive_closure` visiting a shared dependency via two paths
  (`graph.py:118-123`, guarded by the `if label in closure` check).
  Untested.

`c43a787`'s scratch repo did exercise a multi-dep target — again
without leaving a regression test behind.

### T6 — No test of a failed dependency's effect on dependents *(MEDIUM)*

`failing_test_repo` covers a failing *test* whose library dep succeeds.
The reverse — a failing *library* with a dependent — is untested, which
is why C4 is unnoticed.

### T7 — No fixture for a root-package target *(LOW)*

`targets.py:31` (`//{package}:{name}` with `package == ""`) and
`graph.py:30` (`package_for` returning `""`) both have explicit
root-package handling. `test_targets.py:63` asserts the `//:bare` label
form at the parser level, but no fixture repo has a `BUILD.lirk` at its
root, so the graph/CLI path is unexercised.

### T8 — No BUILD.lirk-edit invalidation test *(LOW)*

Nothing edits a `BUILD.lirk` between runs (changing `deps`, adding a
src) and asserts the affected targets re-run. D5 notes this behaviour
is correct today; nothing protects it.

### T9 — Suite runtime is 35s, and that's the right tradeoff *(no action)*

The suite spawns real interpreters instead of mocking `subprocess.run`.
The 2026-07-26 assessment already flagged the wall-clock cost and
correctly concluded that mocking would undercut the one thing this tool
exists to prove. Agreed — do not mock it.

The practical implication for the tasks above: where a new fixture is
testing graph/cache logic rather than execution, prefer `library`
targets so it doesn't pay interpreter-startup cost. Only T1 and T2
genuinely need to spawn processes.

---

## 4. What breaks first, given the roadmap

Ranked by likelihood × consequence against the actual remaining plan
(chess in progress; adventure-engine and world-events-tracker ahead).

1. **`adventure-engine` / `world-events-tracker` hit C2 on day one.**
   Both are data-driven by name. The first story file or event fixture
   forces a choice between a bogus syntax error (Probe J) and silent
   permanent staleness (Probe K). The second option is the one people
   pick, because it looks like it works. This is the highest-consequence
   item in the review: it produces a confidently green run over a
   genuinely broken repo, which is the precise failure mode `lirk` was
   built to be trustworthy about.

2. **chess hits D3 / D4 / T2.** Multi-src targets work today, but
   nothing in the suite protects them (T2), a failure in one src hides
   the rest (D4), and organising into subdirectories rather than flat
   files silently changes a working library layout into an unimportable
   test layout (D3). Chess is the most rule-complex target yet —
   check/checkmate, castling, en passant, promotion — and the most
   likely to want that structure.

3. **C7 + C8 combine into an unbounded hang the first time a test
   touches stdin.** There are already four `main_test.py` targets
   piping input into interactive games, with more coming on the same
   template. A test that under-supplies input to a game looping on
   `input()` currently blocks lirk forever, on a phone terminal, with
   no output because stdout is still buffered. This is the most
   *user-hostile* failure available today even though it's less likely
   than #1.

4. **C1 fires on the next change to what an action does.** It has
   already fired silently twice. It will fire again on the next
   validation or execution change — including several of the fixes
   recommended here, which is a good reason to do C1 first.

5. **Explicitly not breaking soon:** parallelism, remote caching,
   sandboxing, `lirk query`. Both prior assessments deferred these on
   good evidence and nothing here contradicts them. Adding any of them
   now would trade the tool's main asset — a process model simple
   enough to reason about on the device where the original bug appeared
   — for a problem nobody has.

---

## 5. Genuinely good — do not touch

Stated plainly so none of this gets reworked by a later session reading
only the findings above.

**The process model, above all.** One direct `subprocess.run` per test
file, output and exit code read from that same call, no shell, no
process group, no session, no pty, no results file
(`actions.py:74-80`). This is the entire reason the project exists, and
across two assessments and 90+ documented fresh-shell invocations it has
not produced a single flaky result — against Please's 0/45 on a
comparable target.

Every recommendation in this review is compatible with it. C7 and C8
are additional keyword arguments to that same single call. **If any
suggested fix ever appears to require a process group, a session, a
pty, or a write-then-read results file, drop the fix, not the
constraint.**

**Cache-key namespacing by mode** (`cli.py:94`, `f"{mode}:{label}"`)
with the regression test at `test_cli.py:106`. This caught a real
silent-pass bug during manual testing, the fix is exactly right, and
the test comment explains *why* rather than *what*. Model for the rest
of the suite.

**Never caching failures** (`cli.py:111`, `if result.ok:`). The correct
asymmetry: a pass may be trusted forward, a failure must always be
retried. Mutation-tested above and well covered by
`test_failing_test_is_retried_even_though_unchanged`.

**Content hashing rather than mtimes** (`cache.py:22`). Immune to
`touch`, to checkouts, to clock skew, and to iSH-AOK's questionable
time accounting (which the 2026-07-27 assessment documented producing
`user 24m40s` for a 42s run). A whole category of stale-build bug
avoided by construction.

**`load_cache` failing open to `{}`** (`cache.py:61-65`). Corrupt or
unparseable cache → rebuild everything. Fails toward doing more work,
never toward a false pass. Exactly the right direction for a build
tool, and worth preserving explicitly through any D1 rework.

**Raw, uninterpreted test output on failure** (`cli.py:124-126`). Both
assessments independently identified this as a practical strength.
Resist adding a summarising or reformatting layer.

**Cycle reporting that names the full path** (`graph.py:98`) — better
than most real build tools manage.

**TOML via stdlib `tomllib`** (`docs/design/target-format.md`). Zero
external dependencies on a device where installing one is real
friction, and no `exec()` of user code — which would have dragged in
exactly the execution-model complexity the project exists to avoid. It
also keeps `targets.py` at 94 readable lines. C6's fix (rejecting
unknown keys) is about *using* that strictness, not changing the
format.

**The `.lirk-root` marker design** (`cli.py:28-40`). Opt-in, falls back
to prior behaviour when absent, explicit `--root` override. The right
resolution of the sharpest edge the first assessment found, chosen over
the "nearest `BUILD.lirk`" heuristic for a stated and correct reason.

**The documentation discipline itself.** `ACTIVE_SESSION.md`,
`KNOWN_ISSUES.md`, and dated `docs/assessments/` made this review
possible without re-deriving a single decision. The convention of
archiving assessments as dated records rather than folding them into
the issues file is right, and this review follows it.

---

## Summary

The dependency graph and the topological sort are correct and
mutation-resistant. The process model is the project's main asset and
should be defended. Every serious problem found is in the
fingerprint/cache layer, and they share a root cause: **the fingerprint
describes what lirk reads, but nothing about what lirk does (C1) or
about inputs lirk cannot express (C2)**. Those two, plus C3 and C4, are
what turn a build failure into a silently green run — and they are all
cheap to fix relative to what they cost when they fire.

The test suite covers its core invariants genuinely well, but has a
blind spot along the whole subprocess-execution axis: reverting the
only production bug this tool has ever had leaves 56/56 green.

Actionable items are itemised in `TASKS.md` at the repo root.
