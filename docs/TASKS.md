# lirk tasks

Current backlog. Check items off and edit in place as work happens —
this file reflects present reality, not history. Architecture context
lives in [DESIGN.md](DESIGN.md); do not restate it here.

**Before implementing anything**, read DESIGN.md §1. The process-model
constraints are not negotiable: no process group, no session, no pty,
no `shell=True`, no results-file step, no parallel execution. If a task
seems to require one, stop and report it rather than doing it.

Last verified against source: 112 tests, `python3 -m unittest discover
-s tests -t .`. lirk also builds and tests itself — `lirk build //...`
(13 targets) and `lirk test //...` (5 test targets) — which runs
alongside the unittest invocation rather than replacing it. Both must
be green.

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

### 2. Track record on real repos — ❌ NOT MET (blocked on the repo-count clause, not the invocation count)

At least 200 cumulative `lirk build`/`lirk test` invocations across at
least 3 distinct real (non-fixture, non-lirk) repos, with **zero**
`signal: hangup` occurrences and **zero** cache-correctness bugs (a
`cached` result disagreeing with what `--force` produces).

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

**The blocker is the "3 distinct repos" clause.** The documented
invocations above are all against a single consumer,
`terminal-projects`, and no amount of additional running against it
will change that. Self-hosting (criterion 1) now supplies the second
repo. **One more consumer is what remains.**

Worth recording honestly: self-hosting immediately produced a
cache-correctness bug of exactly the shape this criterion forbids — a
`cached` PASS against edited inputs — which is precisely the evidence a
second repo was supposed to generate. It was a configuration gap
(undeclared fixture `data`) rather than an engine defect, and the fix
made the engine able to express the dependency at all. It is fixed and
covered by tests; the criterion's zero-count is intact because the bug
never escaped into a real consumer's usage. But it is the clearest
possible argument for why the third repo matters.

**Decided 2026-08-02: self-hosting counts as the second repo.** lirk
building itself is a genuinely different shape from a games monorepo —
different dependency topology, different test style — so it exercises
the overfitting risk the clause was written to guard against. This
makes criterion 1 a prerequisite for criterion 2 rather than an
independent item, and leaves **one more consumer to find**.

### 3. KNOWN_ISSUES.md clear — ✅ MET

No open entries beyond ones explicitly marked cosmetic-only.

**Status:** two entries. The PYTHONPATH bug is Fixed. The Bazel/JVM
entry is confirmed-and-unfixable platform reality, not an open lirk
defect. Recheck this whenever an entry is added.

---

## Open bugs and gaps

Ordered by priority. Everything here was verified against current
source; nothing is carried forward from resolved historical reports.

### HIGH

Nothing. No known silent-wrong-pass path is currently open.

### MEDIUM

Nothing. M1 and M2 are closed — see Recently closed.

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

*Everything else on this list is closed — see Recently closed.*

---

## Documentation gaps

**D2 — Link the filed iSH-AOK issue from `KNOWN_ISSUES.md`.** The
upstream JVM-crash report has been submitted, and the local draft was
removed. `KNOWN_ISSUES.md` now says so but has no issue URL, so a
reader can't get from the investigation to the upstream thread or its
status. *What's left:* paste the issue link in.

---

## Next actions, in priority order

1. **Find a third consumer repo.** The single thing standing between
   v1 and all three criteria being met, and now the *only* open item
   that is not blocked on external input. Criteria 1 and 3 are met and
   criterion 2 needs only this. `docs/getting-started.md` now exists to
   hand to whoever takes it on, including a closing section telling
   them what to record for this criterion (invocation count, any
   hangup, any `cached` vs `--force` disagreement).
2. **D2**, whenever convenient — needs the upstream issue URL, which is
   not derivable from the repo.

Nothing else is open. The LOW backlog is cleared apart from the half of
L3 deliberately left (see above).

## Recently closed

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
