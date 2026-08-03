# Active Session Log

Purpose: running log of what's being attempted **right now**, updated
before and after every risky/uncertain step, so a mid-session crash
(iSH-AOK has crashed before, wiping uncommitted work) doesn't lose
context about what state things were left in.

Convention: newest entry at the top. Each entry says what was about to
be attempted, and once done, what actually happened.

**Scope:** this file is for in-flight session state only. It is not
the backlog and not the architecture record — those are
[TASKS.md](TASKS.md) and [DESIGN.md](DESIGN.md), both living documents
kept current rather than appended to. Trim this file when entries stop
being useful for crash recovery; the full history stays in git.

Entries prior to 2026-07-30 were trimmed during the docs consolidation
that produced DESIGN.md and TASKS.md — everything still relevant from
them was folded into those two files. `git log docs/ACTIVE_SESSION.md`
has the originals.

---

## 2026-08-03

- **The third repo arrived: `termrery`** (`/root/git/termrery`, review
  in its `docs/lirk-notes.md`). Criterion 2 is now met, so all three v1
  criteria hold. Read the review, then reproduced every behavioural
  claim in it against current lirk source in a throwaway tree before
  recording anything — the review was written against 0.1.0 and none of
  it was taken on trust.
- **One claim turned out to be worse than reported.** They filed
  "`deps` are not checked against real imports" as a boundary/hygiene
  complaint. It is also a *stale-PASS* mechanism: an undeclared edge is
  absent from the fingerprint, so the dependency's contents are not an
  input. Reproduced end to end — edit the undeclared dependency, `lirk
  test` says `cached` and green, `--force` on the same tree FAILs. Same
  family as the fixture-`data` bug closed yesterday, and the second
  instance of it. Filed as **H1**, the only open HIGH.
- Also confirmed: non-`.py` in `srcs` is caught only when the contents
  happen not to parse (`hello` in a `.txt` builds clean, a sentence
  doesn't) — **M3**; the cwd root fallback is silent and label errors
  never name the root — **M4**; no failed-target list in the summary —
  **M6**; no `lirk --version` — **L6**.
- **M5/D4 is the interesting one.** Their "no `binary` type / `lirk
  run`" is a settled decision (DESIGN §6), so it stays closed — but
  their `main()` was defined and never called, `python3 -m cli.render`
  did nothing, and lirk stayed green throughout. The decision rests on
  "a `test` target that subprocesses the entrypoint covers it", and
  that pattern is documented nowhere. Recorded as a docs gap against
  the decision rather than as pressure to re-open it.
- Also settled and deliberately *not* filed: `lirk query` / listing
  targets (deferred at ~26 targets; termrery has four).
- **Then H1 was implemented and closed, same session.** Two decisions
  taken first, both the user's: violations **FAIL** (a warning leaves
  the stale-PASS path open, which was the whole reason it was HIGH),
  and **v1 is tagged after the correctness work, not before**.
- The check walks the trees `validate_target` already parsed, resolves
  each imported module the way the runner does (package dir, then repo
  root), and fails on a resolved file owned by a target outside the
  transitive closure. `ImportEnv` is built in `cli.py` so `actions.py`
  stays free of the graph layer. `ACTION_VERSION` 8 → 9.
- **Ran it against all three real repos before landing** — lirk (13
  targets), `terminal-projects` (66), `termrery` (4): 83 targets, zero
  false positives. Adoption cost is nil; termrery's real BUILD files
  were correct all along (their violation was staged in a copy).
- Fixture `import_repo`. Suite 112 → **127**, self-hosted 13/13 build
  and 5/5 test, both green.
- **H2 opened, and it is the reason v1 isn't tagged yet.** Writing the
  check forced the question of what to do about an imported file that
  *no* target declares. Rejecting it would fail ordinary repos (an
  undeclared `__init__.py` is everywhere, including our own fixtures),
  so the check stays silent on it — which leaves the input
  unfingerprinted. Verified it really is a stale PASS: edit an
  undeclared `orphan/thing.py`, `lirk test` says `cached` and green,
  `--force` FAILs. Same shape as H1, different fix, not yet chosen.
- **Next:** H2 (choose the fix first — implicit fingerprinting vs
  requiring declaration), then the v1 tag. M4/M3/M6/L6/D4 are all small
  and unblocked behind it.

## 2026-08-02

- **M1 and M2 both landed**, suite 91 → 95, all green. Details in
  TASKS.md "Recently closed"; the behavior changes are written up in
  DESIGN.md §3 and §4 rather than here.
- **Decided criterion 2's repo-count clause**: self-hosting counts as
  the second repo. This puts criterion 1 on the critical path for both
  criteria, and leaves one more consumer repo to find.
- **Self-hosting landed — criterion 1 is met.** `lirk build //...`
  builds 13 targets, `lirk test //...` is 5/5 green. Runs alongside
  `unittest discover`, not instead of it. Suite 95 → 110.
- Attempting it forced three engine changes, none of which were
  predictable from reading the source: the fixture scan (L4, promoted
  from LOW — the graph would not load at all), `data` directories, and
  the stale-PASS those two jointly fixed. Details in TASKS.md
  "Recently closed"; behavior is written up in DESIGN.md §2 and §4.
- **Cleared the rest of the backlog** — everything that did not depend
  on having a third repo. L1 (zero-test modules reported PASS on 3.11),
  L2 (a timeout abandoned later srcs), L5 (misnamed parameter), the
  torn-temp-file half of L3, and D1 (`docs/index.md` rewritten against
  the real v1 criteria, plus Installation, `data`, and `ignore`).
  `ACTION_VERSION` 7 → 8 for L1+L2. Suite 110 → 112.
- **Next, and the only things left:** find a third consumer repo
  (blocks criterion 2, and therefore v1), and D2 (needs the upstream
  iSH-AOK issue URL). Both need input that isn't in the repo.

## 2026-07-30

- **Consolidated the docs.** Wrote `docs/DESIGN.md` (current-state
  architecture, verified against source rather than restated from the
  README) and `docs/TASKS.md` (v1 criteria with honest status, open
  bugs, prioritized next actions), folding forward what was still true
  from `docs/assessments/` and `docs/reviews/` and dropping what those
  had already resolved. Added a Contributing section to `README.md`
  pointing at both. `docs/assessments/` and `docs/reviews/` left in
  place as historical record.
- **`DRAFT_BAZEL_JVM_ISSUE.md` removed** — the user filed the upstream
  iSH-AOK issue and deleted the local draft, so it's no longer pending
  review. I briefly restored it from git after mistaking the deletion
  for an accident; re-removed once the user said why. Updated
  `KNOWN_ISSUES.md`'s reference from "draft, pending review before
  filing" to "filed upstream", and dropped the now-dead link from
  `DESIGN.md`. **Still needs the issue URL** — see TASKS.md D2.
- **Deleted `docs/design/target-format.md`** (duplicate of the
  published `docs/build-format.md`, which is a strict superset) and
  repointed `lirk/targets.py`'s module docstring at
  `build-format.md` + `DESIGN.md`.
- **Fixed the one platform-dependent test** (TASKS M3). The suite was
  90/91 on Windows: `validate_target`'s `read_text()` used the locale
  encoding, so cp1252 decoded the `binary_src_repo` PNG fixture and it
  reached `ast.parse` as a null-byte `SyntaxError` instead of the
  intended `UnicodeDecodeError` / "not readable as Python source".
  Pinned `encoding="utf-8"` (correct regardless — Python source is
  UTF-8 by PEP 3120, and `ast.parse` on a `str` ignores coding
  declarations anyway), which makes the behavior identical on every
  platform rather than just loosening the assertion. Bumped
  `ACTION_VERSION` 5 → 6 per DESIGN.md §4, since this changes what a
  successful build means on non-UTF-8 hosts. Suite now **91/91 on
  Windows**; the pin is load-bearing (the test failed without it,
  which is how this was found).
- **Tallied v1 criterion 2** against the archived assessments — see
  TASKS.md for the result and the decision it now needs.
- **Next:** TASKS.md M1 (a missing source file aborting the whole
  repo-wide run) and M2 (subdirectory test srcs), both pending a
  go-ahead since they change execution behavior.
