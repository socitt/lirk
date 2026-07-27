# Active Session Log

Purpose: running log of what's being attempted right now, updated
before and after every risky/uncertain step, so a mid-session crash
(iSH-AOK has crashed before, wiping uncommitted work) doesn't lose
context about what state things were left in.

Convention: newest entry at the top. Each entry says what was about
to be attempted, and once done, what actually happened.

---

## 2026-07-27 (update 7)

- **Committed the architecture review** (`docs/reviews/2026-07-26-architecture-review.md`,
  filed by a separate deep-review session against `611dd23`) and its
  derived `TASKS.md` (18 itemized follow-ups, HIGH/MEDIUM/LOW), both
  as-is with no edits (`fd5a72b`). Starting work through `TASKS.md` in
  order, one task per commit, full suite run after each. Hard
  constraint carried forward from the review: no process
  group/session/pty/`shell=True`/results-file patterns, ever — if a
  task's acceptance criteria seem to need one, stop and flag rather
  than implement. About to start Task 1 (`ACTION_VERSION` folded into
  the cache fingerprint) since several later tasks depend on it.
- **Task 1 done.** `lirk/cache.py`: added `ACTION_VERSION = 1` module
  constant with a comment instructing future bumps whenever
  `validate_target`/`run_test` behaviour changes; folded
  `str(ACTION_VERSION)` into every target's hash in
  `compute_fingerprints`, right after `target.type`. New test
  `test_action_version_change_invalidates_every_target_unchanged` in
  `test_cache.py` patches the constant to two different values via
  `unittest.mock.patch.object` and asserts every target's fingerprint
  differs. Full suite: 57/57 (up from 56), run 3x clean in fresh
  shells (~41-46s each). Every later task that changes what
  build/test success means must bump this constant in the same
  commit — tasks 2, 10, 11, 14 per `TASKS.md`.
- **Task 2 done.** Added a `data: tuple[str, ...]` field to `Target`
  (`lirk/targets.py`), parsed via the existing `_string_list` helper,
  defaulting to `()`. `compute_fingerprints` (`lirk/cache.py`) hashes
  `data` files the same way as `srcs` (sorted, name + content hash),
  in its own loop right after the `srcs` loop; bumped
  `ACTION_VERSION` to 2 in the same commit. `validate_target`
  (`lirk/actions.py`) now checks both `srcs` and `data` files exist
  but only `ast.parse`s `srcs` — a data file failing existence reports
  the same `missing source file(s): ...` message as a missing src.
  Documented the field in `docs/design/target-format.md`. New fixture
  `tests/fixtures/data_dep_repo/` (a library reading `story.txt` via
  `data`, a test target asserting on its contents) plus unit tests in
  `test_targets.py`/`test_actions.py` and the load-bearing CLI test
  `test_editing_a_declared_data_file_invalidates_the_cache` in
  `test_cli.py`. Verified that test is load-bearing: temporarily
  removed the new data-hashing loop from `cache.py`, confirmed the
  test fails (`0 != 1`), restored the loop (this accidentally also
  reverted the `ACTION_VERSION` bump via `git checkout --`, caught and
  reapplied both edits before re-running the suite). Full suite:
  61/61, run 3x clean in fresh shells (~45-49s each).
- **Task 3 done.** Missing/unreadable source files no longer crash
  the CLI with a raw traceback. `lirk/cache.py`: new `CacheError`
  exception; `_hash_file` now catches `OSError` and re-raises it
  naming the target label and path (defense-in-depth for any direct
  caller of `compute_fingerprints`, though the CLI itself never hits
  this path anymore — see below). `lirk/actions.py`: extracted the
  existence check out of `validate_target` into a new
  `missing_files(target, root)` helper (checks both `srcs` and
  `data`) so `cli.py` can reuse the exact same check/message;
  `validate_target`'s `ast.parse`/`read_text()` try block now also
  catches `UnicodeDecodeError`/`ValueError`, reporting `<src>: not
  readable as Python source: <e>` instead of an uncaught exception.
  `lirk/cli.py`: `_execute` now runs the `missing_files` check over
  every target in scope *before* calling `compute_fingerprints`,
  printing a normal `FAIL ... missing source file(s): ...` line per
  affected target and returning early (nothing cached) if any are
  found — this is what actually keeps `compute_fingerprints` from
  ever seeing a missing file in the CLI path; wrapped the
  `compute_fingerprints` call itself in `try/except CacheError` as a
  second line of defense. New fixture `tests/fixtures/binary_src_repo/`
  (a non-UTF-8 `.py` file) alongside the existing `missing_src_repo`.
  New tests: `test_actions.py` (binary file → clean FAIL, not an
  exception), `test_cli.py::MissingOrUnreadableSourceCliTests` (both
  fixtures, asserting exit code 1, the offending filename in the
  output, and no `Traceback`). Verified both CLI tests are
  load-bearing: reverted the `cli.py` preflight (confirmed
  `FileNotFoundError`/`CacheError` propagates as an uncaught
  exception — test errors) and reverted the new `actions.py` except
  clause (confirmed `UnicodeDecodeError` propagates uncaught) via
  `Edit` rather than `git checkout --` this time, having learned from
  task 2 that `git checkout -- <file>` reverts to the last *commit*,
  not just the just-applied test patch, and silently discards
  whatever of the task's real changes hadn't been committed yet (it
  did exactly that to `cli.py` and `cache.py` during task 2's and
  this task's verification steps respectively; both times caught
  immediately via `git diff` and reapplied before moving on — no work
  was lost, but it's a sharp edge worth not hitting a third time).
  Restored both, then full suite: 64/64, run 3x clean in fresh shells
  (~44-46s each).
- **Task 4 done.** `lirk/cli.py`: `_execute`'s main loop now tracks a
  `failed: set[str]`; before acting on a label it checks whether any
  direct dep is already in `failed` (topological order + adding
  skipped labels to `failed` too means one level of checking
  transitively covers the whole subtree) and if so prints `  SKIP
  {label}: dependency {dep} failed`, marks the run failed, and
  `continue`s without touching the cache. A real failure (not just a
  skip) also adds its own label to `failed` now, which is what lets
  the propagation chain start. Added `skipped`/`tests_skipped` to
  `ExecutionSummary`; `tests_total` now includes `tests_skipped` so
  skipped test targets count toward the denominator but never
  `passed`. `cmd_build`'s summary line gained a `, S skipped` suffix
  (existing tests use `assertIn` on a prefix, so unaffected).
  New fixture `tests/fixtures/failed_dep_repo/` mirrors the review's
  Probe F exactly: `//a:broken_lib` has a syntax error, `//a:indep_test`
  depends on it but doesn't import it. New tests in `test_cli.py`
  (`FailedDependencySkipTests`): first run shows FAIL+SKIP and no
  `test://a:indep_test` entry in `.lirk-cache.json`; second run still
  shows SKIP, never `cached`. Verified load-bearing: reverted the
  `failed`-set logic (via `Edit`, not `git checkout` this time),
  confirmed both tests fail and reproduce the review's exact
  contradictory-looking output (`PASS`/`cached` above `lirk: FAILED`),
  restored. Full suite: 66/66, run 3x clean in fresh shells (~44-46s
  each).
- **Task 5 done.** No source change -- pure regression-test gap
  closure (review T1). New fixture `tests/fixtures/rootimport_repo/`
  (`pkg/thing.py`, `pkg/test_thing.py` doing `from pkg.thing import
  value`, the root-relative form every other fixture avoids by using
  flat sibling imports) plus one new test
  `test_passes_for_a_root_relative_import` in `test_actions.py`.
  Verified load-bearing per the task's own acceptance criterion:
  temporarily removed `env=env` from the `subprocess.run` call in
  `lirk/actions.py:run_test` via `Edit` (not `git checkout`, per the
  lesson from tasks 2/3), confirmed the new test fails with
  `ModuleNotFoundError: No module named 'pkg'` -- the exact bug
  `428c517` fixed -- then restored the line and confirmed `git diff
  lirk/actions.py` was empty before re-running the suite. Full suite:
  67/67, run 3x clean in fresh shells (~46-54s each).
- **Task 6 done.** No source change -- pure regression-test gap
  closure (review T2). New fixture `tests/fixtures/multisrc_repo/`:
  a `library` with 3 srcs where the third (`three.py`) has a syntax
  error, and a `test` target with 2 srcs where the second
  (`test_second.py`) fails. Two new tests in `test_actions.py`:
  `test_every_src_of_a_multi_src_library_is_syntax_checked` and
  `test_second_src_of_a_multi_src_test_target_is_run_and_reported`.
  Verified both are load-bearing per the task's acceptance criterion
  (`target.srcs[:1]` on either loop in `lirk/actions.py` must break at
  least one test): applied `[:1]` to the `validate_target` syntax-check
  loop via `Edit`, confirmed the library test fails (`True is not
  false`), restored; then applied `[:1]` to the `run_test` subprocess
  loop, confirmed the test-target test fails the same way, restored;
  confirmed `git diff lirk/actions.py` was empty afterward. Full
  suite: 69/69, run 3x clean in fresh shells (~48-52s each).
- **Task 7 done.** No source change -- pure regression-test gap
  closure (review T3). `test_cache.py` already proved fingerprints
  change after an edit; nothing proved the CLI acted on it. New tests
  in `test_cli.py` (`IncrementalRebuildTests`), using the existing
  linear `//a:a_lib -> //b:b_lib -> //c:c_lib` chain in `sample_repo`:
  edit `c/c.py` (the base dependency) and assert all three test
  targets show `PASS`/re-run, not `cached`; edit `a/a.py` (the leaf,
  nothing depends on it) and assert `//b:b_test`/`//c:c_test` stay
  `cached` while only `//a:a_test` re-runs. First attempt at the edits
  changed each file's `greet()` return value the same way
  `test_cache.py`'s fingerprint-only test does, which broke here
  because these tests actually run the assertions -- `c.py`/`a.py`'s
  own test module asserts on the literal return value, so the edit
  has to perturb the fingerprint (e.g. append a comment) without
  changing behavior. Fixed and verified load-bearing per the task's
  acceptance criterion: removed the `h.update(fingerprints[dep]...)`
  line from `compute_fingerprints` via `Edit`, confirmed both new
  tests fail (dependents wrongly reported `cached`), restored,
  confirmed `git diff lirk/cache.py` was empty. Full suite: 71/71,
  run 3x clean in fresh shells (~70-154s each -- runtime is climbing
  as fixtures accumulate; worth keeping an eye on per review D6).
- **Task 8 done** (first MEDIUM item; all 7 HIGH items now closed).
  `lirk/targets.py`: new `KNOWN_KEYS = {"name", "type", "srcs", "deps",
  "data"}`; `_parse_target` now raises `ConfigError` naming any
  unknown key(s) (sorted, for a stable message) right after the
  table-type check. Checked every existing fixture `BUILD.lirk` first
  (a small script parsing each and diffing its keys against
  `KNOWN_KEYS`) -- none use an undeclared key, so this doesn't break
  anything already committed. New test in `test_targets.py` asserting
  a typo'd `dpes` key raises `ConfigError` mentioning it. This is the
  fix review C6 asked for: a transposed key like `dpes` used to
  silently produce a target with no dependency edges, so the real
  dependency never entered the fingerprint and changes to it never
  invalidated the cache. Full suite: 72/72, run 2x clean in fresh
  shells (~66-67s each) -- two rather than three since this is a
  parse-layer change, not the subprocess/cache-execution axis the
  extra runs are meant to guard.
- **Task 9 done.** `lirk/targets.py`: `_parse_target` now raises
  `ConfigError` when `type == "test"` and `srcs` is empty (a
  `library` with no srcs is still allowed). `lirk/actions.py`:
  `run_test` also got a belt-and-braces guard returning a clean
  failure (`"no srcs to run"`) if it's ever handed an empty-srcs test
  target directly, bypassing the parser. Review C5: `run_test` looping
  over zero srcs fell through to a bare `return ... True, "passed"` --
  zero processes spawned, zero assertions checked, reported and
  cached as a passing test. New tests in `test_targets.py` (empty-srcs
  test rejected, empty-srcs library still allowed) and
  `test_actions.py` (constructing a `Target` directly to exercise
  `run_test`'s defensive path, since the parser now forbids the
  scenario at the source). Found and fixed a collateral hit: the
  pre-existing `test_duplicate_names_raise_config_error` fixture used
  a `type = "test"` target with no `srcs` incidentally (it was testing
  duplicate-name detection, not this rule), so it started raising the
  new error before ever reaching the duplicate check -- added
  `srcs = ["test_dup.py"]` to that fixture's second target. Checked no
  other fixture `BUILD.lirk` has a test target with empty srcs. Full
  suite: 75/75, run 2x clean in fresh shells (~66-68s each; parse-layer
  change).
- **Task 10 done.** `lirk/actions.py`: `run_test`'s `subprocess.run`
  call gained `stdin=subprocess.DEVNULL` -- the only change; bumped
  `ACTION_VERSION` to 3 in `lirk/cache.py`. Review C7: test
  subprocesses previously inherited lirk's own stdin, so a test
  reading stdin on an interactive terminal would block forever
  consuming the user's keystrokes, with no output since stdout is
  still buffered (ties into C8/task 11). New fixture
  `tests/fixtures/stdin_repo/` (`test_stdin.py` asserts
  `sys.stdin.readline() == ""`) plus a unit test in `test_actions.py`.
  Did the manual verification the task calls for: piped `printf
  'x\n'` into a real `lirk test` invocation against a scratch copy of
  the fixture -- confirmed clean `PASS` (EOF, not `x`) with the fix in
  place. Verified load-bearing by temporarily removing
  `stdin=subprocess.DEVNULL` via `Edit`: the same manual invocation
  then showed the child actually reading `x` from the parent's stdin
  and failing its assertion (`AssertionError: 'x\n' != ''`) -- the
  exact failure mode from review Probe E. Restored, confirmed `git
  diff` showed only the intended two-line change. Full suite: 76/76,
  run 3x clean in fresh shells (~67-71s each).
- **Task 11 done.** `lirk/actions.py`: new `TEST_TIMEOUT_SECONDS = 600`
  module constant (600 chosen so it doesn't trip on the ~12s
  `backgammon:main_test`, per the review); `run_test`'s
  `subprocess.run` call now passes `timeout=TEST_TIMEOUT_SECONDS` and
  is wrapped in `try/except subprocess.TimeoutExpired`, returning a
  clean `"{module} timed out after {N}s"` failure (with whatever
  partial stdout/stderr the exception captured) instead of hanging.
  Documented the known limitation as a comment rather than fixing it,
  per the task and the review: `subprocess.run`'s timeout only kills
  the direct child, so a `main_test.py` that spawned its own `main.py`
  grandchild could leave it running -- killing the whole tree needs a
  process group, which this project's process model forbids, so the
  partial cleanup is accepted rather than reaching for
  `start_new_session`. Bumped `ACTION_VERSION` to 4. New fixture
  `tests/fixtures/hang_repo/` (a test that sleeps 5s) plus a test in
  `test_actions.py` patching `TEST_TIMEOUT_SECONDS` down to 0.5s via
  `unittest.mock.patch.object` so the suite doesn't actually wait 600s
  (or even 5s) to prove the timeout fires. Verified load-bearing:
  removed the `try/except`+`timeout=` via `Edit`, confirmed the test
  fails (`True is not false` -- it just waited out the 5s sleep and
  reported PASS), restored, confirmed the diff matched intent. Full
  suite: 77/77, run 3x clean in fresh shells (~68-70s each).
- **Task 12 done.** `lirk/cache.py`: `save_cache` now writes to a
  sibling `.tmp` file and `os.replace()`s it onto the real path, so an
  interrupted write can never leave a truncated cache (review D1).
  `lirk/cli.py`: `_execute` now calls `save_cache` after every
  individually successful target, not only once at the end of the
  whole loop (the final call is kept too -- harmless, and it's what
  covers the all-cached-nothing-changed path). Added `flush=True` to
  every per-target `print()` in `_execute` (the preflight FAIL line,
  SKIP, cached, the verb line, and the stdout/stderr passthrough) so a
  redirected run (`lirk test //... > log.txt`, the exact pattern both
  prior assessments' verification batches used) doesn't lose its whole
  progress log to Python's block-buffering on interruption.
  `load_cache`'s fail-open-to-`{}` behavior on corrupt JSON was left
  untouched, as instructed. New test in `test_cache.py`
  (`test_save_leaves_no_temp_file_behind`). Did the manual
  interruption test the task calls for (automating a real SIGTERM
  mid-run is awkward): built a two-target scratch repo (`a:fast_test`
  completes in under a second, `b:slow_test` sleeps 20s), ran `lirk
  test //...` in the background redirected to a log file, sent
  SIGTERM ~8s in (after `fast_test` had finished but while
  `slow_test` was still sleeping), and confirmed: the log already
  contained `PASS //a:fast_test` (flush worked), `.lirk-cache.json`
  existed with exactly that one entry (incremental save worked,
  unlike the review's Probe P where interrupting left *no* cache file
  and discarded the completed result), no leftover `.tmp` file, and a
  follow-up run showed `cached //a:fast_test` / re-ran `//b:slow_test`
  correctly rather than redoing everything from scratch. Full suite:
  78/78, run 3x clean in fresh shells (~70-75s each).
- **Task 13 done.** `lirk/graph.py`: `find_build_files` now filters
  out any `BUILD.lirk` whose path, relative to `root`, has a
  dot-prefixed directory component (checked relative to root, so root
  itself living under a dotted ancestor is unaffected). Review D2/Probe
  O: an unconditional `root.rglob()` picked up a vendored `BUILD.lirk`
  under e.g. `.venv/`, and its missing source file crashed the entire
  repo-wide build via C3 -- a nested checkout of lirk itself would hit
  the same thing. New test in `test_graph.py`
  (`FindBuildFilesTests`): copies `sample_repo`, adds a
  `.hidden/vendored/BUILD.lirk` declaring a target with a missing src,
  asserts `build_graph` only sees the original six targets. Verified
  load-bearing: reverted to the unconditional `rglob` via `Edit`,
  confirmed the test fails (`//.hidden/vendored:vendored` leaks into
  the graph), restored, confirmed the diff matched intent. Full suite:
  79/79, run 2x clean in fresh shells (~70-76s each; graph-scan
  change, not the subprocess/cache axis, so two runs rather than
  three).
- **Task 14 done** (all MEDIUM items now closed; only LOW remains).
  `lirk/actions.py`: `run_test`'s loop no longer returns immediately
  on the first non-zero exit -- it now collects failed module names
  in `failed_modules` and keeps running every remaining src, returning
  a single `ActionResult` at the end (`"N of M src files failed:
  mod1, mod2"`) only if `failed_modules` is non-empty, still one
  `subprocess.run` per src file. Bumped `ACTION_VERSION` to 5. Review
  D4: stopping at the first failure was invisible while every fixture
  had one src, but `c43a787` explicitly endorsed multi-src as the
  pattern for chess, so a failing `test_moves.py` would silently hide
  `test_castling.py` entirely. Extended `multisrc_repo`'s `multi_test`
  target (from task 6) with a third src, `test_third.py` (also
  fails), so the fixture actually exercises "an earlier failure
  doesn't hide a later one" rather than just "the second of two src
  files is reported," which the old stop-at-first-failure code already
  handled correctly. New test
  `test_all_srcs_run_even_after_an_earlier_one_fails` asserts both
  `test_second` and `test_third` appear in the message. Verified
  load-bearing: reverted to the old return-immediately behavior via
  `Edit`, confirmed the test fails (`test_third` never ran, message
  was just `test_second failed (exit 1)`), restored, confirmed the
  diff matched intent. Task 6's existing mutation test still passes
  unchanged since it only checks `result.ok` and `"test_second" in
  message`, both still true with three srcs. Full suite: 80/80, run
  3x clean in fresh shells (~80-83s each).
- **Task 15 done** (first LOW item; all HIGH/MEDIUM now closed). No
  source change -- pure test-coverage gap closure (review T5). New
  fixture `tests/fixtures/diamond_repo/` (`d -> b`, `d -> c`, both `b`
  and `c` -> `a`, all in one package). `sample_repo`'s linear chain
  never gave a target more than one dep, so two things were untested:
  `compute_fingerprints` sorting a target's deps specifically so
  declaration order doesn't matter, and `transitive_closure` visiting
  a shared dependency (`a`) via two distinct paths without erroring
  or double-counting. New tests: `test_graph.py`
  (`test_diamond_dependency_produces_a_valid_order`,
  `test_diamond_shared_dependency_reached_via_two_paths_is_deduplicated`)
  and `test_cache.py` (`DiamondFingerprintTests`, which edits a
  scratch copy's `BUILD.lirk` to swap `d_lib`'s declared dep order and
  asserts an identical fingerprint). Verified the fingerprint test is
  load-bearing: removed the `sorted()` around `graph.edges[label]` in
  `compute_fingerprints` via `Edit`, confirmed the test fails (two
  different hashes), restored, confirmed `git diff lirk/cache.py` was
  empty. Full suite: 83/83, run 3x clean in fresh shells (~77-82s
  each).
- **Task 16 done.** `lirk/graph.py`: `resolve_label` now validates
  the fully-qualified label shape after the `//`/`:` branch --
  requires exactly one `:` separating package from name, and the name
  part must be non-empty (the package part may be, for the root
  package form `//:name`). Review D7/Probe N: a malformed dep like
  `//a` (no colon) previously fell through to a downstream `dependency
  '//a' does not exist` error, sending a reader hunting for a missing
  target instead of a typo. New tests in `test_graph.py`
  (`ResolveLabelTests`): no-colon, two-colon, and empty-name forms all
  raise `GraphError` mentioning "malformed"; `//:name` and a normal
  relative `:sibling` still resolve correctly. Checked no existing
  fixture `BUILD.lirk` declares a malformed label (none do). Verified
  load-bearing: reverted to the old two-branch version via `Edit`,
  confirmed all three new malformed-label tests fail (`GraphError not
  raised`), restored, confirmed the diff matched intent. Full suite:
  88/88, run 2x clean in fresh shells (~61-62s each).
- **Task 17 done.** No source change -- pure test-coverage gap
  closure (review T7). New fixture `tests/fixtures/root_package_repo/`
  with a `BUILD.lirk` directly at the repo root (deliberately a new
  fixture rather than adding one to `sample_repo`, which nearly every
  other CLI test depends on and whose count assertions like `lirk: 6
  built` would otherwise break). New tests: `test_graph.py`
  (`build_graph` resolves the bare `//:root_lib` label form, package
  is `""`) and `test_cli.py` (`lirk build //:root_lib` works
  end-to-end). Full suite: 90/90, run 2x clean in fresh shells
  (~60-61s each).

## 2026-07-27 (update 6)

- **Closed out the follow-up assessment.** Per the user: archive as a
  dated record rather than fold into `KNOWN_ISSUES.md` (that file is
  for unresolved problems; this assessment closed clean with no
  outstanding bugs). Moved the untracked
  `docs/LIRK_ASSESSMENT.md` to `docs/assessments/2026-07-27-post-go-assessment.md`
  (dated to match its own header and today, not the suggested
  "2026-07-26" which would have collided with the existing
  `2026-07-26-assessment.md` — flagged and confirmed with the user
  before naming it), adding a `## Resolution (2026-07-27)` section
  mirroring the convention already established by the prior archive:
  what happened to each of the 5 suggestions and the bugs section,
  with commit hashes. `docs/assessments/` already existed as a
  directory (holding the one prior archive) so this continues that
  convention rather than inventing a new one.
  Verified the merge is lossless: the appended body is byte-identical
  to the original file's content past the header/note section (`diff`
  confirmed, only difference was a blank-line join artifact, no
  content lost).
  This closes out the entire assessment hand-off: no bugs
  outstanding, both real feature requests shipped
  (multi-file-targets verification + summary line), the `--force`
  doc-sync item explicitly left to `terminal-projects`' own docs (not
  `lirk`'s problem), `lirk run` confirmed off any roadmap, and the
  remaining "not urgent yet" bundle (parallelism/remote
  caching/sandboxing/`lirk query`) reaffirmed deferred. Nothing left
  open from this assessment.

## 2026-07-27 (update 5)

- Item 3 (drop `lirk run` from the roadmap) checked — **nothing to
  remove**. Searched `README.md`, `docs/KNOWN_ISSUES.md`,
  `docs/design/`, and `lirk/*.py` (no `run` subcommand stub exists in
  `cli.py`'s argparse setup) for any live tracking of `lirk run` as a
  planned feature: none found. The only two places it's mentioned are
  `docs/assessments/2026-07-26-assessment.md` (archived as a
  permanent record — editing it would misrepresent what was actually
  suggested/decided on 2026-07-26) and this file's own
  `2026-07-27 (update 2)` log entry recapping that assessment's
  deferred items (a log of a past decision, correct as of when it was
  written). Neither is a live roadmap; both are historical records
  left untouched. Conclusion: the follow-up assessment's suggestion to
  "take it off the roadmap" is already satisfied — it was never on one
  to begin with, only ever proposed and then deferred/reconsidered
  within assessment documents.

## 2026-07-27 (update 4)

- Item 2 (pass/fail summary line) done. `lirk/cli.py`: `_execute` now
  returns an `ExecutionSummary` (built/cached/failed counts, plus
  test-specific passed/failed/cached counts limited to `type ==
  "test"` targets) alongside the existing bool. `cmd_build` prints
  `lirk: N built, M cached, K failed`; `cmd_test` prints `lirk: P/T
  tests passed` (T counts only test-type targets in scope, so a test
  target's library deps don't inflate the denominator; a cached test
  counts as passed since only successful runs are ever cached). Both
  print before the existing `lirk: OK`/`FAILED` line, which is
  unchanged.
  New tests: build summary counts on a fresh run / cached rerun / a
  failure; test summary on a single fresh test, all-fresh `//...`,
  a cached rerun (still counts as passed), and the pre-existing
  failing-test-repo case (confirms a library dep failure doesn't
  inflate the test denominator). One pre-existing test
  (`test_force_bypasses_cache_without_deleting_it`) had to be
  tightened from `assertNotIn("cached", out)` to `assertNotIn("
  cached  ", out)` since the new build summary's `0 cached` text
  otherwise collides with a substring check that was really about the
  per-target line, not the word.
  Full suite (56/56, up from 51) run 3x clean; manual end-to-end
  checks against `tests/fixtures/sample_repo` confirm fresh/cached
  `build` and fresh `test` output all match. Also found and removed a
  stray `.lirk-cache.json` left in `tests/fixtures/sample_repo` from
  earlier item-1 manual comparisons — gitignored, never staged, but
  was making a couple of `test_cli.py` tests fail spuriously
  (`assertIn("PASS", ...)` seeing `cached` instead) until cleaned up.

## 2026-07-27 (update 3)

- **Follow-up assessment** (`docs/LIRK_ASSESSMENT.md`, second dogfooding
  pass, 20 targets across backgammon/go/tictactoe/connect4): no new
  bugs found. Agreed priority order: (1) verify multi-file
  `library`/`test` targets before building `srcs` glob syntax, (2) add
  a one-line pass/fail summary to `lirk test //...`/`lirk build //...`,
  (3) drop `lirk run` from the roadmap. Skipping the doc-sync item
  (not lirk's problem, per the assessment itself).
- Item 1 (multi-file target verification) done — **no code change
  needed**. Built a chess-shaped scratch repo (outside this repo, in
  the session scratchpad) exercising both patterns the assessment
  called out: (a) one `library` target with 3 `srcs`
  (`pieces.py`/`board.py`/`moves.py`, sibling flat imports) plus one
  `test` target with 2 `srcs`; (b) 3 single-file library targets
  chained via `deps` (`moves_lib` depending on *two* other targets:
  `:board_lib` and `:pieces_lib`), each with its own single-file test
  target, plus a cross-package dep (`//utils:helpers`, root-relative
  import, mirroring the `shared/term.py` convention) to also exercise
  multiple deps across packages. `lirk build //...` and
  `lirk test //...` both passed cleanly and consistently: 1 full-repo
  run + 3 isolated per-package runs + 9 more full-repo runs (10
  attempted, 9 completed inside the batch's time budget, 0 failures,
  0 incorrect results) + a cache-hit rerun (`cached` on every target
  the second time, `test //... ` immediately after a clean run). Two
  runs briefly looked like hangs against a 15s per-run timeout;
  isolated timing showed ~11s real wall-clock for the *pre-existing*
  `tests/fixtures/sample_repo` fixture too under this session's
  current environment load, so it's the already-documented
  environment-level subprocess-spawn slowness (see `KNOWN_ISSUES.md`
  / the assessment's own CPU-time note), not a lirk defect. Verdict:
  both multi-file patterns chess is likely to want already work with
  zero new `lirk` code — the assessment's suggestion to hold off on
  `srcs` glob syntax until this was checked is confirmed correct.

## 2026-07-27 (update 2)

- **Status**: Picked up `docs/LIRK_ASSESSMENT.md` (untracked hand-off
  from a dogfooding session in `terminal-projects`, 4 real targets, 60
  fresh-shell test invocations, zero lirk-side bugs found). Summarized
  its findings and agreed a priority order with the user: no bugs to
  fix, so working through suggestions ranked by value/effort — (1)
  `--force`/`--rebuild` flag, (2) `.gitignore` docs, (3) `library`
  syntax validation, (4) `--root` + upward repo-root discovery, defer
  the rest (`lirk run`, `srcs` glob, `lirk query`, parallelism, remote
  caching, sandboxing — all explicitly "not urgent yet" per the
  assessment itself).
- Item 1 done: `--force`/`--rebuild` (build) and `--force`/`--rerun`
  (test) flags added to `lirk/cli.py`, threaded through `cmd_build`/
  `cmd_test`/`_execute` as a `force` bool that skips the `needs_build`
  cache check without touching the cache file. Two new tests
  (`test_force_bypasses_cache_without_deleting_it`,
  `test_force_reruns_unchanged_test_without_deleting_cache`). Full
  suite: 44/44 passing (42 prior + 2 new). Manually verified end-to-end
  against `sample_repo` in a scratch dir: first run builds, second run
  shows `cached`, forced third run rebuilds everything and the cache
  file still exists afterward.
- Item 2 done: added a "Using lirk in a repo" section to `README.md`
  documenting the recommended `.gitignore` entries
  (`.lirk-cache.json`, `__pycache__/`, `*.pyc`) for repos that consume
  lirk — mirrors what lirk's own `.gitignore` already has. Doc-only,
  no test to run.
- Item 3 done: `validate_target` (`lirk/actions.py`) now `ast.parse()`s
  every declared `srcs` file after confirming it exists, so a broken
  `main.py`-style file reports `FAIL: syntax error` on `lirk build`
  instead of silently reporting `built`. New fixture
  `tests/fixtures/syntax_error_repo` (one library target, one file
  with a deliberate syntax error) backs a unit test on
  `validate_target` directly and a CLI-level test on `lirk build`.
  Full suite: 46/46 passing (44 prior + 2 new).
- Item 4 done: added an explicit `--root <path>` flag to both `build`
  and `test` (`lirk/cli.py`), and `_discover_root()`, which walks
  upward from `cwd` for a `.lirk-root` marker file and falls back to
  `cwd` unchanged if none is found anywhere above it — so repos that
  haven't adopted the marker keep today's exact behavior; this only
  changes anything for repos that opt in by dropping an empty
  `.lirk-root` file at their top level. Precedence: explicit `root=`
  kwarg (test harness) > `--root` flag > marker discovery > cwd
  fallback. New tests: `DiscoverRootTests` (unit tests on
  `_discover_root` directly, no chdir) and
  `RootDiscoveryEndToEndTests` (real `os.chdir` into a fixture
  subdirectory, verifying `lirk build` from `//a` correctly resolves
  a marker at the repo root and sees `//b:b_lib`; `os.chdir` restored
  via `addCleanup`). Full suite: 51/51 passing (46 prior + 5 new).
  Manually reproduced the assessment's described failure mode
  end-to-end: running from a subdirectory *without* the marker fails
  with `dependency '//b:b_lib' does not exist` (silent wrong-scope,
  exactly as described); *with* the marker present, the same command
  resolves correctly. README documents the marker and `--root` flag.
- All four planned items from `docs/LIRK_ASSESSMENT.md` are now done.
  Decided to archive rather than fold into `KNOWN_ISSUES.md`: the
  assessment's only "bug" wasn't a `lirk` bug at all, and the rest is
  a broad usage report (evidence + suggestions), not the
  found/root-caused/fixed shape `KNOWN_ISSUES.md`'s convention
  expects. Moved to `docs/assessments/2026-07-26-assessment.md`,
  added a "Resolution" section at the top recording what happened to
  each item (done + commit hash, or deferred + reason, matching the
  assessment's own effort/value ranking).
- This session's work on the assessment is complete: 4 commits
  (`9b2e03f`, `f519fd8`, `3658ff0`, `fac0d0c`), each tested and pushed
  individually, plus this archival commit. Stopping here.

## 2026-07-27

- **Status**: Picked up an uncommitted `FINDINGS.md` left by another
  session's dogfooding run against `terminal-projects`' `shared/`
  package. It reported `lirk test` failing 0/10 on a root-relative
  import (`from shared import term`) with `ModuleNotFoundError`, fully
  root-caused (`run_test` set `cwd=pkg_dir` with no `PYTHONPATH`, so
  the package itself was never importable) but not yet fixed.
  Confirmed this was a real lirk bug, not a clean pass, so it did not
  get folded into `terminal-projects` as a dogfooding success —
  documented in this repo's new `docs/KNOWN_ISSUES.md` instead.
  User approved attempting the smallest of the three sketched fixes:
  inject `PYTHONPATH=<repo root>` into the test subprocess's `env`
  (keeping `cwd=pkg_dir` unchanged). Applied it, then verified with
  two separate 10-run batches against `terminal-projects`'
  `shared:term_test` in fresh shells — 10/10 passing, and 10/10 again
  with `.lirk-cache.json` deleted before every run to force a real
  subprocess execution each time (not a cached result). Full existing
  suite still 42/42 passing. Fix confirmed, documented as "found and
  fixed" in `docs/KNOWN_ISSUES.md`, `FINDINGS.md` deleted (content
  folded into `KNOWN_ISSUES.md`).
- Stopping here per the plan — no further new work this session.

## 2026-07-26 (update 6)

- **Status**: Step 6 done — CLI implemented and manually verified.
  `lirk/actions.py`: `validate_target` (checks srcs exist — v1's
  whole "build" step, no compilation needed) and `run_test` (one
  `subprocess.run([sys.executable, "-m", "unittest", module], cwd=...,
  capture_output=True, text=True)` call per test src file — no shell,
  no new process group/session, no pty, no separate results-file
  step; output/exit code read straight off that call).
  `lirk/graph.py` gained `transitive_closure` so `build`/`test` on a
  single label only touch that target's dependency subgraph.
  `lirk/cli.py`: `build`/`test` subcommands, `//path:name` or `//...`.
  `bin/lirk` added as a short executable shim (`./bin/lirk build ...`
  instead of `python3 -m lirk build ...`) since every keystroke counts
  on the iOS on-screen keyboard.
  **Bug caught during manual end-to-end testing (not by the unit
  suite)**: running `lirk build //...` then `lirk test //...` reported
  every test target as already "cached" — build's file-existence
  validation of a test target wrote the same fingerprint key that
  test's pass/fail cache used, so a build could silently mean a test
  never actually ran. Fixed by namespacing cache keys per command
  (`build:label` vs `test:label`); added a regression test
  (`test_build_does_not_satisfy_a_later_test_run`) and re-verified
  manually. 42 tests passing.
- Steps 1-6 all complete, committed, and pushed. Stopping here per
  the plan — no dogfooding against terminal-projects until told to
  proceed.

## 2026-07-26 (update 5)

- **Status**: Step 5 done. `lirk/cache.py` computes a per-target
  fingerprint (own name/type, source file contents, transitive dep
  fingerprints) and a `.lirk-cache.json` load/save round-trip
  (already gitignored). Added real source files (a.py/b.py/c.py +
  their tests) to the sample_repo fixture so hashing has real content
  to work on — these will double as fixtures for step 6's actual
  subprocess-based test execution. 10 new tests, 25 total, all
  passing.
- Next: step 6, CLI `build`/`test` commands wired to subprocess.run()
  per the no-process-group/no-pty/no-results-file constraints.

## 2026-07-26 (update 4)

- **Status**: Step 4 done. `lirk/graph.py` scans a repo tree for
  BUILD.lirk files, resolves `//pkg:name` and `:name` deps into
  qualified labels, builds a Graph (targets + edges), and does a
  DFS-based topological sort with cycle detection (reports the full
  cycle path). Fixtures added under tests/fixtures/: sample_repo
  (linear a->b->c chain, each with a lib + a test depending on its
  sibling lib), cycle_repo (x<->y cycle), missing_dep_repo, and
  self_dep_repo. 6 new tests, 15 total, all passing.
- Next: step 5, content-hash-based incremental build cache
  (.lirk-cache.json).

## 2026-07-26 (update 3)

- **Status**: Git push auth resolved (user configured credentials
  outside this chat). Pushed the two queued commits successfully.
  Step 3 done: chose TOML for BUILD.lirk (docs/design/target-format.md
  has the tradeoff), implemented `lirk/targets.py` (Target dataclass +
  parse_build_file), 9 passing unittest cases in
  tests/test_targets.py. All committed and pushed.
- Next: step 4, dependency graph + topological sort across all
  packages in a repo, with fake fixture targets.

## 2026-07-26 (update 2)

- **Status**: Step 1 (this file) committed locally as `aad26aa`, but
  `git push` failed — no git credentials configured in this
  environment (no credential helper, no `gh`, no SSH key). Asked
  user how to handle auth; user chose to configure credentials
  themselves outside this chat (declined pasting a PAT into the
  conversation, which was the right call — reasonable to avoid
  putting long-lived secrets in a transcript). `github-cli` (2.83.0)
  is available via `apk` if a device-code login is wanted later.
  **Commits are accumulating locally and are NOT yet on the remote.**
  Proceeding with local commits per the plan; push everything once
  auth is sorted.
- Next: README (step 2), then target-config format (step 3).

## 2026-07-26

- **Status**: Session start. Repo initialized with LICENSE only.
- **Plan for this session** (see user request for full spec):
  1. This file (docs/ACTIVE_SESSION.md) — in progress.
  2. Root README explaining what lirk is and why.
  3. Propose target-config format (BUILD.lirk vs TOML vs YAML),
     implement parser.
  4. Dependency graph + topological sort, with fake test fixtures.
  5. Content-hash-based incremental build skipping.
  6. CLI `build`/`test` commands.
  7. Stop and report back — no dogfooding against terminal-projects
     until explicitly told to proceed.
- **Environment check done**: Python 3.12.13 available, stdlib
  `tomllib` present (read-only TOML parser), `yaml` module NOT
  installed. This informs the format decision in step 3.
- Next: write this file, commit, push, then start README.
