# lirk assessment, from real usage (2026-07-27, follow-up)

Written by an AI session working in `terminal-projects` (the monorepo
this tool exists to serve — see `lirk`'s own README for that origin
story). This is a follow-up to the assessment already archived at
`docs/assessments/2026-07-26-assessment.md`: that one was reviewed,
acted on, and archived as a resolved record. This file picks up from
there and does **not** repeat its content — read that one first if
you haven't, since this assumes it as background. Like its
predecessor, this is standalone-readable by a session with no
`terminal-projects` context beyond what's explained inline.

**Originally left untracked** — written directly to disk, not
committed, for manual hand-off, same convention as its predecessor.
Archived here as a permanent record after its findings were reviewed
and acted on; see Resolution below for what happened to each item.

## Resolution (2026-07-27)

Reviewed with the user, prioritized together, then worked one item at
a time (small commits, tested, pushed):

- **Bugs (section 2):** none outstanding — both incidents noted (the
  `go` territory-scoring test-fixture bug, the mutation-testing
  exercise) were already resolved or were never `lirk`-side issues to
  begin with. No action needed.
- **Suggestion 1 (verify multi-file `library`/`test` targets before
  building `srcs` glob syntax):** verified, `c43a787` — **no code
  change needed**. Built a chess-shaped scratch repo exercising both
  patterns this assessment called out (a multi-`srcs` library target,
  and single-file targets chained via `deps` including a target with
  multiple deps and a cross-package dep). 12+ clean runs, correct
  results and correct caching behavior every time. The `srcs` glob
  suggestion is dropped per this assessment's own framing ("if it
  works, the glob suggestion can likely be dropped entirely").
- **Suggestion 2 (one-line pass/fail summary):** done, `6365c18`.
  `lirk build` now prints `N built, M cached, K failed`; `lirk test`
  prints `P/T tests passed`, scoped to test-type targets only so a
  test target's library deps don't inflate the denominator.
- **Suggestion 3 (relay the `--force` documentation-sync gap):**
  explicitly skipped at the user's direction — not a `lirk`-side
  issue, per this assessment's own framing ("not asking `lirk` to
  solve this").
- **Suggestion 4 (drop `lirk run` from the roadmap):** checked,
  `d5a7b25` — there was nothing to remove it from. Searched
  `README.md`, `docs/KNOWN_ISSUES.md`, `docs/design/`, and `cli.py`'s
  argparse setup: no `run` subcommand stub and no live doc ever
  tracked it as planned work. It only ever existed as a proposal
  inside assessment documents (this one and its now-archived
  predecessor), which is where it stays.
- **Suggestion 5 (parallelism / remote caching / sandboxing /
  `lirk query`):** deferred, per this assessment's own "still not
  urgent" reaffirmation at 2x the prior target count. No action taken.

## Recap: what the last assessment led to

Of its 6 suggestions: 4 done (`--force`/`--rebuild`/`--rerun` flag,
`--root` + upward `.lirk-root` marker discovery, `library`/`test`
source syntax validation via `ast.parse()`, `.gitignore` docs), 2
deferred (`lirk run`, and the lower-priority bundle of `srcs` glob /
`lirk query` / parallelism / remote caching / sandboxing). This
follow-up re-examines those decisions in light of real subsequent
usage, not just in the abstract.

## Basis for this assessment

Since the last pass, `terminal-projects` built two more full game
targets from scratch (`backgammon`, `go` — each meaningfully more
rule-complex than `tictactoe`/`connect4`), and retrofitted a new kind
of test target (`main_test.py`, end-to-end/subprocess-based) onto
**all four** games, including the two already-shipped ones. The repo
grew from 10 targets (end of last assessment) to **20 targets** across
5 `BUILD.lirk` files, all still resolving cleanly under `lirk build
//...`.

| Target | Type | Tests | Confirmed pass rate |
|---|---|---|---|
| `//board-games/backgammon:board_test` | test | 60 | 10/10 fresh-shell, cache cleared each run |
| `//board-games/backgammon:main_test` | test | 1 (full-game smoke) | 16+ fresh runs, genuinely different random dice each time, 0 failures |
| `//board-games/go:board_test` | test | 31 | 10/10 fresh-shell, cache cleared each run |
| `//board-games/go:main_test` | test | 2 | 10/10 fresh-shell, cache cleared each run |
| `//board-games/tictactoe:main_test` | test | 2 | 10/10 fresh-shell, cache cleared each run |
| `//board-games/connect4:main_test` | test | 2 | 10/10 fresh-shell, cache cleared each run |
| `//board-games/tictactoe:board_test`, `//board-games/connect4:board_test` | test | 16, 19 | already 10/10 as of last assessment; still 10/10, re-run this session as part of `lirk test //...` |

New this session, both closing gaps the last assessment explicitly
flagged as untested:

- **`lirk test //...` (whole-repo test form), run for the first time.**
  All 10 test targets (8 game tests + `shared`'s 2), one command,
  clean pass. Timed at **~42s wall-clock** for a full cache-cleared
  run (`time` wrapper; see the CPU-time caveat below on why only the
  wall-clock number is trustworthy). The prior assessment's "both
  [build and test] return in well under a second" claim is now
  **stale** — that was true before `backgammon:main_test` existed
  (a genuine ~2500-line piped-input full-game run); it's no longer
  true for the whole-repo form, though 42s for 10 test targets is
  still entirely reasonable, not yet a real problem (see Suggestions).
- **Caching's "skip unchanged" path, observed firing in the wild.**
  Ran `lirk test //board-games/go:board_test` twice back-to-back with
  no cache-clearing in between: second run printed `cached` for both
  `:board` and `:board_test`, as expected. Also happened
  incidentally, repeatedly, during normal multi-target work this
  session (e.g. `cached //shared:term` / `cached //shared:input` when
  building a second game's `:main` target right after a first one).
  Trust in the cache logic is no longer purely code-reading-based.
- **`--force`/`--rerun` on `lirk test`, verified directly, works
  exactly as designed** — `lirk test <target> --force` bypasses the
  cache and re-runs even with a fresh unchanged cache present; a
  plain call right after correctly shows `cached`. See Bugs/Usability
  below for a more interesting finding about this flag: it was built
  correctly but never actually *used* this session, for a reason
  worth knowing about.

---

## 1. What's been built since last assessment (with what each one exercised in `lirk`)

**`backgammon`** — largest state and rule surface so far. State is a
dict (`points`/`bar`/`off`), not a flat list like the earlier games;
60 tests is by far the largest `board_test.py` in the repo. This
didn't touch `lirk` differently in any structural way (still
`library`/`test`/`deps` — state shape and complexity are invisible to
`lirk`, which only ever does file-existence + `ast.parse()` for
`library` and one `python3 -m unittest <module>` subprocess for
`test`), but it's a good stress test of "does test *count* within one
module cost anything extra" — see the positive finding under
Usability.

**`go`** — largest board (9x9 = 81 cells vs. tic-tac-toe's 9 or
Connect Four's 42) and the most algorithmically involved logic yet
(flood-fill group/liberty tracking, capture resolution, ko position
comparison via full-board equality checks). Same story: `lirk` itself
was completely unaffected by the bigger state — it's a pure Python
concern, invisible at the `BUILD.lirk` level.

**`main_test.py` retrofit across all four games** — this is the
actually-`lirk`-relevant new thing this session. The prior assessment
flagged, as its most *concretely felt* (not theoretical) gap: `lirk`
validates `library` targets like `main.py` only by file-existence +
syntax, never by actually running them, so a broken entrypoint would
still report `built`. Rather than waiting on the deferred `lirk run`
suggestion, this session closed that gap **using tools `lirk` already
has**: a `main_test.py` per game, `type = "test"`, that runs the real
`main.py` as a `subprocess.run()` with piped stdin (same as a player
typing), asserting on stdout content and exit code. Wired in as a
normal `main_test` target (`deps = [":main"]`) in each `BUILD.lirk` —
zero new `lirk` functionality needed. **This is the single most
important finding in this report for prioritization purposes** — see
Suggestion 4.

---

## 2. Bugs found since last assessment

**No new `lirk`-side bugs found.** Same conclusion as the last
assessment's "one failure found was a bug in my own test fixture, not
`lirk`" — reconfirmed on a second, more complex sample.

**One test-fixture bug, same category as the connect4 one, this time
in `go`'s territory-scoring test.** Caught by direct `python3 -m
unittest board_test` *before* `lirk` was ever invoked on it (this
session's discipline: run tests directly first, wire into
`BUILD.lirk` only after a clean local pass) — so, unlike the connect4
case, this one isn't itself evidence of `lirk`'s failure-reporting
path, since `lirk` wasn't touched yet when it was caught. Noting it
mainly for completeness and because it reinforces the same lesson:
the first version of the test only placed black stones on the board,
so the *entire* rest of the empty board legitimately counted as black
territory (correct scoring-engine behavior — one giant connected
empty region touching only black), not the small isolated pocket the
test meant to check. Fixed by adding a distant white stone so the
giant remainder read as neutral instead. Not a `lirk` concern at all,
just logged for the "were there bugs" record.

**A deliberate mutation-testing exercise this session (not a bug
report, but relevant here) further stress-tested `lirk`'s
failure-reporting path.** 4 real rules were broken on purpose, one at
a time, in `go`/`backgammon`'s `board.py` (ko check disabled,
captures disabled, bear-off overshoot rule disabled, blocking rule
weakened), each run through `python3 -m unittest` directly (not
through `lirk`, since this was a `terminal-projects`-side exercise,
not a `lirk` dogfooding one) — all 4 caught, all reverted cleanly. Not
`lirk` evidence directly, but zero surprises or misleading output at
any point across the roughly 150+ total `lirk`/`unittest` invocations
this session (mutation exercise + normal development + verification
batches combined), consistent with the prior assessment's "zero flaky
results" finding holding up under a much larger sample.

---

## 3. Feature requests (concrete, tied to what surfaced this session)

**1. Multi-file targets: probably not actually a gap — verify once,
for real, before building glob syntax.** The prior assessment flagged
`srcs` glob support as "not yet felt... will likely start mattering
once a module splits into multiple files (a `chess` implementation
seems likely to outgrow one file)." Re-reading `lirk/targets.py` and
`lirk/actions.py` this session: `srcs` is *already* an arbitrary list
of strings (`_string_list`), and both `validate_target` and
`run_test` already loop over every entry in `target.srcs`
individually (`run_test` even runs `python3 -m unittest <module>`
**once per src file**, not one combined discovery run). That means
`srcs = ["board.py", "pieces.py", "moves.py"]` on one `library`
target, or splitting into several single-file targets connected by
`deps` (the existing convention every game already uses), both look
like they should already work with zero new `lirk` code — I did not
get to verify this empirically this session (didn't want to touch
`terminal-projects` for an unrelated probe, and chess — the actual
place this would get exercised — hasn't started yet), so treat this
as "very likely, based on reading the code, not yet proven in
anger." **Concrete ask: the next session that starts `chess` should
just try a multi-file `library` target (or multiple targets +
`deps`) directly, before anyone spends effort on glob syntax.** If it
turns out something doesn't work, that's a real, precisely-scoped bug
report; if it works, the glob suggestion can likely be dropped
entirely rather than just deprioritized.

**2. A one-line pass/fail summary on `lirk test //...` (and
plausibly `lirk build //...`).** Running the whole-repo test form for
the first time this session, the output is a flat, unlabeled stream
of `built`/`PASS`/`cached` lines (21 lines for 10 test targets +
their library deps) ending in a bare `lirk: OK` — correct, but
requires eyeballing every line to confirm nothing silently failed,
rather than a summary like `10/10 tests passed` or `18 built, 2
cached, 0 failed`. Low effort, directly felt the first time this
form was actually used at today's scale, and `chess` will push the
test-target count from 8 to roughly 12 (its own `board_test`/
`main_test`, following the now-established pattern), making this
more relevant, not less.

**3. Not a `lirk` code change, but worth relaying: the `--force`
flag shipped last time was never actually used this session.**
Every single fresh-run verification batch this session (backgammon
board_test x10, go board_test x10, all four `main_test` targets x10
each, the mutation-testing setup) used the *old* manual `rm -f
.lirk-cache.json` pattern, despite `lirk test --force`/`--rerun`
doing exactly that, more safely, since `9b2e03f`. Root cause: the
consuming repo's own `docs/ACTIVE_SESSION.md` working-rules section
(the crash-resilience doc this session reads first every time) still
describes the manual `rm`-the-cache-file pattern from before the flag
existed, and was never updated after `lirk` shipped the fix it was
asking for. This isn't a `lirk` bug and probably isn't a `lirk` fix
either — it's a downstream documentation-sync gap — but it's worth
knowing that shipping the right feature doesn't automatically mean
consuming sessions discover and use it, especially crash-resilient
ones that re-read a stale doc fresh every time rather than
accumulating institutional memory. (Flagging for whoever owns
`terminal-projects`' docs next, not asking `lirk` to solve this.) If
`lirk` wants to do anything at all here, the lowest-risk option would
be something like a one-time startup hint the first time `.lirk-cache.json`
is manually deleted while `--force` exists — but this is a genuine
judgment call about whether that's helpful or noisy, not a strong
recommendation either way.

**4. `lirk run` — downgrade further, maybe drop.** Last assessment
ranked this "medium effort, matters more once entrypoints outnumber
the current 2." There are now 4 entrypoints, and the gap it was meant
to close (unvalidated `main.py` files) has been fully closed without
it — see section 1's `main_test.py` writeup. Unless a genuinely new
need shows up that a `test`-type target subprocessing the entrypoint
can't cover (e.g. wanting actual interactive play mediated through
`lirk` itself, which seems out of scope for a build tool rather than
a missing feature), I'd take this off the roadmap rather than just
deprioritize it again.

---

## 4. Usability notes

**Positive, newly confirmed this session: per-module test count is
free.** `lirk`'s test action pays subprocess-spawn overhead once per
**target** (one `python3 -m unittest <module>` call), not once per
**test method**. Backgammon's 60-test `board_test.py` ran in the same
sub-0.2s ballpark as `go`'s 31 or `tictactoe`'s 16 — `unittest`
batches all methods within one process, so growing a module's
internal test count costs nothing extra from `lirk`'s process-model
perspective. Good design property, confirmed rather than assumed this
time.

**The whole-repo test form is no longer sub-second, and that's fine,
but worth having the real number on record.** ~42s wall-clock for
`lirk test //...` across 10 test targets, cache cleared. The bulk of
that is very likely `backgammon:main_test` alone (a real ~2500-line
piped-input full game, ~9-12s through `lirk`'s nested-subprocess path
per earlier measurement in this session), with the remaining ~30s
spread thin across the other 7 subprocess-spawning test targets under
this environment's apparent per-python-process-startup overhead. Not
a complaint — still comfortably a "wait a bit" experience, not a "go
get coffee" one — just correcting the prior assessment's now-stale
"both return in well under a second" claim, which predates this
target existing.

**A concrete, freshly-observed data point on this environment's
broken CPU-time accounting (relevant context, not new to report as a
`lirk` issue — `terminal-projects`' own `docs/KNOWN_ISSUES.md`
already documents this phenomenon under Please/SIGHUP investigation,
but this session hit an even more striking example worth passing
along).** Wrapping `lirk test //...` in the shell's `time` builtin: a
genuine 42-second wall-clock run reported `user 24m40.485s`. Minutes
later, an unrelated command that failed instantly (`stdbuf: command
not found`, ~27ms wall-clock) reported **the same** `user 24m40s`,
give or take a second. Two commands of wildly different real duration
reporting near-identical "user CPU time" strongly suggests `time`'s
CPU-time figures in this environment are not being measured
per-invocation at all (possibly some kind of cumulative or
mismeasured counter) — wall-clock (`real`) is the only trustworthy
number here. Not a `lirk` bug (this is a shell/environment-level
measurement issue, well outside `lirk`'s own code), but worth knowing
if `lirk`'s own test suite or anything else on this project ever
tries to reason about CPU time rather than wall-clock time on this
class of device.

**`BUILD.lirk` copy-paste is real but not yet painful.** The exact
same 4-line `main_test` block (`[[target]] name = "main_test" type =
"test" srcs = ["main_test.py"] deps = [":main"]`) was pasted into 4
different `BUILD.lirk` files this session, identical every time. At 5
`BUILD.lirk` files this is a non-issue; flagging only because `chess`
will make it 6, and if `adventure-engine` later multiplies package
count further, "every package needs this exact boilerplate" could
eventually become worth a templating mechanism. Not recommending
anything now — genuinely fine at this scale, TOML's verbosity here is
a feature (readable, no magic) more than a cost.

**No new error-message data this session.** Every `BUILD.lirk` this
session was syntactically correct on the first try (copied from an
established template), so no new parse-error or config-error messages
were actually triggered or observed. Nothing to report either way.

---

## 5. Updated priority suggestions, through the lens of `chess` (next, and the most rule-complex target yet)

Ranked by value vs. effort, same framing as last time.

1. **Verify multi-file `library`/`test` targets work as expected, the
   first time `chess` actually needs more than one file — before
   spending effort on `srcs` glob syntax.** Near-zero effort (it's a
   verification step, likely not a code change at all, based on
   reading `targets.py`/`actions.py` this session). Directly relevant
   to `chess`, which is meaningfully more rule-complex than anything
   built so far (check/checkmate/stalemate detection, castling with
   its multiple invalidation conditions, en passant, promotion) and
   is a plausible candidate to want e.g. a separate `pieces.py` or
   `moves.py` alongside `board.py`. If this "just works," it closes
   out the last remaining item from the prior assessment's deferred
   list that had any near-term relevance.

2. **Add a one-line summary count to `lirk test //...` output.** Low
   effort, concretely felt the first time that form was used at
   today's scale, and will matter more, not less, once `chess` pushes
   the test-target count higher.

3. **Relay the documentation-sync gap around `--force` to whoever
   owns `terminal-projects` next** (not a `lirk`-side action item) —
   see section 3.3. Genuinely zero `lirk` effort; just a heads-up
   worth not losing.

4. **Drop `lirk run` from the roadmap rather than continuing to
   deprioritize it.** The concrete need it was meant to serve is
   fully met by ordinary `test` targets subprocessing the entrypoint,
   proven across all 4 games now, not just theorized.

5. **Parallelism, remote caching, sandboxing, `lirk query`: still not
   urgent, reconfirmed at 2x the target count.** 20 targets, ~42s for
   a full cache-cleared `lirk test //...`, `lirk build //...` still
   effectively instant (library validation is pure `ast.parse()`, no
   subprocess cost). `chess` will add roughly 4-6 more targets at
   most (matching the established `board`/`board_test`/`main`/
   `main_test` shape, maybe +1-2 if item 1 above leads to a genuine
   multi-file split) — nowhere near a scale where any of these five
   would earn their complexity. Reaffirming the prior ranking, now
   with a second, larger data point behind it rather than just the
   original 10-target baseline.
