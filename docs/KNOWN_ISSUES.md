# Known Issues

Convention: newest entry at the top. Each entry records what was
found, how it was confirmed, what was done about it, and how the fix
was verified — same rigor regardless of whether the bug is closed or
still open.

---

## `lirk test` failed on root-relative imports — found and fixed (2026-07-27)

**Status:** Fixed. Confirmed 10/10 across two separate 10-run batches
(fresh shell / fresh cache each run); lirk's own 42-test suite still
passes.

### What was found

Reported via an uncommitted `FINDINGS.md` from a dogfooding session
against `terminal-projects`' `shared/term.py` / `shared/term_test.py`
(2026-07-27; see that repo's `docs/KNOWN_ISSUES.md` and
`docs/ACTIVE_SESSION.md`, commits `3c87816` / `c17c6f8`, for the
dogfooding-side narrative).

`lirk build //shared:term` succeeded, but `lirk test
//shared:term_test` failed **every time (0/10 runs, fresh shell per
attempt)** with an identical `ModuleNotFoundError: No module named
'shared'`. `shared/term_test.py` imports its sibling module with a
root-relative import — `from shared import term` — the convention
Bazel/Please encourage for disambiguating packages, and the same
convention `terminal-projects`' pre-existing Please-based `BUILD`
already relied on.

### Root cause

`lirk/actions.py`'s `run_test` ran each test via `python3 -m unittest
<module>` with `cwd` set to the target's own package directory
(`root / target.package`) and no `PYTHONPATH` set. `python -m` puts
the current directory on `sys.path[0]`, so only modules sitting flat
inside that package directory were importable — `shared` (the package
itself, needed to resolve `from shared import term`) was never on
`sys.path`.

This matched a real scope gap in `lirk`'s own test suite: every
fixture (`tests/fixtures/sample_repo/a/test_a.py` etc.) used a flat
import (`from a import greet`), so this path was never exercised
end-to-end before the `terminal-projects` dogfooding run surfaced it.

### Fix

`lirk/actions.py`, `run_test`: keep `cwd=pkg_dir` (unchanged), but
pass an `env` to `subprocess.run` with `PYTHONPATH` set to the repo
root, prepended in front of any existing `PYTHONPATH` from the calling
environment. This is the smallest of three directions the findings
handoff sketched (the other two — running with `cwd=root` plus a
dotted module path, or scoping v1 to flat imports only and documenting
it as a limitation — were not attempted, since this one resolved it).

Flat imports keep working unchanged (still resolved via `cwd` being
`sys.path[0]`); root-relative imports now resolve via the repo root
being on `PYTHONPATH`. No process-group/session/pty/shell=True
constraints were touched — still one direct `subprocess.run()` call
per test file.

### Verification

- Full existing suite: 42/42 tests still passing after the change.
- Reproduction against `terminal-projects`' `shared:term_test`:
  10/10 passes in `env -i` fresh shells.
  10/10 passes in a second batch with `.lirk-cache.json` deleted
  before *every* run, to force a real subprocess execution each time
  rather than a cached pass/fail result — ruling out "lucky cache hit"
  as an explanation.
- No stray state left in `terminal-projects` (`.lirk-cache.json` is
  gitignored there and was removed after verification).
