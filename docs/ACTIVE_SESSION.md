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
- **Next:** find a third consumer repo. That is now the *only* thing
  between the project and all three v1 criteria. After that, D1 —
  `docs/index.md` is doubly stale now, still claiming "not yet
  self-hosting" and predating both `.lirk-root` config and `data`
  directories.

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
