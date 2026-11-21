# lirk dogfooding notes: adventure-engine (2026-07-27)

## Resolution (2026-07-28)

Picked up per the hand-off convention. No bugs found and no watch
items raised in this file — the "shape of the target" question it set
out to answer (does the target model hold up when a `library`'s
content is mostly a big dict literal instead of functions?) is
answered inline: yes, no friction. Archived here rather than folded
into `KNOWN_ISSUES.md`, matching the precedent set by the two prior
closed-clean assessments (see `docs/assessments/2026-07-26-assessment.md`
and `2026-07-27-post-go-assessment.md`) — no action needed.

(The same day's chess-session dogfooding file raised one open item,
the flat per-test-invocation overhead; see the Resolution section at
the top of `2026-07-27-chess.md` for that investigation.)

---

Running log of real lirk usage from the consumer side (terminal-projects
repo) while building `adventure-engine` — the first non-board-game
target. Append-only; not rewritten. Leaving this uncommitted in the lirk
repo per the established hand-off convention — a lirk session will pick
it up later.

Context for whoever reads this cold: terminal-projects is consuming
lirk at HEAD as of this session (still `9611760`, no new lirk commits
since the chess session — `git -C ../lirk pull` at session start
reported already up to date).

## Why this target is a genuinely different shape

The five board games are all "rule validation" targets: a fixed board
representation, a fixed ruleset, pure functions that either allow or
reject a move. `adventure-engine` inverts that — the *engine* (`engine.py`,
`runner.py`) is small and generic, and the interesting content
(`stories/dungeon`, `stories/train-mystery`) is branching, mutable,
author-facing data rather than code enforcing a fixed rule surface.
Watching for: does lirk's target/dependency model (BUILD.lirk
`library`/`test` targets, explicit `deps`) hold up the same way when a
`library` target's "logic" is mostly a big dict literal instead of a
handful of pure functions? So far (through `engine.py`/`runner.py`,
before any real story content exists) — no friction, it's just another
`library` target with `srcs`/`deps` like any other. Will note if that
changes once real story `.py` data files with large ASCII-art string
literals get added as `library` targets of their own.

## Engine core (engine.py, runner.py) — no lirk-specific findings yet

Both built and tested clean on the first `lirk build`/`lirk test` try
each. One operational note, not a lirk bug: `runner_test.py` is a
subprocess-based test (same style as every board game's `main_test.py`)
that itself spawns a *further* subprocess per test case (the real
interactive loop, piped stdin) — that's two layers of subprocess
nesting under `lirk test`'s own subprocess model. Wall-clock cost:
~6-7s standalone via plain `python3 -m unittest`, ~10-12s per `lirk
test //adventure-engine:runner_test` invocation. A flat 10-run batch of
that target hit the Bash tool's 120s default timeout (10 runs x ~10-12s
each is right at the edge) — not a lirk failure, just needed a longer
Bash-tool timeout for the batch, same category of "don't mistake slow
for hung" note already on record for backgammon's `main_test` in the
chess-session dogfooding file. No new lirk-side finding here, just
confirming the same overhead shape shows up again with a different kind
of nested subprocess (this repo's own `runner.py`-driven fixture
script, not another game's `main.py`).

## Story packs (stories/dungeon, stories/train-mystery) — closing notes

Both packs' `story.py` data files (9 and 8 scenes respectively, ASCII
art + branching dicts, ~170-210 lines each) built as ordinary
`library` targets with zero friction — the "watching for" question
above is answered: lirk's target model doesn't care whether a
`library`'s content is mostly functions or mostly a big nested dict
literal, it's just Python source either way as far as `lirk build` is
concerned. No large-literal-specific slowdown or parsing issue
observed at this size.

The one genuinely new wrinkle vs. the five board games: this is the
first time a `library` target (`//adventure-engine:runner`) is
consumed cross-package from *two different* sibling packages
(`stories/dungeon:main` and `stories/train-mystery:main`) rather than
just from `shared:term`/`shared:input` into a single leaf package.
Worked exactly as expected — `lirk build //...` resolved the full
34-target graph clean, both story packs' `BUILD.lirk` files declaring
`deps = [":story", "//adventure-engine:runner"]` independently, no
diamond-dependency issue (`runner` itself depends on `engine` +
`shared:term` + `shared:input`, so it's a 2-level cross-package fan-in
into a target that itself has cross-package deps — lirk's cache
handled the shared `engine`/`shared:*` builds being reused across both
story packs' test runs without any staleness, confirmed across
multiple cache-cleared 10-run batches for each story's `main_test`).

Final tally for this target: `lirk build //...` 34/34 clean, `lirk
test //...` 16/16 clean, every individual test target independently
confirmed 10/10 across fresh-shell, cache-cleared runs. No lirk bugs
found this session — this file is a "shape of the target" observation
log, not a bug report, unlike the chess-session file's regression
checks against 18 real upstream fixes. Nothing here needs action from
a lirk-side session; safe to fold into a general "cross-package
fan-in works fine at this scale" note whenever this file gets triaged.
