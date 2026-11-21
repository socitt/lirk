# lirk assessment, from real usage (2026-07-27)

Written by an AI session working in a separate repo, `terminal-projects`
(a monorepo of small terminal games/tools, the reason `lirk` exists —
see `lirk`'s own README for that origin story). This file is a
standalone report for whoever picks up `lirk` next; it assumes no
knowledge of `terminal-projects` beyond what's explained inline.

**Originally left untracked** — written directly to disk, not
committed, for manual hand-off. Archived here as a permanent record
after its findings were reviewed and acted on; see Resolution below
for what happened to each item.

## Resolution (2026-07-27)

Reviewed with the user, prioritized together, then worked one item at
a time (small commits, tested, pushed):

- **Bugs (section 2):** none outstanding — the one failure found was a
  bug in the report's own test fixture, not in `lirk`. No action
  needed.
- **Suggestion 1 (`--force`/`--rebuild`):** done, `9b2e03f`.
- **Suggestion 2 (`--root` + upward marker discovery):** done,
  `fac0d0c`. Used a `.lirk-root` marker file (opt-in, falls back to
  today's cwd behavior if absent) rather than treating the nearest
  `BUILD.lirk` as the root marker, since a package's own `BUILD.lirk`
  isn't a reliable repo-root signal.
- **Suggestion 3 (`library` syntax validation):** done, `3658ff0`, via
  `ast.parse()` on each `srcs` file.
- **Suggestion 4 (`lirk run`):** deferred — matches the assessment's
  own effort/value ranking (medium effort, matters more once
  entrypoints outnumber the current 2).
- **Suggestion 5 (`.gitignore` docs):** done, `f519fd8`.
- **Suggestion 6 (`srcs` glob, `lirk query`, parallelism, remote
  caching, sandboxing):** deferred, per the assessment's own
  "not urgent yet" ranking — none were causing friction at the
  reported scale.

## Basis for this assessment

Four real targets, built and tested across multiple sessions, at
current commit `428c517` ("Fix lirk test failing on root-relative
imports"):

| Target | Type | Tests | Confirmed pass rate |
|---|---|---|---|
| `//shared:term_test` | test | 5 | 0/10 pre-fix (deterministic `ModuleNotFoundError`, see this repo's own `docs/KNOWN_ISSUES.md`) → 10/10 post-fix (this session) + 20/20 (reported from a `lirk`-repo session) = **30/30 since the fix** |
| `//shared:input_test` | test | 8 | 10/10 |
| `//board-games/tictactoe:board_test` | test | 16 | 10/10 |
| `//board-games/connect4:board_test` | test | 19 | 0/10 (a bug in *my own test fixture*, not `lirk` — see Bugs section) → 10/10 after fixing the test |

All test-target batches: fresh shell process per attempt, `.lirk-cache.json`
deleted before *every single run* (not just once) to force real
re-execution rather than a cached result — the same rigor the
Please/SIGHUP saga in `terminal-projects` demanded, after a prior false
lead there turned out to be a cache hit mistaken for a fix.

Total fresh-shell `lirk test` invocations across this dogfooding effort:
**60**, plus one full run of `lirk`'s own suite (**42/42**, confirmed
directly by me just now, not just taken on faith from `docs/KNOWN_ISSUES.md`).
Also ran `lirk build //...` repeatedly as the target count grew (3 → 7 → 10
targets across `shared/`, `board-games/tictactoe/`, `board-games/connect4/`),
always clean.

---

## 1. What works well (with evidence)

**Zero flaky results across 60 fresh-shell test invocations.** Every
pass and every fail was 100% deterministic and fully explained by an
identifiable cause (a real `lirk` bug, a real bug in my own test code,
or genuinely correct code) — never a "sometimes passes, sometimes
doesn't for no clear reason" result. That's the entire reason this
tool exists, and on the evidence so far, it's actually delivering:
Please never returned a single clean `plz test` exit code on
`shared:term_test` across ~45+ attempts in `terminal-projects`; `lirk`
is 30/30 on the exact same target since its own bug got fixed.

**Cross-package dependency resolution just worked.** `board-games/tictactoe:main`
and `board-games/connect4:main` both depend on `//shared:term` and
`//shared:input` — the first cross-package deps exercised in real
usage (all prior targets were single-package). No friction, no special
handling needed, correct topological build order both times, first
try.

**Failure output is raw and immediately diagnosable.** Every failure I
hit in practice — the original `ModuleNotFoundError` traceback before
the fix, and a broken assertion in my own `connect4` test — was
understandable at a glance from the dumped stdout/stderr, with no need
to dig into `lirk`'s internals to figure out what went wrong. Not
adding a custom wrapper/interpretation layer around test output turned
out to be a real strength in practice, not just a minimization choice.

**Compact, narrow-terminal-appropriate CLI output.** `  built  //shared:term`
/ `  PASS   //board-games/connect4:board_test` — short, fixed-width
verb column, no wasted horizontal space. (Caveat: I can't directly
confirm how this renders on the actual iPhone/iSH-AOK device — my own
tool access is a normal-width terminal — but the format is clearly
designed for it and reads cleanly here.)

**Fast.** Full `lirk build //...` over 10 targets and a `lirk test` of
any individual target both return in well under a second in normal
use (excluding the deliberate cache-clearing I did for verification
rigor). No process-spawn-per-target overhead complaints.

---

## 2. Bugs found during real usage since the PYTHONPATH fix

**The `connect4` test failure was a bug in my test fixture, not in
`lirk`.** Worth being precise about this since the prompt that led to
this report specifically asked me to distinguish the two. My
`is_draw`-with-a-winner test filled the entire board with `"O"`, then
overwrote 4 cells with `"X"` to form a win, and asserted
`winner(board) == "X"`. But a full board of `"O"` also contains
several full-length `"O"` runs (entire rows, since the board is 7
columns wide), and `board.py`'s `winner()` scans row-major and returns
the *first* four-in-a-row it finds — which was an `"O"` run, not my
`"X"` line. `lirk` reported this exactly correctly: a genuine,
deterministic, reproducible test failure (0/10, same assertion error
every time), with the real Python traceback showing exactly which line
and what values disagreed. There is no `lirk` bug here — this is
`lirk` working as intended and catching a real mistake. I'm flagging
it mainly because it's useful proof that `lirk`'s test-failure path is
trustworthy under real (not synthetic) conditions: it didn't mask,
misattribute, or intermittently swallow the failure. Fixed by not
asserting *which* mark wins in that specific test (already covered by
dedicated win-direction tests); 10/10 after the fix.

**No other `lirk`-side bugs found.** Everything else below is
usability/gaps, not incorrect behavior.

---

## 3. Usability / developer experience friction

**Repo-root discovery is fragile — this is the sharpest edge I found.**
`lirk`'s `root` defaults to `Path.cwd()` (`cli.py`, `main()`), and
`build_graph`/`find_build_files` only searches *downward* from `root`
(`root.rglob(BUILD_FILENAME)` in `graph.py`) — there's no upward search
for a repo-root marker (no `WORKSPACE`-file equivalent), and no `--root`
CLI flag to override it. I always invoked `lirk` from the
`terminal-projects` repo root as a matter of discipline (`../lirk/bin/lirk
test //shared:term_test`), so I never actually broke on this — but two
related traps are sitting there for whoever hits them next:
  - The `bin/lirk` path itself is relative and depth-dependent: `../lirk/bin/lirk`
    only works from the repo root; a game two directories deeper (e.g.
    `adventure-engine/stories/dungeon/`) would need `../../../lirk/bin/lirk`
    instead, and it's easy to get that wrong, especially typing on an iOS
    on-screen keyboard where retyping a long relative path is real friction.
  - Even if the binary invocation is right, running `lirk` from inside
    a subdirectory silently scopes `root` to that subtree instead of
    erroring — e.g. running from `board-games/tictactoe/` would mean
    `//shared:term` is invisible (never scanned), and the dependency
    would fail with "does not exist" rather than lirk explaining *why*
    it can't see it. I never actually hit this error message, so I
    can't report exactly how confusing/clear it is — flagging it as an
    untested edge, not a confirmed complaint.

**No way to force a clean run without manually deleting the cache
file.** Every verification batch in this dogfooding effort required
`rm -f .lirk-cache.json` before *each* run to guarantee a real
re-execution rather than a cache hit. There's no `--rebuild`/`--rerun`/
`--force` flag (Please has `--rebuild` for build and `--rerun` for
test). This matters more than it might look like: the entire reason
this rigor exists is a documented incident in `terminal-projects` where
a "fix" was believed real because of a cache hit, and was actually
never re-tested. `lirk` has no built-in guard against that same
category of mistake — it only didn't happen here because I manually
remembered to delete the cache file every time.

**`main.py` entrypoints are validated only by file-existence, never
actually exercised by `lirk`.** Both `tictactoe/main.py` and
`connect4/main.py` are declared as `type = "library"` purely so `lirk
build` confirms the file exists — `validate_target` (`actions.py`)
never imports it, parses it, or runs it, and `library` targets have no
test-equivalent. I manually ran each entrypoint outside `lirk`
(`printf '1\n2\n...' | python3 board-games/tictactoe/main.py`, piped
input, verified the win output) to actually confirm they work. `lirk`
itself would report "built" (success) even if `main.py` had a syntax
error, since nothing ever imports it. This is the one gap in this
list I'd call *concretely felt*, not theoretical — it happened
identically on both games so far, and will happen again on every game
after this unless something changes (see Suggestions).

**Caching's "skip unchanged" path was never actually observed firing
in this dogfooding effort.** Every real invocation I made deliberately
cleared the cache first, specifically to avoid the false-positive trap
described above — so while I trust the cache logic (read `cache.py`,
and `lirk`'s own `test_cache.py`/`test_cli.py` cover it, e.g.
`test_second_build_hits_cache`, `test_second_run_skips_unchanged_passing_test`),
I have zero *end-to-end dogfooding* evidence of a `cached` line
actually printing during routine (non-verification) use. Worth someone
running a normal, non-adversarial `lirk build //...` twice in a row
without touching the cache file, just to see it in the wild.

**`lirk test //...` (all test targets at once) has never actually been
exercised by me.** I always ran individual test labels
(`//shared:term_test`, `//board-games/connect4:board_test`, etc.) — never
the whole-repo form, even though that's the form that will matter most
as the target count grows past a handful. Not a bug, just an untested
workflow gap in this report's own coverage.

**`lirk`'s own test suite is slow relative to its size:** 42 tests, 31
seconds, on this device. Not something I felt as a `terminal-projects`
user (I only run 1-19-test targets, seconds each), but if `lirk` is
being iterated on directly, that's worth knowing — some `test_cli.py`/
`test_actions.py` tests spawn real `python3 -m unittest` subprocesses
rather than mocking them, which is consistent with the project's
"trust real `subprocess.run()`, no shortcuts" philosophy, but likely
means each subprocess-spawning test pays a full interpreter-startup
cost under iSH-AOK's aarch64 emulation. Not asking for this to change
(mocking it would undercut exactly the thing this tool is trying to
prove about itself) — just flagging the wall-clock cost as real.

---

## 4. Gaps: felt vs. theoretical

Cross-referencing the README's explicitly-deferred v1 scope:

- **More target types (binary/genrule-equivalent): felt, concretely.**
  See the `main.py`-validation gap above — this is the one deferred
  scope item that has already caused a real coverage hole across both
  games built so far, not a hypothetical future need.
- **`srcs` glob support:** not yet felt — every target so far has
  exactly one source file. Will likely start mattering once a module
  splits into multiple files (a `chess` implementation seems likely to
  outgrow one file). Flagging as "coming soon," not urgent yet.
- **Parallelism:** purely theoretical so far. 10 targets, sub-second
  serial builds — nowhere near a scale where this would be felt.
- **Remote caching:** purely theoretical. Single device, single user,
  no CI, no second machine in the picture.
- **Sandboxing/process isolation:** purely theoretical. Never
  encountered a case where an action needed isolating from the local
  filesystem.
- **`lirk query` / dependency introspection:** not felt yet — every
  graph so far has been small enough (2-4 nodes) to reason about by
  reading `BUILD.lirk` files directly. Would likely start mattering
  once `shared/` has more consumers and "what depends on `//shared:term`"
  stops being obvious at a glance.
- **`--root` / repo-root discovery:** not in the README's original
  deferred-scope list at all, but based on real usage, this is the gap
  I'd actually prioritize over most of the explicitly-deferred ones
  above — see Suggestions.

---

## 5. Concrete suggestions, ranked by value vs. effort

Aimed at what would help the next 4-5 real targets (backgammon, go,
chess, adventure-engine) most, not speculative future-proofing.

1. **Add a `--force`/`--rebuild` flag that bypasses the cache for a
   single invocation, without deleting the cache file.** Low effort
   (a CLI flag that skips the `needs_build` check), directly closes
   the "had to manually `rm .lirk-cache.json` every time" friction,
   and removes a real footgun (forgetting to clear the cache and
   silently trusting a stale pass). High value for the amount of code
   this is.

2. **Add repo-root discovery: walk upward from `cwd` for a marker file
   (e.g. the first `BUILD.lirk` found ancestor-wise, or a dedicated
   marker like `.lirk-root`), and/or add an explicit `--root` flag.**
   Medium effort, but this is the sharpest edge found in this report —
   currently silent/wrong-scope rather than clearly-erroring when
   invoked from the wrong directory, and the deeper `terminal-projects`
   gets (more subdirectories, e.g. `adventure-engine/stories/*`), the
   more likely this is to actually bite someone typing on an iOS
   keyboard who gets a relative path wrong.

3. **Give `library` targets at least optional syntax validation** (e.g.
   `py_compile.compile()` or `ast.parse()` on each `srcs` file during
   `lirk build`, catching syntax errors without needing a full test
   suite). Low-to-medium effort, directly closes the "a broken
   `main.py` reports as `built` successfully" gap that's already been
   real (if latent — no actual syntax errors shipped, but nothing
   would have caught one) across both games so far. Doesn't require
   inventing a new target type yet — just makes `library` validation
   less trivially a no-op.

4. **Consider a minimal `binary`/`run` capability** — even just
   `lirk run //path:target` that executes a designated entrypoint file
   directly (no build-graph implications beyond what `library` already
   has), so entrypoints like `main.py` get *something* closer to
   first-class treatment than "declared but never touched by the
   tool." Medium effort, matters more as the number of playable
   entrypoints grows past 2.

5. **Document (README or a short doc) the recommended `.gitignore`
   entries for a repo consuming `lirk`** (`.lirk-cache.json`,
   `__pycache__/`, `*.pyc`) — I had to figure this out and add it to
   `terminal-projects/.gitignore` myself. Trivial effort, saves the
   next consuming repo a small but avoidable step.

6. **Lower priority / not urgent yet:** `srcs` glob support, `lirk
   query`, parallelism. All real eventually based on the trajectory of
   this repo (more targets, more files per module), but none of them
   are causing friction today at 10 targets — I'd rank all three below
   items 1-5 above for now.
