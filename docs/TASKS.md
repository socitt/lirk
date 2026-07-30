# lirk tasks

Current backlog. Check items off and edit in place as work happens —
this file reflects present reality, not history. Architecture context
lives in [DESIGN.md](DESIGN.md); do not restate it here.

**Before implementing anything**, read DESIGN.md §1. The process-model
constraints are not negotiable: no process group, no session, no pty,
no `shell=True`, no results-file step, no parallel execution. If a task
seems to require one, stop and report it rather than doing it.

Last verified against source: 91 tests, `python3 -m unittest discover
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

**Decision needed — this is a judgment call, not a task.** Pick one:

- **Find two more consumers.** Highest-value evidence, since a second
  and third repo is exactly what would surface assumptions baked in by
  a single consumer's conventions (flat package layouts, one
  `main_test.py` per game, `shared/` cross-package deps). Also the
  slowest.
- **Count self-hosting as the second repo.** lirk building itself is
  a genuinely different shape from a games monorepo — different
  dependency topology, different test style. Would leave one to find.
  Depends on criterion 1 landing first.
- **Revise the clause with a stated reason.** Defensible if lirk is
  only ever meant to serve one monorepo; the clause was written to
  guard against overfitting to one consumer, and if there is only ever
  going to be one consumer, that risk is hypothetical. Requires
  editing the README's criteria, which is why it needs your call
  rather than mine — these were deliberately made non-subjective.

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

**M1 — One missing source file aborts the entire repo-wide run.**
`cli.py:_execute`'s preflight loop checks `missing_files()` across
every target in scope, then `return`s if *any* target failed. So a
single stale filename in one package's `BUILD.lirk` prevents every
other, unrelated target in the repo from building or testing — while
the failed-dependency path right below it does the strictly better
thing (FAIL that target, SKIP only its dependents, proceed with the
rest). The abort exists for a real ordering reason (`compute_fingerprints`
would otherwise hit the missing file first, see DESIGN.md §3), but the
blast radius is wider than it needs to be.

*Fix direction:* fingerprint and execute only the targets whose files
are all present, marking the missing-file targets as failed so the
existing `failed` set skips their dependents naturally. The ordering
constraint is satisfied by excluding them from `order` before calling
`compute_fingerprints`, not by aborting.

*Acceptance:* a fixture repo where `//a` has a missing src and `//b` is
unrelated — `lirk build //...` reports `FAIL //a:...`, `built //b:...`,
and exits 1.

**M2 — Test srcs in a package subdirectory fail with an unexplained
`ModuleNotFoundError`.** `run_test` derives the module name as
`Path(src).stem` and runs `python3 -m unittest <stem>` with
`cwd=pkg_dir`. So `srcs = ["sub/test_helper.py"]` is valid in a
`library` target and broken in a `test` target — same path, same
package, opposite outcomes, with an error message that explains
nothing. Second consequence: two srcs with the same stem in different
subdirectories silently collide on one module name.

The failure is loud, which is why this is MEDIUM and not HIGH. It is
the piece most likely to strain the first time a consumer organizes a
target into subdirectories rather than flat files.

*Fix direction:* derive a dotted module path from the src path
relative to the package
(`Path(src).with_suffix("").as_posix().replace("/", ".")`) and confirm
it resolves under the existing `cwd`/`PYTHONPATH` model. Bump
`ACTION_VERSION` in the same commit — this changes what running a test
means. Alternatively, if it stays unsupported, reject a `test` target
whose `srcs` contain a path separator at parse time, so the error names
the actual problem.

*Acceptance:* a fixture with `sub/test_helper.py` in a `test` target
either runs correctly, or fails at parse time with a message naming the
subdirectory as the reason.

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

1. **Decide criterion 2's repo-count clause** (see above). It is the
   only thing standing between the track-record criterion and being
   met, and it's a call only you can make.
2. **M1**, then **M2**. Both are correctness-adjacent and both are
   contained to one function. Both change execution behavior, so both
   need `ACTION_VERSION` bumped in the same commit.
3. **Self-hosting (criterion 1).** The largest item, and the one that
   turns lirk from a tool that works into a tool that's proven. Worth
   doing after M1/M2 so it isn't fighting known rough edges — and it
   may also resolve criterion 2's second repo.
4. **D1**, alongside or after self-hosting, so the published status
   text and the real status agree.
5. **D2**, whenever convenient — one look at the live site.
6. LOW items opportunistically; none block anything.

## Recently closed

- **Suite was 90/91 on Windows** (2026-07-30). `validate_target`'s
  `read_text()` used the locale encoding, so cp1252 decoded the
  `binary_src_repo` fixture and it reached `ast.parse` as a null-byte
  `SyntaxError` rather than the intended `UnicodeDecodeError`. Pinned
  `encoding="utf-8"`; `ACTION_VERSION` 5 → 6. Now 91/91 on Windows.
- **`docs/design/target-format.md` deleted** (2026-07-30), duplicate of
  `docs/build-format.md`; `targets.py`'s docstring repointed.
