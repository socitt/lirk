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
    than an unguarded traceback out of the cache layer."""
    pkg_dir = root / target.package
    return [f for f in (*target.srcs, *target.data) if not (pkg_dir / f).is_file()]


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
            ast.parse(src_path.read_text(), filename=str(src_path))
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

    env = os.environ.copy()
    root_str = str(root.resolve())
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{root_str}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else root_str
    )

    for src in target.srcs:
        module = Path(src).stem
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
            stdout_parts.append(e.stdout or "")
            stderr_parts.append(e.stderr or "")
            return ActionResult(
                target.label,
                False,
                f"{module} timed out after {TEST_TIMEOUT_SECONDS}s",
                "\n".join(stdout_parts),
                "\n".join(stderr_parts),
            )
        stdout_parts.append(proc.stdout)
        stderr_parts.append(proc.stderr)
        if proc.returncode != 0:
            return ActionResult(
                target.label,
                False,
                f"{module} failed (exit {proc.returncode})",
                "\n".join(stdout_parts),
                "\n".join(stderr_parts),
            )

    return ActionResult(
        target.label, True, "passed", "\n".join(stdout_parts), "\n".join(stderr_parts)
    )
