"""`lirk init`: draft BUILD.lirk files for an existing repo.

Deliberately split in two, so the part that has to be right is the part
that is already proven:

1. **Skeleton (this module).** One `library` per package directory with
   the directory's non-test `.py` files as srcs, and one `test` target
   for its `test_*.py` / `*_test.py` files. No deps are written here.
2. **Deps (lirk.fix).** The new targets are then handed to the same
   planner `lirk fix` uses, which derives every edge from the imports
   the srcs actually make -- never guessing between two owners, never
   closing a cycle, and verifying each edit by re-parse before writing.

So `init` invents nothing about the dependency graph: it declares which
files exist, and the import check says how they connect.

A directory that already has a BUILD.lirk is never touched, so `init`
is safe to re-run after adding packages.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from lirk.targets import BUILD_FILENAME, ROOT_MARKER, load_ignores

# Directory names never scanned for sources, beyond the dot-prefixed rule
# the BUILD.lirk scan already applies: generated output and environments,
# which hold Python that is not this repo's source.
# Never source, skipped silently. Deliberately *not* "env"/"venv": a real
# virtualenv is recognised by its pyvenv.cfg whatever it's called, and a
# package named `env` (an RL environment, settings) is ordinary code --
# skipping it by name silently dropped one in the slingshot repo.
SKIP_DIRS = {"__pycache__", "node_modules", "site-packages"}
# Usually generated output (setuptools copies the package into build/),
# so skipped -- but said out loud, since a package can have these names.
SKIP_ANNOUNCED = {"build": "looks like build output", "dist": "looks like build output"}
_TEST_FILE = re.compile(r"^(test_.*|.*_test)\.py$")
_IMPORTS_UNITTEST = re.compile(r"^\s*(import unittest\b|from unittest\b)", re.MULTILINE)
_IMPORTS_PYTEST = re.compile(r"^\s*(import pytest\b|from pytest\b)", re.MULTILINE)


@dataclass
class PackageDraft:
    package: str  # "" for the repo root
    name: str
    srcs: list[str]
    tests: list[str]
    runner: str
    # Subdirectories holding files but no Python: likely runtime data
    # (fixtures, golden output) that tests read and should declare.
    data_hints: list[str] = field(default_factory=list)

    @property
    def library_label(self) -> str | None:
        return f"//{self.package}:{self.name}" if self.srcs else None

    @property
    def test_label(self) -> str | None:
        return f"//{self.package}:{self.name}_test" if self.tests else None

    def render(self) -> str:
        """The BUILD.lirk text. Deps are left to `lirk fix`."""
        blocks = [
            "# Drafted by `lirk init`. Deps were derived from the srcs' imports.\n"
            "# Declare any file a target reads at runtime under `data`, and\n"
            "# split targets further as needed (each is a unit of caching).\n"
        ]
        if self.srcs:
            blocks.append(
                "[[target]]\n"
                f'name = "{self.name}"\n'
                'type = "library"\n'
                f"srcs = {_toml_list(self.srcs)}\n"
            )
        if self.tests:
            runner = f'runner = "{self.runner}"\n' if self.runner != "unittest" else ""
            blocks.append(
                "[[target]]\n"
                f'name = "{self.name}_test"\n'
                'type = "test"\n'
                f"{runner}"
                f"srcs = {_toml_list(self.tests)}\n"
            )
        return "\n".join(blocks)


def _toml_list(items: list[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"


def _is_venv(path: Path) -> bool:
    return (path / "pyvenv.cfg").is_file()


def _runner_for(tests: list[Path]) -> str:
    """pytest if any test file imports pytest or doesn't import unittest
    at all (plain `def test_...` functions only run under pytest)."""
    for path in tests:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _IMPORTS_PYTEST.search(text) or not _IMPORTS_UNITTEST.search(text):
            return "pytest"
    return "unittest"


def _holds_only_data(directory: Path) -> bool:
    """True if `directory` contains files, none of them Python, at any
    depth (ignoring hidden entries and __pycache__)."""
    has_files = False
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        for f in filenames:
            if f.startswith("."):
                continue
            if f.endswith(".py"):
                return False
            has_files = True
    return has_files


def draft_packages(
    root: Path,
) -> tuple[list[PackageDraft], list[str], list[tuple[str, str]]]:
    """Survey the repo for `lirk init`.

    Returns (drafts for every directory holding `.py` files and no
    BUILD.lirk, packages kept because they already have one, and
    (directory, reason) for each directory skipped that a person might
    have expected to be drafted).
    """
    ignored = {Path(e.strip("/")) for e in load_ignores(root) if e.strip("/")}
    drafts: list[PackageDraft] = []
    kept: list[str] = []
    skipped: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        rel = here.relative_to(root)
        keep = []
        for d in sorted(dirnames):
            sub = rel / d
            if d.startswith(".") or d in SKIP_DIRS or sub in ignored:
                continue
            if _is_venv(here / d):
                skipped.append((sub.as_posix(), "a virtualenv"))
                continue
            if d in SKIP_ANNOUNCED:
                skipped.append((sub.as_posix(), SKIP_ANNOUNCED[d]))
                continue
            keep.append(d)
        dirnames[:] = keep
        py = sorted(f for f in filenames if f.endswith(".py"))
        # conftest.py is a pytest input, fingerprinted automatically for
        # pytest targets -- not a library src or a test module.
        py = [f for f in py if f != "conftest.py"]
        if not py:
            continue
        package = "" if rel == Path(".") else rel.as_posix()
        if BUILD_FILENAME in filenames:
            kept.append(package)
            continue
        tests = [f for f in py if _TEST_FILE.match(f)]
        srcs = [f for f in py if f not in tests]
        name = here.name if package else root.resolve().name
        hints = [d for d in keep if _holds_only_data(here / d)]
        drafts.append(
            PackageDraft(
                package, name, srcs, tests, _runner_for([here / t for t in tests]), hints
            )
        )
    return drafts, kept, skipped


def write_drafts(root: Path, drafts: list[PackageDraft]) -> list[str]:
    """Write each draft's BUILD.lirk (and an empty .lirk-root if the repo
    has none). Returns the labels of every target created."""
    if not (root / ROOT_MARKER).exists():
        (root / ROOT_MARKER).write_text("")
    labels: list[str] = []
    for draft in drafts:
        (root / draft.package / BUILD_FILENAME).write_text(draft.render(), encoding="utf-8")
        labels += [l for l in (draft.library_label, draft.test_label) if l]
    return labels
