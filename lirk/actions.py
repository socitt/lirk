"""Build and test actions.

Per the process-model constraints this project exists to satisfy: one
direct subprocess.run() call per test file, output and exit code
captured straight from that call (no separate results-file step), no
new process group/session, no pseudo-terminal, no shell=True.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lirk.targets import Target


@dataclass
class ActionResult:
    label: str
    ok: bool
    message: str
    stdout: str = ""
    stderr: str = ""


def validate_target(target: Target, root: Path) -> ActionResult:
    """'Build' a target. Python needs no compilation step, so for v1
    this just confirms its declared source files exist."""
    pkg_dir = root / target.package
    missing = [src for src in target.srcs if not (pkg_dir / src).is_file()]
    if missing:
        return ActionResult(
            target.label, False, f"missing source file(s): {', '.join(missing)}"
        )
    return ActionResult(target.label, True, "ok")


def run_test(target: Target, root: Path) -> ActionResult:
    """Run a test target's source files via `python3 -m unittest`."""
    validation = validate_target(target, root)
    if not validation.ok:
        return validation

    pkg_dir = root / target.package
    stdout_parts = []
    stderr_parts = []

    for src in target.srcs:
        module = Path(src).stem
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", module],
            cwd=pkg_dir,
            capture_output=True,
            text=True,
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
