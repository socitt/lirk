"""Build and test actions.

Per the process-model constraints this project exists to satisfy: one
direct subprocess.run() call per test file, output and exit code
captured straight from that call (no separate results-file step), no
new process group/session, no pseudo-terminal, no shell=True.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lirk.targets import Target

# Chosen so it doesn't trip on the slowest known test target (~12s,
# backgammon:main_test). subprocess.run's timeout only kills the
# direct child, not any grandchild a main_test.py may have spawned
# itself (e.g. a main.py it drives) -- killing the whole tree needs a
# process group, which this project's process model forbids. A
# partially-cleaned-up timeout is accepted as strictly better than an
# unbounded hang.
TEST_TIMEOUT_SECONDS = 600


@dataclass
class ActionResult:
    label: str
    ok: bool
    message: str
    stdout: str = ""
    stderr: str = ""


def missing_files(target: Target, root: Path) -> list[str]:
    """Declared srcs/data files (relative to the target's package) that
    don't exist. Checked up front by the CLI, before fingerprinting,
    so a missing file is reported as a clean per-target failure rather
    than an unguarded traceback out of the cache layer.

    A `data` entry may name a directory, in which case it exists if the
    directory does; `srcs` must still be files, since every src is
    parsed as Python."""
    pkg_dir = root / target.package
    missing = [s for s in target.srcs if not (pkg_dir / s).is_file()]
    missing += [
        d
        for d in target.data
        if not (pkg_dir / d).is_file() and not (pkg_dir / d).is_dir()
    ]
    return missing


def validate_target(target: Target, root: Path) -> ActionResult:
    """'Build' a target: confirm its declared source files exist and
    parse as syntactically valid Python. No compilation step beyond
    that (v1 has no bytecode/artifact output)."""
    pkg_dir = root / target.package
    missing = missing_files(target, root)
    if missing:
        return ActionResult(
            target.label, False, f"missing source file(s): {', '.join(missing)}"
        )

    for src in target.srcs:
        src_path = pkg_dir / src
        try:
            # Decoded as UTF-8 explicitly, not via the locale encoding:
            # Python source is UTF-8 by default (PEP 3120), and a
            # locale-dependent read makes this check platform-dependent
            # -- a single-byte locale like cp1252 decodes arbitrary
            # bytes, so a binary file reaches ast.parse and reports a
            # confusing syntax error instead of "not readable".
            ast.parse(
                src_path.read_text(encoding="utf-8"), filename=str(src_path)
            )
        except SyntaxError as e:
            return ActionResult(
                target.label, False, f"{src}: syntax error: {e}"
            )
        except (UnicodeDecodeError, ValueError) as e:
            return ActionResult(
                target.label, False, f"{src}: not readable as Python source: {e}"
            )

    return ActionResult(target.label, True, "ok")


def run_test(target: Target, root: Path) -> ActionResult:
    """Run a test target's source files via `python3 -m unittest`."""
    validation = validate_target(target, root)
    if not validation.ok:
        return validation

    if not target.srcs:
        # Belt-and-braces: _parse_target already rejects a `test`
        # target with no srcs, so this shouldn't be reachable, but a
        # target with zero srcs must never silently report success.
        return ActionResult(target.label, False, "no srcs to run")

    pkg_dir = root / target.package
    stdout_parts = []
    stderr_parts = []
    failed_modules: list[str] = []
    timed_out: list[str] = []
    ran_nothing: list[str] = []

    env = os.environ.copy()
    root_str = str(root.resolve())
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{root_str}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else root_str
    )

    for src in target.srcs:
        # Dotted path relative to the package, not just the stem: a src
        # in a subdirectory ("sub/test_nested.py") must run as
        # `sub.test_nested`, since `-m unittest test_nested` with
        # cwd=pkg_dir cannot find it. Resolves without __init__.py --
        # sub/ is importable as a namespace package (PEP 420).
        # Using the stem alone also silently collided two srcs with the
        # same filename in different subdirectories onto one module.
        module = Path(src).with_suffix("").as_posix().replace("/", ".")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", module],
                cwd=pkg_dir,
                capture_output=True,
                text=True,
                env=env,
                stdin=subprocess.DEVNULL,
                timeout=TEST_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            # Recorded and carried on, not returned: bailing out here
            # let one hung src hide every src after it, which is the
            # asymmetry accumulating failures was meant to remove. A
            # hung test often does mean the whole target is wedged, but
            # that is a guess, and guessing costs the other results.
            stdout_parts.append(e.stdout or "")
            stderr_parts.append(e.stderr or "")
            failed_modules.append(module)
            timed_out.append(module)
            continue
        stdout_parts.append(proc.stdout)
        stderr_parts.append(proc.stderr)
        # A module with no tests exits 5 (NO TESTS RAN) on 3.12+, but
        # exits 0 on 3.11 -- which pyproject.toml still supports -- so
        # a green exit code alone reports a false PASS for a test file
        # that tests nothing. The "Ran 0 tests" summary line is written
        # on every version, so it is the portable signal.
        #
        # Checked independently of the exit code rather than as a
        # fallback for a zero one, so the reason is named on 3.12 too,
        # where the exit code already catches it but explains nothing.
        # It can only ever add to the failure, never excuse one.
        ran_no_tests = "Ran 0 tests" in proc.stderr
        if proc.returncode != 0 or ran_no_tests:
            failed_modules.append(module)
        if ran_no_tests:
            ran_nothing.append(module)

    if failed_modules:
        detail = (
            f"{len(failed_modules)} of {len(target.srcs)} src files failed: "
            f"{', '.join(failed_modules)}"
        )
        if timed_out:
            detail += (
                f" -- timed out after {TEST_TIMEOUT_SECONDS}s: "
                f"{', '.join(timed_out)}"
            )
        if ran_nothing:
            detail += f" -- contained no tests: {', '.join(ran_nothing)}"
        return ActionResult(
            target.label,
            False,
            detail,
            "\n".join(stdout_parts),
            "\n".join(stderr_parts),
        )

    return ActionResult(
        target.label, True, "passed", "\n".join(stdout_parts), "\n".join(stderr_parts)
    )
