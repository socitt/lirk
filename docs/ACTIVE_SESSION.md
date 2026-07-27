# Active Session Log

Purpose: running log of what's being attempted right now, updated
before and after every risky/uncertain step, so a mid-session crash
(iSH-AOK has crashed before, wiping uncommitted work) doesn't lose
context about what state things were left in.

Convention: newest entry at the top. Each entry says what was about
to be attempted, and once done, what actually happened.

---

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
