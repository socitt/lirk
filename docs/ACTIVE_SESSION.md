# Active Session Log

Purpose: running log of what's being attempted right now, updated
before and after every risky/uncertain step, so a mid-session crash
(iSH-AOK has crashed before, wiping uncommitted work) doesn't lose
context about what state things were left in.

Convention: newest entry at the top. Each entry says what was about
to be attempted, and once done, what actually happened.

---

## 2026-07-26

- **Status**: Session start. Repo initialized with LICENSE only.
- **Plan for this session** (see user request for full spec):
  1. This file (docs/ACTIVE_SESSION.md) — in progress.
  2. Root README explaining what lirk is and why.
  3. Propose target-config format (BUILD.lirk vs TOML vs YAML),
     implement parser.
  4. Dependency graph + topological sort, with fake test fixtures.
  5. Content-hash-based incremental build skipping.
  6. CLI `build`/`test` commands.
  7. Stop and report back — no dogfooding against terminal-projects
     until explicitly told to proceed.
- **Environment check done**: Python 3.12.13 available, stdlib
  `tomllib` present (read-only TOML parser), `yaml` module NOT
  installed. This informs the format decision in step 3.
- Next: write this file, commit, push, then start README.
