# lirk dogfooding notes: board-games/chess (2026-07-27)

## Resolution (2026-07-28)

Picked up per the hand-off convention. No bugs found in this file, so
per the precedent set by the two prior assessments (see
`docs/assessments/2026-07-26-assessment.md` and
`2026-07-27-post-go-assessment.md`) this is archived here rather than
folded into `KNOWN_ISSUES.md`, which tracks unresolved problems, not
closed-clean usage reports.

**The one open item — the flat ~2.7-3.2s per-test-invocation
overhead flagged below as "worth a lirk-side profiling pass" — was
investigated.** Root cause: it's the cost of the `lirk` CLI process
itself cold-starting, not the test subprocess or anything in the
target/cache graph.

Measured against `tests/fixtures/sample_repo` (1 trivial test, 3
targets), isolating each layer:

- `python3 -c "pass"`: 0.50s — this sandbox's own baseline process-
  start cost is already high (same category of slow-syscall
  environment noted in this file's own aside about untrustworthy
  `time` output, and the reason lirk's process model exists at all —
  see the README's origin story).
- `python3 -m unittest <one test>` standalone: 1.85s.
- `lirk test //a:a_test` **fully cached** (`needs_build` returns
  False for every target, zero `subprocess.run` calls made for any
  test): **2.70s** — this alone accounts for almost the entire
  reported "flat overhead," with no test actually executed.
- `python3 -c "import lirk.cli"` alone: 2.56s, confirmed via
  `python3 -X importtime` to be dominated by stdlib import chains
  pulled in at module load: `argparse` → `re`/`enum`/`functools`
  (~520ms), `dataclasses` → `inspect`/`ast`/`dis` (~450ms),
  `lirk.targets` → `tomllib` (~355ms, mostly regex compilation in
  `tomllib._parser`), `subprocess` → `typing` (~145ms), `pathlib` →
  `urllib.parse`/`ipaddress` (~170ms).

So the ~2.7-3.2s is CPython's own import-time tax for an
"argparse + dataclasses + tomllib + subprocess" CLI, paid once per
process, made disproportionately visible by a host environment that's
already slow at process/import machinery generally — not something
that scales with test count (matches "flat regardless of suite size"
exactly) and not caused by lirk's subprocess-per-test model or its
graph/cache layers.

**No code change made.** The only ways to meaningfully cut this
further are dropping `dataclasses`/`argparse` for hand-rolled
equivalents, which trades stdlib clarity for marginal per-invocation
savings — against this project's own v1 priority ("prove the core
approach works... before expanding scope") and not blocking any
consumer, per this file's own closing line below. Leaving as an
understood, explained characteristic rather than open work.

---

Running log of real lirk usage from the consumer side (terminal-projects
repo) while building chess — the most rule-complex target exercised
against lirk so far (5 games in, but chess's move-generation/legality
surface is bigger than tictactoe/connect4/backgammon/go combined).
Append-only; not rewritten. Leaving this uncommitted in the lirk repo
per the established hand-off convention — a lirk session will pick it
up later.

Context for whoever reads this cold: terminal-projects is consuming
lirk at HEAD as of this session (`9611760`, "Close out the
review-driven work in the session log") — post architecture-review,
18 follow-up hardening commits landed since the last time this repo
used it (`428c517`).

## Post-review regression check against the existing graph

Before touching chess, re-verified the *existing* 20 targets (shared/,
tictactoe/, connect4/, backgammon/, go/) still build and test clean
against the updated lirk, since 18 commits landed since this repo last
pulled and several looked like they could plausibly change observable
behavior for existing BUILD.lirk files:

- "Reject unknown keys in `[[target]]`" — could have broken any
  existing BUILD.lirk with a stray/legacy key. It didn't; none of the
  5 games' BUILD.lirk files hit this.
- "Reject a test target with no srcs" — same, no existing target hits
  this (all test targets have srcs).
- "Run all srcs of a test target, don't stop at the first failure",
  "Pass stdin=DEVNULL to test subprocesses", "Add a timeout to test
  subprocesses" — behavioral changes to `lirk test`'s subprocess model.
  Worth watching for the backgammon `main_test` in particular (it's the
  one target already known to run long — ~9-12s through lirk's nested-
  subprocess overhead per the session log) in case the new timeout is
  tight enough to matter. Not observed to be a problem: full `lirk test
  //...` batch completed normally, no timeout-related failures.

Result: `rm -f .lirk-cache.json && lirk build //...` → 20/20 built,
clean. `lirk test //...` → 10/10 tests passed, run 3x fresh-shell
(cache cleared each time) — no regressions from the hardening work.
Good sign that the 18 fixes were genuinely additive/defensive rather
than changing behavior existing consumers depend on.

## Next entries to add as chess work progresses

Watching for, specifically because chess is more complex than anything
tried so far:

- Whether `board_test.py`'s 55 tests (biggest single test file by a
  wide margin — connect4's was 19, go's 31, backgammon's 60 is close)
  run notably slower through `lirk test`'s subprocess model, and if so
  whether the new test-subprocess timeout (one of the 18 fixes) is
  comfortably clear of that or worth flagging.
- Cross-package dependency behavior once `chess/BUILD.lirk` is added
  (`//shared:term`, `//shared:input` deps) — same shape as the other
  4 games, so mainly confirming it stays boring.
- `main_test.py` for chess will need a scripted game reaching a clean
  outcome via piped stdin, same pattern as the other 4 games' subprocess-
  based integration tests — noting here only if lirk's stdin/timeout
  handling interacts with it in any surprising way.

## Chess complete: all 4 targets green, full graph clean

`board_test.py` (55 tests) and `main_test.py` (2 subprocess-based
integration tests) both wired into `chess/BUILD.lirk` with the same
`board`/`board_test`/`main`/`main_test` shape as the other 4 games, plus
the same `//shared:term`/`//shared:input` cross-package deps `main`
already exercises elsewhere. `lirk test //board-games/chess:board_test`
and `:main_test`: **10/10** fresh-shell, cache-cleared runs each,
no flakiness. `lirk build //...`: 24/24 targets across the whole repo
build clean. `lirk test //...`: 12/12 tests pass. No new timeout issues
despite chess having the largest single test file in the repo (55
tests) — comfortably clear of whatever the new test-subprocess timeout
is set to.

**Concrete overhead number, since it came up as a watch-item above:**
wall-clock `time` comparison, single fresh invocation each (`real` only
— this environment's `user`/`sys` numbers reported by `time` are
suspiciously identical across unrelated commands, almost certainly
reporting container-wide cumulative CPU rather than per-process, so
not trustworthy here and not worth chasing):

- `board_test` (55 tests): 0.22s python-internal (`unittest` itself),
  1.65s standalone (`python3 -m unittest`) wall, **4.82s** through
  `lirk test`.
- `main_test` (2 subprocess-spawning integration tests, ~1.87s of real
  work): 3.68s standalone wall, **6.36s** through `lirk test`.

So lirk's overhead here is roughly a flat ~2.7-3.2s per test-target
invocation regardless of the underlying suite's own runtime — consistent
with the backgammon `main_test` note from the prior session (~9-12s
through lirk vs ~2-4s standalone, there attributed to "nested-subprocess
overhead"). This is now confirmed across two different targets/sessions
as a repeatable, flat per-invocation cost rather than something that
scales with test count — worth a lirk-side profiling pass at some point
(where is the ~3s going — process spawn, results-file I/O, cache
lookup?) but not a correctness problem and not something blocking any
consumer so far. Flagging it here mainly so a lirk session has two
independent data points instead of one anecdote.

## Overall assessment building the most complex target so far

Nothing about chess's complexity (55 rule-coverage tests, 8x8 stateful
board, cross-package deps, algebraic-notation I/O) stressed lirk's
model in any new way. The dependency graph, incremental caching, and
test-running model all handled it exactly like the simpler 4 games —
the only new thing surfaced was the flat-overhead-per-invocation
pattern above, and that was already visible (just less clearly
isolated) in backgammon. No workarounds needed, nothing broke, nothing
confusing. The `PYTHONPATH` root-relative-import fix from the last
session's dogfooding remains solid — every cross-package import in
`chess/main.py` (`from shared import term`) and `chess/board_test.py`
(`from board import ...`) worked on the first try with no special
handling needed on this repo's side.
