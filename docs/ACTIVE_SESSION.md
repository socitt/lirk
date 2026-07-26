# Active Session Log

Purpose: running log of what's being attempted right now, updated
before and after every risky/uncertain step, so a mid-session crash
(iSH-AOK has crashed before, wiping uncommitted work) doesn't lose
context about what state things were left in.

Convention: newest entry at the top. Each entry says what was about
to be attempted, and once done, what actually happened.

---

## 2026-07-26 (update 5)

- **Status**: Step 5 done. `lirk/cache.py` computes a per-target
  fingerprint (own name/type, source file contents, transitive dep
  fingerprints) and a `.lirk-cache.json` load/save round-trip
  (already gitignored). Added real source files (a.py/b.py/c.py +
  their tests) to the sample_repo fixture so hashing has real content
  to work on — these will double as fixtures for step 6's actual
  subprocess-based test execution. 10 new tests, 25 total, all
  passing.
- Next: step 6, CLI `build`/`test` commands wired to subprocess.run()
  per the no-process-group/no-pty/no-results-file constraints.

## 2026-07-26 (update 4)

- **Status**: Step 4 done. `lirk/graph.py` scans a repo tree for
  BUILD.lirk files, resolves `//pkg:name` and `:name` deps into
  qualified labels, builds a Graph (targets + edges), and does a
  DFS-based topological sort with cycle detection (reports the full
  cycle path). Fixtures added under tests/fixtures/: sample_repo
  (linear a->b->c chain, each with a lib + a test depending on its
  sibling lib), cycle_repo (x<->y cycle), missing_dep_repo, and
  self_dep_repo. 6 new tests, 15 total, all passing.
- Next: step 5, content-hash-based incremental build cache
  (.lirk-cache.json).

## 2026-07-26 (update 3)

- **Status**: Git push auth resolved (user configured credentials
  outside this chat). Pushed the two queued commits successfully.
  Step 3 done: chose TOML for BUILD.lirk (docs/design/target-format.md
  has the tradeoff), implemented `lirk/targets.py` (Target dataclass +
  parse_build_file), 9 passing unittest cases in
  tests/test_targets.py. All committed and pushed.
- Next: step 4, dependency graph + topological sort across all
  packages in a repo, with fake fixture targets.

## 2026-07-26 (update 2)

- **Status**: Step 1 (this file) committed locally as `aad26aa`, but
  `git push` failed — no git credentials configured in this
  environment (no credential helper, no `gh`, no SSH key). Asked
  user how to handle auth; user chose to configure credentials
  themselves outside this chat (declined pasting a PAT into the
  conversation, which was the right call — reasonable to avoid
  putting long-lived secrets in a transcript). `github-cli` (2.83.0)
  is available via `apk` if a device-code login is wanted later.
  **Commits are accumulating locally and are NOT yet on the remote.**
  Proceeding with local commits per the plan; push everything once
  auth is sorted.
- Next: README (step 2), then target-config format (step 3).

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
