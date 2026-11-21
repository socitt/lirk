"""Build and test actions.

Per the process-model constraints this project exists to satisfy: one
direct subprocess.run() call per test file, output and exit code
captured straight from that call (no separate results-file step), no
new process group/session, no pseudo-terminal, no shell=True.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass
from pathlib import Path

from lirk.targets import Target, pytest_inputs

# Chosen so it doesn't trip on the slowest known test target (~12s,
# backgammon:main_test). subprocess.run's timeout only kills the
# direct child, not any grandchild a main_test.py may have spawned
# itself (e.g. a main.py it drives) -- killing the whole tree needs a
# process group, which this project's process model forbids. A
# partially-cleaned-up timeout is accepted as strictly better than an
# unbounded hang.
TEST_TIMEOUT_SECONDS = 600

# unittest's closing summary line, e.g. "Ran 3 tests in 0.004s". Anchored
# to a line start, and only the *last* occurrence is consulted: a test
# that itself drives unittest (lirk's own suite does) can echo an inner
# run's summary into its stderr before its own.
_RAN_LINE = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)


def _ran_zero_tests(stderr: str) -> bool:
    matches = _RAN_LINE.findall(stderr)
    return bool(matches) and matches[-1] == "0"


def _pytest_missing(stderr: str) -> bool:
    """`python -m pytest` failed because pytest isn't importable.

    Worth naming: the raw "No module named pytest" is easy to misread as
    the test's own import failing, and the fix (install pytest for the
    interpreter lirk runs under) is nothing to do with the test.
    """
    return "No module named pytest" in stderr


def _as_text(captured: str | bytes | None) -> str:
    """Partial output from a TimeoutExpired, as str.

    subprocess.run raises TimeoutExpired carrying the *raw bytes* read so
    far, even when called with text=True -- the decode only happens on
    the normal return path. Joining that with the str output of other
    srcs raised TypeError, so a timed-out test that had printed anything
    crashed lirk instead of being reported.
    """
    if captured is None:
        return ""
    if isinstance(captured, bytes):
        return captured.decode("utf-8", errors="replace")
    return captured


@dataclass
class ActionResult:
    label: str
    ok: bool
    message: str
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ImportEnv:
    """Repo context the import check needs, assembled by the caller.

    Passed in rather than derived here so this module stays free of the
    graph layer: `owners` is a repo-wide index and `allowed` is
    per-target, and only the CLI has both.

    - `owners`: resolved absolute path of every declared src -> the
      labels of every target declaring it (usually exactly one).
    - `allowed`: the labels this target may import from -- its whole
      transitive dep closure, including itself.
    """

    owners: Mapping[Path, frozenset[str]]
    allowed: Set[str]


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


def owner_index(
    targets: Mapping[str, Target], root: Path
) -> dict[Path, frozenset[str]]:
    """Resolved path of every declared src -> the labels declaring it.

    Built once per run and shared by every target's ImportEnv. A src
    declared by more than one target maps to all of them, and an import
    of it is allowed if *any* declaring target is in the importer's
    closure: each of them fingerprints the file, so any one in the
    closure is enough to make an edit invalidate the importer. Keeping
    only one owner (as this once did) made the verdict depend on which
    declaration happened to be indexed last -- a correct `deps` entry on
    the other declaring target was reported as an undeclared import.
    """
    index: dict[Path, set[str]] = {}
    for label, target in targets.items():
        for src in target.srcs:
            index.setdefault((root / target.package / src).resolve(), set()).add(label)
    return {path: frozenset(labels) for path, labels in index.items()}


def _imported_modules(tree: ast.AST, src_path: Path) -> list[tuple[str, Path | None]]:
    """Every module an AST imports, as (dotted name, base directory).

    The base is None for an absolute import (resolve it against sys.path
    as the runner sets it up) and an explicit directory for a relative
    one.

    `from pkg import name` yields both `pkg` and `pkg.name`: `name` may
    be a submodule -- which is an edge into another package -- or an
    ordinary attribute, which simply won't resolve to a file and is
    ignored.
    """
    found: list[tuple[str, Path | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, None) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base: Path | None = None
            if node.level:
                # `.` is the src's own directory, `..` its parent, etc.
                base = src_path.parent
                for _ in range(node.level - 1):
                    base = base.parent
            prefix = node.module or ""
            if prefix:
                found.append((prefix, base))
            for alias in node.names:
                dotted = f"{prefix}.{alias.name}" if prefix else alias.name
                found.append((dotted, base))
    return found


def _resolve_module(dotted: str, bases: Sequence[Path]) -> Path | None:
    """The file a dotted module name resolves to under `bases`, or None.

    Mirrors how the runner actually sets up imports (see run_test): the
    target's own package directory is `sys.path[0]`, and the repo root
    is on PYTHONPATH. Anything resolving outside those -- the stdlib,
    site-packages -- returns None and is not lirk's business.

    Resolves the full dotted path to one file, rather than also
    collecting the `__init__.py` of each package along the way. Those
    ancestors are inputs too in principle, but in a repo that declares
    its packages at all they belong to the same target as the module
    itself, and chasing them turns one clear error into several.
    """
    parts = dotted.split(".")
    if not all(parts):
        return None
    for base in bases:
        candidate = base.joinpath(*parts)
        module = candidate.with_suffix(".py")
        if module.is_file():
            return module
        init = candidate / "__init__.py"
        if init.is_file():
            return init
    return None


@dataclass(frozen=True)
class ImportProblem:
    """One import reaching outside a target's dep closure.

    `owners` is empty when no target declares the imported file (`path`,
    repo-relative); otherwise it names every target that does, none of
    which is in the importer's closure.
    """

    src: str
    dotted: str
    path: str
    owners: frozenset[str]

    def message(self) -> str:
        if not self.owners:
            return f"{self.src} imports '{self.dotted}' -- no target declares {self.path}"
        return (
            f"{self.src} imports '{self.dotted}' "
            f"({', '.join(sorted(self.owners))}), not in deps"
        )


def undeclared_imports(
    target: Target,
    root: Path,
    env: ImportEnv,
    parsed: Iterable[tuple[str, ast.AST]],
) -> list[str]:
    """Imports reaching outside the dep closure, as messages; see
    import_problems for the rule and its reasoning."""
    return [p.message() for p in import_problems(target, root, env, parsed)]


def import_problems(
    target: Target,
    root: Path,
    env: ImportEnv,
    parsed: Iterable[tuple[str, ast.AST]],
) -> list[ImportProblem]:
    """Imports reaching a target outside this one's declared dep closure.

    This is what stops `deps` from being decoration. Because targets run
    with the repo root importable, Python resolves a cross-package
    import whether or not the edge is declared -- so an undeclared edge
    is not merely undocumented, it is *absent from the fingerprint*, and
    editing the imported package invalidates nothing. The result is a
    cached PASS that `--force` turns into a FAIL. See docs/dev/TASKS.md H1.

    Checked against the transitive closure, not direct deps only: the
    stale-input problem is closed as soon as the dependency is folded
    into the fingerprint, which the closure does. Requiring a direct
    edge is a stricter hygiene rule (Bazel's "strict deps") that buys no
    additional correctness here, and would reject lirk's own BUILD
    files.

    An import resolving to a repo file that *no* target declares is
    reported too, for the same reason and with a different message: an
    undeclared file is fingerprinted by nobody, so it is the same stale
    input with no owner to name. Rejecting rather than fingerprinting it
    implicitly keeps the graph fully explicit, and gets transitivity for
    free -- once the file must be declared, whatever *it* imports falls
    under the rule above (docs/dev/TASKS.md H2).

    Only the module the dotted path resolves to is checked, not the
    `__init__.py` of each package along the way (see _resolve_module).
    An undeclared *ancestor* package init is therefore still an
    unfingerprinted input; it resolved to nothing across all three real
    repos, and collecting ancestors would turn one clear error into
    several.
    """
    pkg_dir = root / target.package
    root_resolved = root.resolve()
    problems: list[ImportProblem] = []
    seen: set[tuple[str, str]] = set()

    for src, tree in parsed:
        src_path = (pkg_dir / src).resolve()
        for dotted, base in _imported_modules(tree, src_path):
            bases = [base] if base is not None else [pkg_dir, root]
            found = _resolve_module(dotted, bases)
            if found is None:
                continue
            found = found.resolve()
            if not found.is_relative_to(root_resolved):
                continue
            owners = env.owners.get(found, frozenset())
            if owners & env.allowed:
                continue
            if (src, dotted) in seen:
                continue
            seen.add((src, dotted))
            rel = found.relative_to(root_resolved).as_posix()
            problems.append(ImportProblem(src, dotted, rel, owners))

    return problems


def validate_target(
    target: Target, root: Path, env: ImportEnv | None = None
) -> ActionResult:
    """'Build' a target: confirm its declared source files exist, parse
    as syntactically valid Python, and -- when `env` is supplied --
    import only from the targets this one declares. No compilation step
    beyond that (v1 has no bytecode/artifact output).

    `env` is None only when a target is validated with no repo context
    around it (unit tests do this); the CLI always supplies one, so the
    import check is not optional in a real run.
    """
    missing = missing_files(target, root)
    if missing:
        return ActionResult(
            target.label, False, f"missing source file(s): {', '.join(missing)}"
        )

    # A pytest target's conftest.py files are parsed and import-checked
    # like srcs: pytest imports them before any test, and they are
    # fingerprinted implicitly (cache.compute_fingerprints), so an import
    # they make outside the closure is the same stale input as one a src
    # makes. Named relative to the package ("../conftest.py") so the
    # message points at the right file and undeclared_imports resolves
    # it from the package directory like any src.
    parsed, error = _parse_sources(target, sources_to_parse(target, root))
    if error is not None:
        return error

    if env is not None:
        # Reuses the trees parsed above rather than re-reading the srcs:
        # syntax validity is a precondition of the import check anyway,
        # so a second parse would only be a second chance to disagree.
        undeclared = undeclared_imports(target, root, env, parsed)
        if undeclared:
            return ActionResult(
                target.label, False, "; ".join(undeclared)
            )

    return ActionResult(target.label, True, "ok")


def parse_target(
    target: Target, root: Path
) -> tuple[list[tuple[str, ast.AST]], ActionResult | None]:
    """Parse everything validate_target would, without the import check:
    the (name, tree) pairs, or the failure that stopped parsing."""
    missing = missing_files(target, root)
    if missing:
        return [], ActionResult(
            target.label, False, f"missing source file(s): {', '.join(missing)}"
        )
    return _parse_sources(target, sources_to_parse(target, root))


def sources_to_parse(target: Target, root: Path) -> list[tuple[str, Path]]:
    """(name, path) of everything validate_target parses for `target`:
    its srcs, plus a pytest target's conftest modules (see there)."""
    pkg_dir = root / target.package
    to_parse = [(src, pkg_dir / src) for src in target.srcs]
    to_parse += [
        (os.path.relpath(path, pkg_dir.resolve()).replace(os.sep, "/"), path)
        for path in pytest_inputs(target, root)
        if path.name == "conftest.py"
    ]
    return to_parse


def _parse_sources(
    target: Target, to_parse: Sequence[tuple[str, Path]]
) -> tuple[list[tuple[str, ast.AST]], ActionResult | None]:
    """Parse each (name, path); the trees, or the first failure."""
    parsed: list[tuple[str, ast.AST]] = []
    for src, src_path in to_parse:
        try:
            # Decoded as UTF-8 explicitly, not via the locale encoding:
            # Python source is UTF-8 by default (PEP 3120), and a
            # locale-dependent read makes this check platform-dependent
            # -- a single-byte locale like cp1252 decodes arbitrary
            # bytes, so a binary file reaches ast.parse and reports a
            # confusing syntax error instead of "not readable".
            tree = ast.parse(
                src_path.read_text(encoding="utf-8"), filename=str(src_path)
            )
        except SyntaxError as e:
            return parsed, ActionResult(
                target.label, False, f"{src}: syntax error: {e}"
            )
        except (UnicodeDecodeError, ValueError) as e:
            return parsed, ActionResult(
                target.label, False, f"{src}: not readable as Python source: {e}"
            )
        parsed.append((src, tree))
    return parsed, None


def run_test(target: Target, root: Path, env: ImportEnv | None = None) -> ActionResult:
    """Run a test target's source files via `python3 -m unittest`, or
    `python3 -m pytest` for a target declaring `runner = "pytest"`.

    Each src gets the target's own `timeout` if it declares one, else
    TEST_TIMEOUT_SECONDS. Read at call time rather than bound as a
    default argument, so a patched module constant is honoured."""
    validation = validate_target(target, root, env)
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
    missing_runner: list[str] = []

    timeout = target.timeout if target.timeout is not None else TEST_TIMEOUT_SECONDS

    child_env = os.environ.copy()
    root_str = str(root.resolve())
    existing_pythonpath = child_env.get("PYTHONPATH")
    child_env["PYTHONPATH"] = (
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
        if target.runner == "pytest":
            # pytest takes the file path rather than a dotted module.
            # `-p no:cacheprovider` stops it writing .pytest_cache into
            # the package: lirk keeps its own cache, and a tool that
            # writes into the source tree as a side effect of a test run
            # is how inputs start changing underneath their fingerprint.
            #
            # --rootdir and --confcutdir pin pytest to the repo root. Left
            # to itself, pytest run from the package directory takes that
            # directory as rootdir and stops loading conftest.py files
            # there -- so a root conftest lirk fingerprints (pytest_inputs)
            # was silently never loaded. Found by the slingshot repo, where
            # a seeding guard in the root conftest was inactive under lirk
            # while its tests passed. confcutdir also stops pytest loading
            # a conftest from *above* the repo, which lirk does not see.
            root_str = str(root.resolve())
            argv = [
                sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
                f"--rootdir={root_str}", f"--confcutdir={root_str}", src,
            ]
        else:
            argv = [sys.executable, "-m", "unittest", module]
        try:
            proc = subprocess.run(
                argv,
                cwd=pkg_dir,
                capture_output=True,
                text=True,
                env=child_env,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            # Recorded and carried on, not returned: bailing out here
            # let one hung src hide every src after it, which is the
            # asymmetry accumulating failures was meant to remove. A
            # hung test often does mean the whole target is wedged, but
            # that is a guess, and guessing costs the other results.
            stdout_parts.append(_as_text(e.stdout))
            stderr_parts.append(_as_text(e.stderr))
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
        if target.runner == "pytest":
            # pytest's own, version-stable signal: exit 5 means nothing
            # was collected. Unlike unittest on 3.11, it never exits 0
            # for an empty module, so the exit code is enough.
            ran_no_tests = proc.returncode == 5
            if _pytest_missing(proc.stderr):
                missing_runner.append(module)
        else:
            ran_no_tests = _ran_zero_tests(proc.stderr)
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
                f" -- timed out after {timeout}s: "
                f"{', '.join(timed_out)}"
            )
        if ran_nothing:
            detail += f" -- contained no tests: {', '.join(ran_nothing)}"
        if missing_runner:
            detail += f" -- pytest is not installed for {sys.executable}"
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
