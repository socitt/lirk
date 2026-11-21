# lirk tasks

Current backlog. Check items off and edit in place as work happens —
this file reflects present reality, not history. Architecture context
lives in [DESIGN.md](DESIGN.md); do not restate it here.

**Before implementing anything**, read DESIGN.md §1. The process-model
constraints are not negotiable: no process group, no session, no pty,
no `shell=True`, no results-file step, no parallel execution. If a task
seems to require one, stop and report it rather than doing it.

Last verified against source (2026-11-21): 309 tests, `python3 -m
unittest discover -s tests -t .`. lirk also builds and tests itself —
`lirk build //...` (19 targets) and `lirk test //...` (8 test targets)
— which runs alongside the unittest invocation rather than replacing
it. Both must be green.

---

## v1 stability criteria

All three must hold before parallelism work starts or scope expands
beyond Python `library`/`test` targets. Status is honest, not
optimistic — "probably true" counts as not met.

### 1. Self-hosting — ✅ MET (2026-08-02)

lirk builds and tests its own source through its own `BUILD.lirk`
files (`lirk build //...` and `lirk test //...` against this repo), not
only via a separately maintained `unittest` suite.

**Status:** `lirk/BUILD.lirk` and `tests/BUILD.lirk` describe 13
targets whose deps mirror the real import graph. `lirk build //...`
builds 13/13; `lirk test //...` runs the suite through lirk, 5/5 test
targets green (all 112 underlying tests) in ~2m45s.

Decisions made when this landed:

- **`lirk test //...` runs *alongside* `unittest discover`, not instead
  of it.** `unittest discover` stays the source of truth. Self-hosting
  is the proof, not the safety net — a lirk bug that reported false
  green would otherwise have no independent check, and a cache bug
  could mask a real regression indefinitely. Both must be green.
- **Fixture imports were never at risk.** The concern recorded here was
  that `tests/` resolves fixtures by path relative to the repo root; in
  fact all four modules derive `FIXTURES` from `Path(__file__).parent`,
  which is cwd-independent and works unchanged under `cwd=pkg_dir`.
- Longest single module is ~88s against a 600s `TEST_TIMEOUT_SECONDS`,
  so there is ample headroom even with nested subprocesses.

Getting here required three engine changes, all of which surfaced only
by actually attempting it — see Recently closed for L4 (the fixture
scan), the `data` directory support, and the stale-PASS they jointly
fixed.

### 2. Track record on real repos — ✅ MET (2026-08-03)

At least 200 cumulative `lirk build`/`lirk test` invocations across at
least 3 distinct real (non-fixture, non-lirk) repos, with **zero**
`signal: hangup` occurrences and **zero** cache-correctness bugs (a
`cached` result disagreeing with what `--force` produces).

> **Correction (2026-11-21): the zero-cache-bug record did not hold.**
> Running terminal-projects (lirk's largest consumer, 66 targets) on
> 1.0.1 found a stale PASS that had existed since 2026-07-30, so it was
> present when v1.0 was tagged. `furminal/runner.py` loads
> region-explorer by computed file path (`spec_from_file_location`),
> invisible to the import check, and the edge was undeclared. Breaking
> region-explorer left `//furminal:main_test` cached and green while
> `--force` failed all four of its tests. It is a configuration gap of
> the same family as H1/H2, not an engine defect, but it is exactly the
> outcome this clause forbids, and it went unnoticed through the whole
> tally. Response: a build-time note for path-based loads, and
> `lirk verify --mutate`, which finds such edges by behaviour (it
> reports exactly the three on the pre-fix commit, and none after). The
> `signal: hangup` count is still zero.

**Tallied 2026-07-30** from the archived assessments. Counting only
explicitly-stated numbers, treating "16+" as 16 and "repeatedly" /
"multiple batches" as their floor:

| Source | Counted `lirk` invocations |
|---|---|
| `2026-07-26-assessment.md` | 60 test + ≥3 build |
| `2026-07-27-post-go-assessment.md` | 66 test + 1 whole-repo test + ≥1 build |
| `2026-07-27-chess-dogfooding.md` | 23 test + ≥2 build |
| `2026-07-27-adventure-engine-dogfooding.md` | ~30 test + ≥2 build |
| **Documented floor** | **~187** |

Every one of those was fresh-shell with the cache cleared, and every
assessment independently reports zero flaky results and zero
unexplained failures. **No `signal: hangup` has ever been observed in
lirk, and no cache-correctness bug has been reported from real usage.**
The true total is comfortably past 200 once uncounted build
invocations are included — the two failure-mode sub-clauses are
effectively satisfied.

**The "3 distinct repos" clause is now satisfied.** The tallied
invocations above are all against a single consumer,
`terminal-projects`. Self-hosting (criterion 1) supplied the second
repo. **`termrery` is the third** — a curses solar-system orrery, two
packages and four targets, built under lirk 0.1.0 from its first
commit. Its write-up is `docs/lirk-notes.md` in that repo, and every
finding in it was re-reproduced against current lirk source on
2026-08-03 before being recorded below.

Honest caveats on this one:

- **termrery did not tally its invocations.** The session is described
  as "a lot of small edits" with caching "consistently right", which is
  a qualitative report, not a count. The ~187 floor above is unchanged
  by it; what termrery supplies is the third *repo*, which is what was
  actually blocking.
- **No `signal: hangup`, and none has ever been observed** in any repo,
  in any session, to date.
- **The zero-cache-bug sub-clause survives, but it needed a ruling**:
  an undeclared dependency produced a `cached` PASS that `--force`
  turned into a FAIL — a configuration gap rather than an engine
  defect, exactly as the fixture-`data` case was, and it never escaped
  into a wrong answer about lirk's own correctness. Two of these,
  though, both found the moment a new repo was added, was the argument
  that "configuration gap" was carrying more weight than it should.
  **The engine now detects it** (H1, closed 2026-08-03), which is the
  better answer than continuing to rule on it. H2, the other member of
  the family, is closed too (2026-08-04).

Worth recording honestly: self-hosting immediately produced a
cache-correctness bug of exactly the shape this criterion forbids — a
`cached` PASS against edited inputs — which is precisely the evidence a
second repo was supposed to generate. It was a configuration gap
(undeclared fixture `data`) rather than an engine defect, and the fix
made the engine able to express the dependency at all. It is fixed and
covered by tests; the criterion's zero-count is intact because the bug
never escaped into a real consumer's usage. But it is the clearest
possible argument for why the third repo matters — and the third repo
then produced a second bug of exactly the same family (H1), which
settles the argument.

**Decided 2026-08-02: self-hosting counts as the second repo.** lirk
building itself is a genuinely different shape from a games monorepo —
different dependency topology, different test style — so it exercises
the overfitting risk the clause was written to guard against. This
makes criterion 1 a prerequisite for criterion 2 rather than an
independent item.

**What the third repo bought, which is the whole point of the clause:**
six backlog items — H1, M3, M4, M5, M6 and L6 below — most of which no
amount of further running against `terminal-projects` or lirk itself
would have produced, because both of those repos declare their deps
correctly, both keep their `.lirk-root` in place, and neither has an
entry point. The pattern from self-hosting repeated exactly: a new
consumer finds gaps by *being shaped differently*, not by adding
invocations.

### 3. KNOWN_ISSUES.md clear — ✅ MET

No open entries beyond ones explicitly marked cosmetic-only.

**Status:** two entries. The PYTHONPATH bug is Fixed. The Bazel/JVM
entry is confirmed-and-unfixable platform reality, not an open lirk
defect. Recheck this whenever an entry is added.

---

## Open bugs and gaps

Ordered by priority. Everything here was verified against current
source; nothing is carried forward from resolved historical reports.

The termrery trial (2026-08-03) produced H1 and M3–M6 and L6; all are
now closed. What remains open is only what needs input from outside the
repo, or what was left deliberately.

### HIGH

*None. H1 and H2 are both closed — see Recently closed. No known
stale-PASS path remains open.*

### MEDIUM

*None. M1–M6 are all closed — see Recently closed.*

### LOW

**L3 (partial) — concurrent invocations can still lose cache entries.**
The torn-temp-file half is fixed (the temp filename now carries the
PID). `load_cache`/`save_cache` remain an unlocked read-modify-write,
so two overlapping runs can still lose one run's entries.

Deliberately left: the failure mode is a redundant rebuild, never a
wrong result, and the single-device workflow makes overlap unlikely.
Fixing it properly means a lock file, which is real complexity and a
new failure mode of its own (a stale lock after a crash — and iSH-AOK
crashing is the environment this tool exists for). Not worth it unless
concurrent runs actually become a workflow.

**L7 — an undeclared *ancestor* `__init__.py` is still unfingerprinted.**
The residual sliver of H2. `_resolve_module` resolves a dotted path to
one file and does not also collect the `__init__.py` of each package
along the way, so `import a.b.c` never looks at `a/__init__.py`; if no
target declares that file, editing it invalidates nothing. Same
stale-PASS shape as H2, two steps further out.

Left open deliberately rather than folded into the H2 fix, on evidence:
zero imports across `terminal-projects` (66 targets), lirk (13) and
`termrery` (4) resolve to an undeclared ancestor init. Collecting
ancestors also turns one clear error into several, which is the reason
`_resolve_module` doesn't do it. Worth doing if a repo ever hits it;
not worth the message noise before that.

*Everything else on this list is closed — see Recently closed.*

### Raised by termrery, already settled — not backlog

Recorded so they aren't re-derived from the review as if they were new:

- **A `binary` target type and `lirk run`** (their #2). Off the roadmap
  per DESIGN §6. The real cost they hit was M5 — a docs gap in the
  replacement pattern, not a missing feature — and that pattern is now
  written up in `getting-started.md` (D4, closed).
- **`lirk query` / any way to list targets** (their #5 — "`grep -r
  '^name' */BUILD.lirk` is the current answer"). Deferred on evidence
  in §6, most recently at ~26 targets; termrery has four, so it is no
  new evidence against that. Worth revisiting only if a consumer
  arrives with a target count where grep genuinely stops working.

---

## Documentation gaps

*None. D2 is closed — see Recently closed.*

---

## Roadmap (proposed 2026-11-21)

**The position lirk should own:** the build tool that runs where heavier
ones can't (iSH, Termux, Raspberry Pi, Chromebooks, locked-down
machines, cheap CI), and whose green you can believe. Not a smaller
Bazel. Every feature should strengthen one of three things: **trust**
(a cached green is always a real green), **adoption** (minutes to
convert a repo, not an afternoon) or **reach** (runs anywhere Python
does). Python-only, `library`/`test`-only stays the scope.

| Milestone | Theme | Contents |
|---|---|---|
| **v1.0** | Tag it | Version decision, PyPI (F9), CI matrix (F1) |
| **v1.x** | Trust and adoption | ~~Environment fingerprinting~~, ~~pytest runner~~, ~~`lirk verify`~~, ~~`lirk fix` / `lirk init`~~ — **all done** |
| **v1.y** | Speed without parallelism | `--changed`, per-target timings (F2), `--fail-fast` (F4), repo-wide timeout (F3) |
| **v2** | Teams | JSON / JUnit-XML output, a GitHub Action; opt-in `-j` only with evidence |

- [x] **R1 — Fingerprint the Python environment.** Done 2026-11-21:
  the interpreter version and installed distributions are folded into
  every fingerprint (DESIGN §4). Closed a real stale-PASS path: upgrading
  Python or a package left everything `cached`.
- [x] **R2 — `lirk verify`.** Done 2026-11-21. Re-runs every valid
  cache entry in scope (or `--sample N`, seeded), reports any that now
  fail as `STALE`, evicts them, and exits 1. On lirk itself: 12 cached
  results verified, 0 stale. DESIGN §4.
- [x] **R3 — pytest runner.** Done 2026-11-21: `runner = "pytest"`,
  one `subprocess.run()` per src, exit 5 detected as "no tests".
  conftest and pytest config files from the package up to the root are
  fingerprinted, and conftest imports are checked against `deps`
  (DESIGN §5). Self-hosting doesn't exercise it, since lirk's own suite
  is unittest; the `pytest_repo` fixture and tests do.
- [x] **R4 — `lirk fix` and `lirk init`.** *`init` done 2026-11-21*:
  drafts skeleton BUILD files (files and target types only) and hands
  the new targets to `fix`'s planner for every dep. From zero BUILD files,
  the `sample_repo` fixture reaches 3/3 tests passing with no hand edits.
  *`fix` done 2026-11-21*:
  adds every missing `deps` entry the import check can attribute to
  exactly one target, refuses edits that would create a cycle (counting
  the run's own earlier additions), drops additions another addition
  already reaches, and re-parses each edited file — writing nothing
  unless the result is exactly the originals plus the planned deps.
  Comments and layout are preserved. `--dry-run` reports only.
  *`init` remains.* Original note: The import check already
  knows the exact missing `deps` label; `fix` writes it into the BUILD
  file instead of only failing. `init` generates first-draft BUILD files
  for an existing repo from its imports. Rewriting TOML without
  destroying comments needs care (no stdlib TOML writer) — likely
  append-only edits to a `deps` line.
- [ ] **R5 — `lirk test --changed [ref]`.** Run only targets whose
  closure contains a file changed since `ref` (default: the working
  tree versus `HEAD`). Reverse-closure over the existing graph; the
  `git diff --name-only` call is a plain subprocess, outside the action
  model.
- [ ] **R6 — Machine-readable results.** Optional `--report json` /
  JUnit XML written *after* the run, for CI dashboards. Writing a report
  is fine; DESIGN §1 forbids only *reading* test results back from a
  file.
- [ ] **R7 — Opt-in parallelism, maybe never.** The v1 criteria now
  permit it, but it reintroduces the concurrent-lifecycle surface lirk
  exists to avoid. Serial stays the default permanently; an opt-in `-j`
  is considered only if users ask, and only after a long soak test
  hunting `signal: hangup`. One hangup and lirk loses its reason to
  exist.

**Deliberately not on the roadmap:** other languages, genrules,
remote caching, sandboxing. Each widens what has to stay correct, in
territory Bazel already covers.

## Feature ideas (proposed 2026-11-21)

Candidates, not commitments. Each one fits inside DESIGN §1 (one
direct `subprocess.run()` per src, serial, no process groups) and none
of them reopens a settled decision in §6. Roughly in order of value
for effort.

- [x] **F1 — CI on every supported Python.** Done 2026-11-21:
  `.github/workflows/ci.yml`. Original note: No workflow exists, and
  `pyproject.toml` promises 3.11+ while development happens on one
  version. A GitHub Actions matrix (3.11, 3.12, 3.13) running both
  `unittest discover` and `python3 -m lirk test //...` would catch a
  3.11-only break, like the `Ran 0 tests` exit-code difference L1 had
  to work around.
- [x] **F2 — Per-target durations in the output.** Done 2026-11-21:
  test lines always, `built` lines over 1s, and a "slowest" list when a
  run's tests total 10s or more. e.g. `PASS
  //a:a_test (12.4s)`. Cheap (one `time.monotonic()` around the
  existing call), and it is the data you need to choose a sensible
  `timeout` and to find the slow target in a suite.
- [x] **F3 — Repo-wide default `timeout` in `.lirk-root`.** For
  example `timeout = 60`, so the 600s fallback can be lowered once
  rather than per target. A per-target value still wins. It would
  need to enter the fingerprint the same way the per-target one does.
- [x] **F4 — `--fail-fast`.** Stop after the first FAIL. Keep-going
  stays the default (it is the deliberate behaviour per §5), but on a
  phone a long suite with a broken core library is mostly waiting.
- [x] **F5 — Prune dead cache entries.** `.lirk-cache.json` keeps
  entries for targets that were deleted or renamed, forever. Drop keys
  whose label is no longer in the graph when saving. This is safe
  because only labels absent from the *whole* graph are dropped, never
  ones merely outside this run's scope.
- [ ] **F6 — Warn about undeclared `.py` files in a package.** A
  `lirk build` note, not a failure, listing `.py` files in a package
  directory that no target declares. It catches the H2 family *before*
  something imports the file, and catches dead files. Needs a design
  decision on how test-only helpers and scripts opt out.
- [ ] **F7 — Pass a test filter through to unittest.** e.g. `lirk test
  //a:a_test -- -k castling`, appended to the existing argv (an
  argument, not a process-model change). A filtered run must **never**
  be written to the cache, or it would record a partial pass as a full
  one.
- [x] **F8 — Flag `ignore` entries that match nothing.** A typo'd path
  in `.lirk-root`'s `ignore` silently excludes nothing, and the
  failure then shows up as a confusing graph error from the very
  fixtures it was meant to hide.
- [~] **F9 — Publish to PyPI after the v1 tag.** *In progress
  2026-11-21:* trusted-publishing workflow and packaging metadata ready
  (`docs/RELEASING.md`); the first upload will be 1.0.1. Original note: `pip install lirk`
  rather than a git URL. Packaging is already in place.
- [ ] **F10 — L7 (ancestor `__init__.py`).** Already tracked above;
  listed here so the whole "what next" picture is in one place. Still
  gated on a real repo hitting it.

## Next actions, in priority order

**All three v1 criteria hold and the high-priority correctness work is
done, so v1 is ready to tag** (decided 2026-08-03: fix first, tag after
— tagging v1 with a known silent-wrong-pass path open is the thing the
criteria exist to prevent). H1 and H2 are both closed, and **no known
stale-PASS path remains open.**

The whole termrery-derived backlog is now closed too (M3–M6, L6, D4,
2026-08-04), so nothing is queued behind the tag either.

1. **Roadmap v1.x is complete** (R1–R4) and released as `v1.0.0`.
   Next is evidence rather than features: the `slingshot` project, built
   with lirk from its first commit, is the fourth real repo. Its
   `docs/lirk-notes.md` drives what comes next. F9 (PyPI) is the
   remaining adoption step.
2. **L7**, only if a real repo hits it. **L3**'s remaining half only if
   concurrent runs become a real workflow.

## Recently closed

- **terminal-projects on 1.0.1: path-loaded code, and `verify --mutate`**
  (2026-11-21). See the correction under criterion 2. Two changes:
  - **A note when a src loads code by file path**
    (`spec_from_file_location`, `SourceFileLoader`, `runpy.run_path`,
    `load_source`). The path is almost always computed, so it can't be
    resolved, but the call can be seen. It's a note, not a failure (a
    correctly declared target looks the same), printed only when the
    target is rebuilt.
  - **`lirk verify --mutate`**, built from terminal-projects' own sweep
    script. In a copy of the repo, it breaks each library source in turn
    and runs every passing test that claims not to depend on it; any
    failure is an undeclared edge. It checks behaviour, so it catches
    path loads and any other indirection, but not files read only as
    data. On terminal-projects at the pre-fix commit it finds exactly
    the three edges (984 test runs, ~80s here); after the fix, none.
    lirk's own repo: none. `--sample N` and labels bound the cost.

- **slingshot round 2: #9, #12–#15** (2026-11-21), from its
  `docs/lirk-notes.md` (75 invocations, no `signal: hangup`). Each was
  reproduced against slingshot itself before and after the fix.
  - **#9 (high): entry-point tests cached a stale PASS.** A test that runs
    the app (`subprocess.run([sys.executable, "-m", "cli.main"])`)
    imported nothing from it, so no dep was required and `fix`/`init`
    added none. The import check now treats a literal `"-m", "pkg.mod"`
    pair and `runpy.run_module("pkg.mod")` as a dependency, reported as
    "runs". On slingshot, removing its three hand-declared entry-point
    deps now fails the build, and `lirk fix` restores exactly those.
    Docs gained the BUILD block and the reason.
  - **#13: a pytest file that skips itself counted as "no tests".** pytest
    exits 5 both for an empty file and for a module-level
    `importorskip`; the summary line ("1 skipped" vs "no tests ran")
    tells them apart, and a self-skipped file now passes. The
    environment fingerprint reruns it once the package is installed.
  - **#12:** `srcs`/`data` paths that leave the repo are a graph error.
    Paths into other packages are still fine, and the docs show the
    shared-data-target pattern.
  - **#14:** an unknown label suggests the closest one (same package
    first, near-ties only). A library passed to `lirk test` lists its
    tests, nearest first.
  - **#15:** `init` no longer skips `env/`, `venv/` by name (a virtualenv
    is recognised by `pyvenv.cfg`), announces `build/`, `dist/` and
    virtualenvs it skips, and hints directories that hold no Python as
    `data`. It also fixes "1 srcs" and says "split targets further as
    needed". slingshot's own `init` trial went from 20 MANUAL to 1, a
    real cycle (`env` ↔ `npbackend` at one-target-per-directory), and
    the MANUAL text now suggests splitting.
  `ACTION_VERSION` 12 → 13 (#9 and #13 change what a result means).
  Version 1.1.0.
  - **Caught in lirk's own repo by the #9 fix, minutes after it landed:**
    `bench/run.py` runs `python -m lirk` without depending on lirk. Now
    declared. "Runs a package" also requires its `__main__.py`, which is
    what `-m pkg` actually executes. (The self-hosted run flagged it.
    The first push of the #9 commit went out with that red, because a
    pipe hid the exit code. Fixed in the next commit.)

- **Quick wins F3, F4, F5, F8** (2026-11-21).
  - **F4 `--fail-fast`** on `build` and `test`: stops before starting
    anything new after a failure, and counts what was not run.
  - **F3 repo-wide `timeout`** in `.lirk-root`, applied to the `Target`
    at load time, so the effective timeout is what gets fingerprinted.
    A target's own setting wins.
  - **F5:** cache entries for targets absent from the *whole* graph are
    dropped on save, never ones merely outside the run's selection.
  - **F8:** an `ignore` entry matching no directory warns on stderr.

- **Scale benchmark, and two hotspots fixed** (2026-11-21). `bench/`
  generates repos of any size and shape (wide, deep, mesh) where every
  declared dep is a real import, and times lirk on them (cold, cached,
  one-file edit, test, verify, fix). Nothing scaled badly, but the
  profile showed two avoidable costs. A cold 1,000-target build went
  from 1.40s to 0.73s:
  - **Repeated import lookups (half the build).** Now memoized per run,
    per (module, base directory), and never across runs.
  - **Rewriting the cache after every target (17%, O(n²)).** Test passes
    are still saved immediately. Validations are batched to one save
    per second, and a `finally` saves on the way out. Tests cover the
    batching and that Ctrl-C keeps finished results.
  No `ACTION_VERSION` bump: neither changes what a result means.
  **Still to measure on iSH**, the environment lirk targets.

- **Docs rewritten for users** (2026-11-21). The published site now
  leads with what lirk does and why to use it: Overview, Getting
  started, Existing repos, BUILD files, Commands, How it works and
  Troubleshooting. The tutorial was re-run verbatim to confirm its
  output. Maintainer docs moved to `docs/dev/`, and history (the
  original docs, assessments, reviews, session log) to `docs/archive/`.
  Both are excluded from the site. A short README and a new
  CONTRIBUTING.md replace the long README.

- **v1.0.0 released** (2026-11-21). Tagged on `main` at the PR #3 merge
  (`39047ee`), so the release includes all of v1.x: environment
  fingerprinting, pytest runner, `verify`, `fix`, `init`, CI, timings,
  and the slingshot fixes.

- **slingshot milestone-1 findings** (2026-11-21). The fourth real repo,
  built with lirk from its first commit, reported in its
  `docs/lirk-notes.md`. Every item was reproduced here before fixing:
  - **Root `conftest.py` silently not loaded (bug).** pytest, run from
    the package directory, took that directory as rootdir and skipped
    the repo-root conftest that lirk fingerprints. slingshot's
    unseeded-randomness guard was inactive while its tests passed. Now
    `--rootdir` and `--confcutdir` are pinned to the repo root. The
    regression test runs from a temp copy, because inside this checkout
    lirk's own `pyproject.toml` made pytest load the conftest by
    accident and hid the bug. `ACTION_VERSION` 11 → 12.
  - **`lirk build` redid library checks `lirk test` had just done.**
    Cache keys now name the action (`build:` = validates, `test:` =
    tests ran), so validations are shared between commands. A built
    test target still never counts as tested.
  - **Messages:** `fix --dry-run` says `would fix`; `verify` labels
    lines `(build)` / `(tests)` and names the targets it couldn't check.
    (`deps` placement was already fixed by `init`'s work.)
  - **Stale docs:** the "two subcommands" line, the contradiction about
    non-`.py` files in `srcs` (the real error is a parse-time rejection),
    and three different gitignore lists, now one.

- **Version set to 1.0.0** (2026-11-21). The criteria never fixed a
  number; 1.0.0 is the plain reading of "v1". The git tag waits for the
  merge to `main`.
- **D2 — upstream iSH-AOK issue linked** (2026-11-21).
  `KNOWN_ISSUES.md` now links
  [emkey1/ish-AOK#542](https://github.com/emkey1/ish-AOK/issues/542).
  Identified by search, not by a recorded URL: same filing date as the
  local draft (2026-07-28), same title and the same HotSpot error.

- **Codebase review pass** (2026-11-21). Two crashes found by probing
  edges the suite didn't reach, three smaller correctness fixes, and
  three features chosen because they serve the existing `library`/`test`
  scope without touching the process model or reopening a settled
  decision (§6 of DESIGN.md is unchanged). Suite 143 → 176; self-hosted
  build/test green. `ACTION_VERSION` 10 → 11.

  *Bugs:*
  - **A timed-out test that had printed anything crashed lirk.**
    `subprocess.run` raises `TimeoutExpired` carrying *bytes* even with
    `text=True`; `run_test` joined them with `str` output and died with
    `TypeError`. The existing hang fixture printed nothing, which is
    why it never showed. Now decoded; fixture
    `hang_repo/test_noisy_hang.py` prints before hanging, and the test
    was confirmed to crash against the old source.
  - **A deep dependency chain crashed the topological sort** with
    `RecursionError` past ~1000 levels. Now an iterative DFS producing
    the identical order and the same full-path cycle message; tested at
    depth 3000.
  - **A src declared by two targets made the import check
    order-dependent.** `owner_index` kept whichever declaration was
    indexed last, so depending on the *other* declaring target reported
    a false "not in deps". It now records every declaring target and
    accepts any one in the closure.
  - **The zero-tests check matched `Ran 0 tests` anywhere in stderr**,
    including an inner run echoed by a test that drives unittest itself
    (which lirk's own suite does). Now only the last line-anchored
    `Ran N tests in` summary counts.
  - **Repeated `srcs`/`deps`/`data` entries are rejected at parse
    time.** A repeated test src ran twice.

  *Improvements and features:*
  - **The BUILD.lirk scan prunes** dot-prefixed and `ignore`d
    directories instead of `rglob`-ing into `.git`/`.venv` and
    filtering afterwards — on iSH-AOK the dominant cost of the scan.
  - **Label patterns and multiple labels on the command line:**
    `//pkg:all`, `//pkg/...`, and any number of labels per invocation.
    Previously `//...` was the only wildcard, and malformed labels on
    the command line reported as "unknown target"; they now say
    *malformed* or *must be absolute*, as `deps` labels already did.
  - **Per-target `timeout`** on `test` targets (positive integer
    seconds, part of the fingerprint). A wedged test no longer has to
    cost the full 600s.
  - **`lirk clean`** deletes the cache and any stray temp files, so a
    full reset no longer means remembering the filename.
  - `run_test`'s child environment no longer shadows its `env`
    (`ImportEnv`) parameter.

- **M4 — the root is named, and the cwd fallback announces itself**
  (2026-08-04). `main` prints a stderr note when no `.lirk-root` is
  found, naming the directory it fell back to; graph errors and
  unknown-target errors both print `lirk: repo root is <path>`. The note
  is suppressed when a marker is found or `--root` is given — a warning
  about an implicit choice is noise once the choice is explicit, and a
  message on every run of every correctly configured repo would train
  people to skip it. Tests cover all four cases, including termrery's
  exact confusion (build from a package subdirectory with no marker: the
  error says the dep doesn't exist, and now also says why).
- **M3 — `srcs` is restricted to `.py`, by extension, at parse time**
  (2026-08-04). Rejected in `_parse_target` with a message pointing at
  `data`, so the `srcs`/`data` split is self-teaching rather than
  something you discover later. This is what makes DESIGN §2's existing
  claim true as written: left to `ast.parse`, `hello` in a `.txt` built
  clean while a sentence didn't. No `ACTION_VERSION` bump — a
  BUILD-parse error is loud and immediate, not a green result computed
  under changed rules. The `binary_src_repo` fixture is unaffected
  because its PNG is *named* `broken.py`, which is exactly the case an
  extension check can't catch and `validate_target`'s decode guard
  still must.
- **M6 — a failing run lists what failed** (2026-08-04).
  `_print_failures` restates the failed labels immediately above the
  counts. Not the summarizing layer ruled out in DESIGN §6: it reprints
  labels lirk already printed and touches nothing about captured
  output. `SKIP`ped targets are deliberately excluded — they are
  consequences, and listing them buries the label worth acting on. A
  test asserts the list lands *below* the unittest traceback, since
  landing above it would be no better than the line that already
  scrolled off.
- **L6 — `lirk --version` works without a subcommand** (2026-08-04).
  Via a small custom argparse action rather than `action="version"`, so
  `importlib.metadata` is imported only when the flag is passed —
  DESIGN §6 settled that startup cost is the dominant per-invocation
  expense, and a flag almost no run uses must not add to it. Prints a
  clear "not installed; running from a source checkout" when the
  distribution isn't found, rather than guessing a version. A test
  asserts the flag didn't make the required subcommand optional.
- **M5 / D4 — the entrypoint-as-`test`-target pattern is documented**
  (2026-08-04). `getting-started.md` gains a "Covering your entry point"
  section: a `--selftest` path on the entry point, a `test` target
  whose src subprocesses `python3 -m cli.render`, and the instruction to
  assert all three of starts / exits 0 / produces output — exit code
  alone passes for a program whose `main()` is never called, which is
  exactly termrery's failure. This is what makes DESIGN §6's rejection
  of `lirk run` defensible rather than merely recorded: the decision
  rests on the replacement being covered, and now it is discoverable.
- **H2 — an import of a file no target declares now FAILs**
  (2026-08-04). The other half of H1, and the last known stale-PASS
  path. `undeclared_imports` already resolved these files and skipped
  them when no target owned them; it now reports them with a distinct
  message, since the fix differs — declare the file, rather than add a
  `deps` entry:

  ```
    FAIL   //leaf:orphan_user: orphan_user.py imports 'orphan.thing' -- no target declares orphan/thing.py
  ```

  **Rejecting, not implicit fingerprinting.** Both options closed the
  stale PASS; rejecting won on three counts. It keeps the graph fully
  explicit rather than half-inferred. It gets transitivity for free —
  implicit folding would need a walk over the undeclared-file import
  graph, since orphan A importing orphan B leaves B unfingerprinted
  otherwise. And it keeps `compute_fingerprints` free of `ast`, which
  implicit folding would have required on every run, including fully
  cached ones where the parse is currently skipped entirely.

  **The recorded objection was measured, not assumed.** This item said
  rejecting "would fail ordinary repos — an undeclared `__init__.py` is
  extremely common". Checked before landing, by resolving every import
  in every declared src exactly as `undeclared_imports` does:
  `terminal-projects` (66 targets), lirk itself (13) and `termrery` (4)
  produce **zero** imports resolving to an undeclared file — 83 targets,
  no false positives, the same result H1 got. The exposure is also
  narrower than assumed, because `_resolve_module` doesn't collect
  ancestor package inits, so only `from pkg import ...` can reach one.
  Exactly one fixture hit it, `rootimport_repo`'s empty
  `pkg/__init__.py`, now declared — which is what `lirk/BUILD.lirk`
  already does with its own `:init` target.

  `ACTION_VERSION` 9 → 10: a prior green was computed under rules that
  permitted this. Residual sliver tracked as L7. Fixture: `import_repo`
  already carried `orphan_user.py`; its assertion is inverted, and a CLI
  test declares the orphaned file on a writable copy to prove the
  documented fix works end to end — without that, a check that rejected
  every unowned import would look correct. Suite 127 → 130.

- **H1 — `deps` is now checked against real imports** (2026-08-03).
  After every src parses, the `Import`/`ImportFrom` nodes of the trees
  `validate_target` already built are walked, each module resolved the
  way the runner resolves it (package dir, then repo root), and the
  target FAILs if a resolved file belongs to a target outside its
  transitive dep closure:

  ```
    FAIL   //cli:cli: render.py imports 'orrery.camera' (//orrery:orrery), not in deps
  ```

  **FAIL, not warn** — decided deliberately: a warning leaves the
  stale-PASS path open, which was the entire reason the item was HIGH.
  `ACTION_VERSION` 8 → 9, since a prior green was computed under rules
  that permitted this.

  Decisions inside it, all written up in DESIGN §3: checked against the
  transitive closure rather than direct deps (the closure is what the
  fingerprint covers; direct-only is hygiene, buys no correctness here,
  and would reject lirk's own BUILD files); a file no target declares
  is not reported (that's H2, and a different fix); resolution mirrors
  the runner rather than using `importlib`, so nothing is imported to
  find out; the AST is reused rather than re-parsed. `ImportEnv` is
  assembled by `cli.py` and passed down, so `actions.py` still doesn't
  import the graph layer.

  **Adoption cost turned out to be zero.** Run against all three real
  repos before landing: lirk itself (13 targets), `terminal-projects`
  (66), and `termrery` (4) all build clean — 83 targets, no false
  positives. termrery's own BUILD files were correct; the violation in
  their review was staged in a throwaway copy.

  Fixture: `import_repo`, which pairs `undeclared.py` and `declared.py`
  — the same import, differing only in the BUILD file, so a check that
  rejected everything couldn't look correct. Suite 112 → 127.
- **Criterion 2: the third repo is `termrery`** (2026-08-03). Two
  packages, four targets, a curses application; built under lirk from
  its first commit rather than converted afterwards. Its review lives
  at `docs/lirk-notes.md` in that repo and is the source of H1 and
  M3–M6. Every claim in it was re-reproduced against current lirk
  source before being recorded, and one turned out to be worse than
  reported: their "deps are documentation, not enforced" is also a
  stale-PASS mechanism, since an undeclared edge is absent from the
  fingerprint (H1). The trial cost nothing in engine changes and
  returned five findings, four of which neither existing repo could
  have produced.
- **D3 — onboarding guide written** (2026-08-02).
  `docs/getting-started.md`: a worked two-package example with real
  captured output, converting an existing repo, a full CLI/label
  reference, an output-and-exit-code key, and troubleshooting keyed to
  actual error strings. The gap it closes: the docs were complete as
  *reference* (`build-format.md`) and *rationale* (DESIGN.md) but had
  no path a stranger could follow, and several facts a new consumer
  needs most — `--force`, the `cwd`+`PYTHONPATH` import model, that
  `//...` is the only wildcard — existed only in DESIGN.md or in
  `cli.py`. Written while actually building the example repo, which is
  how the module-shadowing trap (a module named the same as its own
  package directory) got found and documented.
- **L1 — a test module with zero tests now fails** (2026-08-02).
  Detected from the `Ran 0 tests` summary line, which `unittest` writes
  on every version, rather than by raising the Python floor to 3.12.
  That keeps 3.11 supported (as `pyproject.toml` promises) and is the
  more robust signal. Checked independently of the exit code rather
  than as a fallback for a zero one, so the failure message names the
  reason on 3.12 too — there the exit code already caught it but
  reported only `1 of 1 src files failed`. Fixture: `no_tests_repo`.
- **L2 — a timeout no longer abandons the remaining srcs**
  (2026-08-02). `TimeoutExpired` records the module and continues
  instead of returning, so one hung src no longer hides every src after
  it. The fixture pairs the hanging src with a deliberately *failing*
  one, since a passing one could not distinguish "ran" from "skipped".
- **L5 — `needs_build`'s parameter renamed** `label` → `cache_key`
  (2026-08-02), with a docstring saying what it actually receives.
- L1 and L2 together bumped `ACTION_VERSION` 7 → 8: both change what a
  passing test means, so prior green results must not be trusted from
  cache.
- **D1 — `docs/index.md` refreshed** (2026-08-02). Replaced the "Not
  yet self-hosting" status with the three v1 criteria and their honest
  state, added an Installation section, and documented `data` and
  `.lirk-root`'s `ignore` list, neither of which the page had ever
  mentioned.
- **Criterion 1: lirk is self-hosting** (2026-08-02). See the criterion
  above for the shape and the decisions. `lirk test //...` runs
  alongside `unittest discover`, not instead of it.
- **L4 — the repo scan takes an ignore list** (2026-08-02). Promoted
  from LOW the moment self-hosting was attempted: `tests/fixtures/`'s
  24 `BUILD.lirk` files made `lirk build //...` fail to load the graph
  at all (`//tests/fixtures/cycle_repo/x:x: dependency '//y:y' does not
  exist`). `.lirk-root` now doubles as repo config carrying
  `ignore = [...]` of root-relative directories, excluded with their
  subtrees. An empty marker behaves exactly as before. Entries that are
  absolute or contain `..` are rejected. Fixture: `ignore_repo`.
- **`data` entries may name a directory** (2026-08-02). Fingerprinted
  recursively, with each file's relative path hashed alongside its
  contents so additions and removals register. Dot-prefixed and
  `__pycache__` segments are skipped — a fixture tree accumulates
  `.pyc` files from running the very tests the fingerprint gates, which
  would otherwise change the input every run and cache nothing. No
  `ACTION_VERSION` bump: file-only `data` fingerprints are unchanged,
  so no existing cache entry is falsely invalidated.
  Fixture: `datadir_repo`.
- **Stale PASS on edited fixtures** (2026-08-02). Found by self-hosting
  and verified directly: appending to a fixture that `test_targets`
  reads left it `cached` and green. `tests/BUILD.lirk` now declares
  `data = ["fixtures"]` on the four modules that read fixtures
  (`test_targets` builds its inputs with `tempfile` and declares none).
  Required the `data` directory support above — enumerating 61 files by
  hand would have gone stale the next time a fixture was added.
- **M1 — one missing source file no longer aborts the repo-wide run**
  (2026-08-02). The preflight loop now marks missing-file targets
  failed instead of `return`ing, and excludes them plus their
  transitive dependents from `order` before `compute_fingerprints`
  (which would `KeyError` on an absent dep fingerprint otherwise).
  Dependents are reported by the existing dep_failure SKIP branch, and
  unrelated targets build and reach the cache normally. No
  `ACTION_VERSION` bump — this changes which targets are attempted, not
  what a successful build means. Fixture: `missing_src_partial_repo`.
- **M2 — test srcs in a package subdirectory now run** (2026-08-02).
  `run_test` derives a dotted module path relative to the package
  rather than `Path(src).stem`, so `sub/test_nested.py` runs as
  `sub.test_nested`. Verified to resolve under the existing
  `cwd=pkg_dir` + `PYTHONPATH=root` model with no `__init__.py` needed
  (PEP 420 namespace packages). Also fixes the silent same-stem
  collision, where two srcs named `test_dup.py` in different
  subdirectories became one module and only one ever ran.
  `ACTION_VERSION` 6 → 7. Fixtures: `subdir_test_repo`,
  `stem_collision_repo`.

- **Suite was 90/91 on Windows** (2026-07-30). `validate_target`'s
  `read_text()` used the locale encoding, so cp1252 decoded the
  `binary_src_repo` fixture and it reached `ast.parse` as a null-byte
  `SyntaxError` rather than the intended `UnicodeDecodeError`. Pinned
  `encoding="utf-8"`; `ACTION_VERSION` 5 → 6. Now 91/91 on Windows.
- **`docs/design/target-format.md` deleted** (2026-07-30), duplicate of
  `docs/build-format.md`; `targets.py`'s docstring repointed.
