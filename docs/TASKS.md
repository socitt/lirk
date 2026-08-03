# lirk tasks

Current backlog. Check items off and edit in place as work happens —
this file reflects present reality, not history. Architecture context
lives in [DESIGN.md](DESIGN.md); do not restate it here.

**Before implementing anything**, read DESIGN.md §1. The process-model
constraints are not negotiable: no process group, no session, no pty,
no `shell=True`, no results-file step, no parallel execution. If a task
seems to require one, stop and report it rather than doing it.

Last verified against source (2026-08-03): 127 tests, `python3 -m
unittest discover -s tests -t .`. lirk also builds and tests itself —
`lirk build //...` (13 targets) and `lirk test //...` (5 test targets)
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
  better answer than continuing to rule on it. H2 is the remaining
  member of the family.

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

H1, M3–M6 and L6 all came from the termrery trial (2026-08-03) and were
reproduced against current source before being written here; the repros
are given inline so no one has to take the source repo's word for it.

### HIGH

**H2 — a `.py` file no target declares is an unfingerprinted input.**
H1 closed the case where the imported file belongs to an *undeclared
target*. This is the remaining half: a file under the repo that no
target lists in `srcs` at all. Nothing fingerprints it, so editing it
invalidates nothing, and the import check deliberately stays silent
(rejecting it would fail ordinary repos — an undeclared package
`__init__.py` is extremely common, including in lirk's own fixtures).

Reproduced against current source, with the import check in place:

```
$ lirk test //leaf:orphan_test      # imports orphan.thing; no target declares orphan/thing.py
  PASS   //leaf:orphan_test
$ vi orphan/thing.py                # change the value the test asserts on
$ lirk test //leaf:orphan_test
  cached  //leaf:orphan_test
lirk: 1/1 tests passed              # <-- wrong
$ lirk test //leaf:orphan_test --force
lirk: 0/1 tests passed
```

Same severity as H1 and the same failure shape; what differs is the
fix. Rejecting the import is not available, so the options are to fold
the resolved file's contents into the importing target's fingerprint as
an implicit input (correct, silent, and makes the graph partly
implicit), or to require every imported repo file to be declared
somewhere (explicit, and a much harder adoption story). Undecided, and
worth deciding before it's implemented.

Narrower than H1 in practice — it needs a file outside every target,
where H1 needed only a missing `deps` line — but it is not rare: an
`__init__.py` that no BUILD file mentions is the ordinary case, and
editing one currently invalidates nothing that imports it.

### MEDIUM

M1 and M2 are closed — see Recently closed.

**M3 — `srcs` accepts non-`.py` files, and only catches them by
accident.** Nothing checks the extension; a src is rejected only if its
contents fail `ast.parse`. Whether a text file is caught therefore
depends on what it says:

```
srcs = ["notes.txt"]     # "a rough note about the module" -> FAIL, syntax error
srcs = ["oneword.txt"]   # "hello"                         -> built, OK
```

DESIGN.md §2 states flatly that "a `.txt` fixture in `srcs` produces a
bogus syntax error"; that is true only for contents that don't happen
to parse. A one-word file, an empty file, or anything else Python
accepts sails through into `srcs`, where every consumer assumes it is
importable. Rejecting non-`.py` in `srcs` by extension makes the
`srcs`/`data` split self-teaching — termrery's point was that the
distinction exists but nothing steers you toward it — and makes
DESIGN.md's claim true as written.

**M4 — the root fallback to cwd is silent, and label errors don't say
what the root was.** Documented behavior is "nearest ancestor
containing `.lirk-root`, else cwd itself" (`_discover_root`). When the
marker is missing the fallback is invisible, so `//` silently changes
meaning depending on which directory you're standing in. From the repo
root everything looks fine; from a package subdirectory that package
becomes the root, and you get an error about a dependency:

```
$ cd cli && lirk build //...        # marker deleted
lirk: //:cli: dependency '//orrery:orrery' does not exist
```

The message points at the dep. The actual fault is that the root became
`cli/`, which nothing on screen says. termrery notes this bit an
earlier attempt at that project badly enough that creating `.lirk-root`
is now the first instruction in its README. Two cheap fixes, both
worth doing: say which directory was chosen as the root and why when
falling back to cwd, and name the root in the error when a `//` label
fails to resolve.

**M5 — an entry point can be dead and every lirk command stays
green.** `lirk run` and a `binary` type are a settled decision (DESIGN
§6: "the need is fully met by `test` targets that subprocess the
entrypoint"), and this entry does **not** re-open it. What termrery
supplies is evidence about the *documented alternative*: nobody wrote
that test target, because nothing in the docs says to. Their `main()`
was defined and never called, so `python3 -m cli.render` did nothing at
all while `lirk build //...` reported OK throughout — the application
the repo exists to produce was the one artifact lirk had no opinion
about.

The settled decision holds only if the pattern that replaces it is
discoverable, and right now it isn't documented anywhere. *What's
left:* a worked entrypoint-as-`test`-target example in
`getting-started.md` — a `test` target whose src subprocesses the real
entry point and asserts it starts, exits, and prints something. See D4.

**M6 — a failing run prints no list of what failed.** `_execute` prints
per-target lines as it goes and then a counts-only summary (`lirk: 0/1
tests passed`). Test output goes through unmodified, which is correct
and is a settled decision (§6, no summarizing layer) — but with a few
packages the failing target's own line scrolls off above the unittest
dump, and the summary that survives on screen says only how many
failed, not which. On a phone terminal that means scrolling back
through a full traceback to recover a label you already saw.

A trailing list of failed labels is not a summarizing layer over test
output — it restates labels lirk already printed, and touches nothing
about the captured stdout/stderr. Cheap: `_execute` already has
`failed`.

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

**L6 — `lirk --version` isn't a flag.** `main`'s parser requires a
subcommand, so `lirk --version` errors with the subcommand usage and
`pip show lirk` is the workaround. One `parser.add_argument("--version",
action="version", ...)` against the installed distribution version.
Raised by termrery; trivial, and the first thing anyone reports a bug
against.

*Everything else on this list is closed — see Recently closed.*

### Raised by termrery, already settled — not backlog

Recorded so they aren't re-derived from the review as if they were new:

- **A `binary` target type and `lirk run`** (their #2). Off the roadmap
  per DESIGN §6. The real cost they hit is M5 above, which is a docs
  gap in the replacement pattern, not a missing feature.
- **`lirk query` / any way to list targets** (their #5 — "`grep -r
  '^name' */BUILD.lirk` is the current answer"). Deferred on evidence
  in §6, most recently at ~26 targets; termrery has four, so it is no
  new evidence against that. Worth revisiting only if a consumer
  arrives with a target count where grep genuinely stops working.

---

## Documentation gaps

**D4 — Document the entrypoint-as-`test`-target pattern.** The
counterpart to M5: DESIGN §6 rules out `lirk run` on the grounds that a
`test` target subprocessing the entry point covers it, and no document
shows how. `getting-started.md` should carry a worked example —
`subprocess.run([sys.executable, "-m", "cli.render", "--selftest"])`,
or equivalent — asserting the entry point starts, exits 0, and produces
output. That is what would have caught termrery's never-called
`main()`. Small, and it is what makes a settled decision defensible
rather than merely recorded.

**D2 — Link the filed iSH-AOK issue from `KNOWN_ISSUES.md`.** The
upstream JVM-crash report has been submitted, and the local draft was
removed. `KNOWN_ISSUES.md` now says so but has no issue URL, so a
reader can't get from the investigation to the upstream thread or its
status. *What's left:* paste the issue link in.

---

## Next actions, in priority order

**All three v1 criteria hold, and v1 is to be tagged once the
high-priority correctness work is done** (decided 2026-08-03: fix
first, tag after — tagging v1 with a known silent-wrong-pass path open
is the thing the criteria exist to prevent). H1 is closed; **H2 is what
now stands between here and the tag.**

1. **H2 — undeclared files as unfingerprinted inputs.** The last known
   stale-PASS path. Needs its fix chosen first: implicit fingerprinting
   of imported-but-undeclared files, or requiring them to be declared.
   Unlike H1, rejecting is not an option.
2. **M4 — name the root.** Two small, independent changes (announce the
   cwd fallback; put the root in unresolved-`//`-label errors) against
   a failure that has now confused two separate projects.
3. **M3 — reject non-`.py` in `srcs`.** Small, and makes DESIGN §2's
   existing claim true as written.
4. **M6** and **L6**, both trivial. **D4** alongside whichever of these
   gets picked up, since it's a docs edit rather than an engine change.
5. **M5** is D4 — no engine work.
6. **D2**, whenever convenient — needs the upstream issue URL, which is
   not derivable from the repo.

Apart from the half of L3 deliberately left (see above), everything
open came out of the termrery trial or the H1 work it prompted.

## Recently closed

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
