# lirk tasks

Current backlog. Check items off and edit in place as work happens —
this file reflects present reality, not history. Architecture context
lives in [DESIGN.md](DESIGN.md); do not restate it here.

**Before implementing anything**, read DESIGN.md §1. The process-model
constraints are not negotiable: no process group, no session, no pty,
no `shell=True`, no results-file step, no parallel execution. If a task
seems to require one, stop and report it rather than doing it.

Last verified against source (2026-08-04): 143 tests, `python3 -m
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

**D2 — Link the filed iSH-AOK issue from `KNOWN_ISSUES.md`.** The
upstream JVM-crash report has been submitted, and the local draft was
removed. `KNOWN_ISSUES.md` now says so but has no issue URL, so a
reader can't get from the investigation to the upstream thread or its
status. *What's left:* paste the issue link in.

---

## Next actions, in priority order

**All three v1 criteria hold and the high-priority correctness work is
done, so v1 is ready to tag** (decided 2026-08-03: fix first, tag after
— tagging v1 with a known silent-wrong-pass path open is the thing the
criteria exist to prevent). H1 and H2 are both closed, and **no known
stale-PASS path remains open.**

The whole termrery-derived backlog is now closed too (M3–M6, L6, D4,
2026-08-04), so nothing is queued behind the tag either.

1. **Tag v1.** The only outstanding item. Needs one decision that isn't
   derivable from the repo: `pyproject.toml` still says `0.1.0`, and
   tagging v1 means bumping it — `1.0.0` is the obvious reading of "v1",
   but the criteria never fixed a number, so it is the author's call.
2. **D2**, whenever convenient — needs the upstream iSH-AOK issue URL,
   which is likewise not derivable from the repo.
3. **L7**, only if a real repo hits it. **L3**'s remaining half only if
   concurrent runs become a real workflow.

Both remaining items need input from outside the repo. Everything that
could be done from inside it is done.

## Recently closed

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
