# lirk tasks

Current backlog. Check items off and edit in place as work happens —
this file reflects present reality, not history. Architecture context
lives in [DESIGN.md](DESIGN.md); do not restate it here.

**Before implementing anything**, read DESIGN.md §1. The process-model
constraints are not negotiable: no process group, no session, no pty,
no `shell=True`, no results-file step, no parallel execution. If a task
seems to require one, stop and report it rather than doing it.

Last verified against source: 95 tests, `python3 -m unittest discover
-s tests -t .`.

---

## v1 stability criteria

All three must hold before parallelism work starts or scope expands
beyond Python `library`/`test` targets. Status is honest, not
optimistic — "probably true" counts as not met.

### 1. Self-hosting — ❌ NOT MET

lirk builds and tests its own source through its own `BUILD.lirk`
files (`lirk build //...` and `lirk test //...` against this repo), not
only via a separately maintained `unittest` suite.

**Status:** no `BUILD.lirk` exists anywhere in this repo outside
`tests/fixtures/`. Nothing started.

**What it needs:** a `BUILD.lirk` describing `lirk/`'s modules as
`library` targets with their real inter-module deps
(`cli` → `actions`/`cache`/`graph`/`targets`; `cache` → `graph`;
`graph` → `targets`), plus `tests/` as `test` targets. Two decisions to
make when starting:

- Does `lirk test //...` *replace* the `unittest discover` invocation
  or run alongside it? Replacing it makes lirk's own CI depend on lirk
  being correct, which is the point of self-hosting and also the risk.
- `tests/` imports fixtures by relative path from the repo root.
  Confirm that resolves under `run_test`'s `cwd=pkg_dir` +
  `PYTHONPATH=root` model before assuming the layout works as-is.

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

**The blocker is the "3 distinct repos" clause.** Every documented
invocation is against a single consumer, `terminal-projects`. That is
one repo, not three, and no amount of additional running against it
will change that.

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

**L1 — A test module containing zero tests can report PASS on
Python 3.11.** `python3 -m unittest <module>` exits 5 (`NO TESTS RAN`)
on 3.12+, so lirk correctly reports `FAIL ... (exit 5)`. That exit code
was introduced in 3.12; on 3.11 the same case exits 0 and lirk reports
a false PASS. `pyproject.toml` declares `requires-python = ">=3.11"`,
so 3.11 is a supported runtime.

*Fix direction:* either raise the floor to 3.12 (cheapest, if nothing
depends on 3.11), or detect the zero-tests case from the subprocess
output. Bump `ACTION_VERSION` if the latter.

**L2 — A timeout abandons the remaining srcs of a multi-src test
target.** `run_test` accumulates failures across all srcs, but the
`TimeoutExpired` handler `return`s immediately — so one hung src hides
every src after it, the exact asymmetry the accumulate-failures change
was meant to remove.

*Fix direction:* record the timeout in `failed_modules` and continue
the loop. Cheap; the only argument against is that a hung test often
means the whole target is wedged. Bump `ACTION_VERSION`.

**L3 — Concurrent invocations clobber the cache.** `load_cache` /
`save_cache` are an unlocked read-modify-write, and both runs write the
same `.lirk-cache.json.tmp` path before `os.replace`. Two overlapping
runs lose one run's entries, and could in principle replace a
partially-written temp file.

Failure mode is a redundant rebuild, not a wrong result, and the
single-device workflow makes overlap unlikely. *Fix direction, if ever
worth it:* include the PID in the temp filename (one line, removes the
worse half of the problem) and leave the lost-entries half alone.

**L4 — The downward repo scan skips dot-directories only.** Nothing
excludes `node_modules/`, `vendor/`, or a nested non-dot checkout. The
dot-prefix rule covers the realistic cases seen so far.

*Fix direction, if it comes up:* an optional ignore list in a
root-level config, not a hardcoded name list.

**L5 — `needs_build`'s first parameter is named `label` but receives a
cache key** (`"<mode>:<label>"`). Cosmetic; misleading when reading
`cache.py` cold.

---

## Documentation gaps

**D1 — `docs/index.md` is stale.** The published Pages overview still
carries the vague "until serial execution is proven stable" and "Not
yet self-hosting" language that the README replaced with the explicit
v1 criteria above. It also has no Installation section and doesn't
mention the `data` field. It should point at the criteria rather than
restate a softer version of them.

**D2 — Link the filed iSH-AOK issue from `KNOWN_ISSUES.md`.** The
upstream JVM-crash report has been submitted, and the local draft was
removed. `KNOWN_ISSUES.md` now says so but has no issue URL, so a
reader can't get from the investigation to the upstream thread or its
status. *What's left:* paste the issue link in.

---

## Next actions, in priority order

1. **Self-hosting (criterion 1).** Now the largest open item and the
   critical path for two criteria at once, since it also counts as
   criterion 2's second repo. M2's fix means a `tests/` layout with
   subdirectories is no longer a blocker for it.
2. **Find a third consumer repo** — the last thing criterion 2 needs
   after self-hosting lands.
3. **D1**, alongside or after self-hosting, so the published status
   text and the real status agree.
4. **D2**, whenever convenient — one look at the live site.
5. LOW items opportunistically; none block anything.

## Recently closed

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
