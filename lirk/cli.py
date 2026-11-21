"""The `lirk` command line: `build` and `test` over one or more target
labels or patterns, and `clean`. Output is kept compact -- this runs in
a narrow phone terminal.

Label forms accepted on the command line:

- `//pkg:name`  -- exactly that target.
- `//pkg:all`   -- every target in package `pkg` (`//:all` for the root
  package). An actual target named `all` takes precedence.
- `//pkg/...`   -- every target in `pkg` and all packages beneath it.
- `//...`       -- every target in the repo.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from lirk.actions import (
    ImportEnv,
    missing_files,
    owner_index,
    run_test,
    validate_target,
)
from lirk.cache import (
    CACHE_FILENAME,
    CacheError,
    compute_fingerprints,
    load_cache,
    needs_build,
    save_cache,
)
from lirk.graph import Graph, GraphError, build_graph, topological_sort, transitive_closure
from lirk.targets import ROOT_MARKER, ConfigError

ALL_TARGETS = "//..."
RECURSIVE_SUFFIX = "/..."
PACKAGE_WILDCARD = "all"


class LabelError(Exception):
    """A command-line label or pattern is malformed or matches nothing."""


def _expand_pattern(graph: Graph, pattern: str) -> tuple[set[str], bool]:
    """Labels one command-line argument names, and whether it was a
    wildcard (as opposed to naming a single target explicitly).

    The distinction matters to `lirk test`: a wildcard quietly narrows to
    the test targets it covers, while an explicit non-test label is an
    error, exactly as before patterns existed.
    """
    if not pattern.startswith("//"):
        raise LabelError(
            f"invalid label {pattern!r}: command-line labels must be absolute "
            "(start with '//')"
        )

    if pattern == ALL_TARGETS:
        return set(graph.targets), True

    if pattern.endswith(RECURSIVE_SUFFIX) and ":" not in pattern:
        prefix = pattern[2 : -len(RECURSIVE_SUFFIX)].strip("/")
        matched = {
            label
            for label, t in graph.targets.items()
            if t.package == prefix or t.package.startswith(prefix + "/")
        }
        if not matched:
            raise LabelError(f"pattern {pattern} matches no targets")
        return matched, True

    if pattern in graph.targets:
        return {pattern}, False

    package, sep, name = pattern[2:].rpartition(":")
    if sep and name == PACKAGE_WILDCARD:
        matched = {l for l, t in graph.targets.items() if t.package == package}
        if not matched:
            raise LabelError(f"pattern {pattern} matches no targets")
        return matched, True

    if not sep or not name:
        raise LabelError(
            f"malformed label {pattern!r}: expected //package:name, "
            "//package:all, //package/... or //..."
        )
    raise LabelError(f"unknown target: {pattern}")


def _select_roots(graph: Graph, patterns: list[str], mode: str) -> set[str]:
    """Union of every pattern's labels, narrowed for `test` mode.

    Raises LabelError for a malformed pattern, one matching nothing, or
    (in test mode) an explicit label naming a non-test target.
    """
    roots: set[str] = set()
    for pattern in patterns:
        matched, wildcard = _expand_pattern(graph, pattern)
        if mode == "test":
            if not wildcard:
                (label,) = matched
                type_ = graph.targets[label].type
                if type_ != "test":
                    raise LabelError(f"{label} is type {type_!r}, not 'test'")
            matched = {l for l in matched if graph.targets[l].type == "test"}
        roots |= matched
    return roots


def _discover_root(start: Path) -> Path:
    """Walk upward from `start` for a `.lirk-root` marker file naming
    the repo root explicitly.

    Falls back to `start` unchanged if no marker is found in any
    ancestor, so repos that haven't added the marker keep today's
    cwd-as-root behavior -- this only changes anything for repos that
    opt in.
    """
    for candidate in (start, *start.parents):
        if (candidate / ROOT_MARKER).is_file():
            return candidate
    return start


def _load_graph(root: Path) -> tuple[Graph, list[str]] | None:
    try:
        graph = build_graph(root)
        order = topological_sort(graph)
    except (ConfigError, GraphError) as e:
        print(f"lirk: {e}", file=sys.stderr)
        # Naming the root here is the difference between a legible error
        # and a wild goose chase. A `//` label means nothing without it:
        # run from a package subdirectory with no marker in sight and
        # that package silently becomes the root, so the failure reads
        # as "dependency //orrery:orrery does not exist" when the real
        # fault is that //orrery is no longer inside the repo.
        print(f"lirk: repo root is {root}", file=sys.stderr)
        return None
    return graph, order


@dataclass
class ExecutionSummary:
    built: int = 0
    cached: int = 0
    failed: int = 0
    skipped: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_cached: int = 0
    tests_skipped: int = 0
    # Labels that actually FAILed, in the order reported. Skipped
    # dependents are deliberately not in here: they are consequences,
    # and listing them buries the labels worth acting on.
    failures: list[str] = field(default_factory=list)

    @property
    def tests_total(self) -> int:
        return (
            self.tests_passed
            + self.tests_failed
            + self.tests_cached
            + self.tests_skipped
        )


def _execute(
    root: Path, graph: Graph, order: list[str], mode: str, force: bool = False
) -> tuple[bool, ExecutionSummary]:
    """Validate (and, in 'test' mode, run) each target in `order`.

    `mode` ('build' or 'test') namespaces the cache: `lirk build`
    merely validating a test target's files must not count as
    `lirk test` having actually run and passed it, so the two modes
    never share a cache entry for the same target.

    `force`, if set, skips the cache check so every target is
    re-validated/re-run regardless of its fingerprint, without
    touching the cache file itself.

    Returns (ok, summary): `ok` is True iff everything succeeded.
    Only successful results are written to the cache, so a failure is
    retried on the next run even if its fingerprint hasn't changed.
    """
    cache_path = root / CACHE_FILENAME
    cache = load_cache(cache_path)

    ok = True
    summary = ExecutionSummary()

    # Built from the whole graph, not `order`: a target may import from
    # a package outside the requested subset, and that is exactly the
    # case worth catching.
    owners = owner_index(graph.targets, root)

    # Check every target's declared files exist before fingerprinting
    # anything: compute_fingerprints reads file contents unconditionally,
    # so a missing file reached from there would otherwise surface as an
    # unguarded traceback instead of the clean per-target failure below.
    #
    # A target with missing files is marked failed rather than aborting
    # the whole run -- a stale filename in one package must not stop
    # every unrelated target in the repo. Its dependents are skipped by
    # the same dep_failure branch that handles an execution failure.
    failed: set[str] = set()
    for label in order:
        target = graph.targets[label]
        missing = missing_files(target, root)
        if not missing:
            continue
        ok = False
        failed.add(label)
        summary.failed += 1
        summary.failures.append(label)
        if mode == "test" and target.type == "test":
            summary.tests_failed += 1
        print(
            f"  FAIL   {label}: missing source file(s): {', '.join(missing)}",
            flush=True,
        )

    # compute_fingerprints reads every dependency's fingerprint, so a
    # target is only fingerprintable if its whole dependency closure is.
    # `order` is topological, so one forward pass propagates exclusion to
    # every transitive dependent.
    excluded = set(failed)
    for label in order:
        if label not in excluded and any(d in excluded for d in graph.edges[label]):
            excluded.add(label)

    try:
        fingerprints = compute_fingerprints(
            graph, root, [l for l in order if l not in excluded]
        )
    except CacheError as e:
        print(f"lirk: {e}", file=sys.stderr)
        summary.failed += 1
        return False, summary

    for label in order:
        target = graph.targets[label]
        cache_key = f"{mode}:{label}"
        is_test = mode == "test" and target.type == "test"

        if label in failed:
            # A preflight missing-file failure, already reported above.
            continue

        dep_failure = next((d for d in graph.edges[label] if d in failed), None)
        if dep_failure is not None:
            ok = False
            failed.add(label)
            summary.skipped += 1
            if is_test:
                summary.tests_skipped += 1
            print(f"  SKIP   {label}: dependency {dep_failure} failed", flush=True)
            continue

        fp = fingerprints[label]

        if not force and not needs_build(cache_key, fp, cache):
            print(f"  cached  {label}", flush=True)
            summary.cached += 1
            if is_test:
                summary.tests_cached += 1
            continue

        env = ImportEnv(owners=owners, allowed=transitive_closure(graph, {label}))

        if is_test:
            result = run_test(target, root, env)
            verb = "PASS" if result.ok else "FAIL"
        else:
            result = validate_target(target, root, env)
            verb = "built" if result.ok else "FAIL"

        if result.ok:
            cache[cache_key] = fp
            print(f"  {verb:6} {label}", flush=True)
            if is_test:
                summary.tests_passed += 1
            else:
                summary.built += 1
            # Saved after every successful target, not just at the end
            # of the loop, so an interruption (Ctrl-C, SIGTERM, an
            # iSH-AOK crash) never discards results already computed.
            save_cache(cache_path, cache)
        else:
            ok = False
            failed.add(label)
            summary.failed += 1
            summary.failures.append(label)
            if is_test:
                summary.tests_failed += 1
            print(f"  {verb:6} {label}: {result.message}", flush=True)
            for stream in (result.stdout, result.stderr):
                if stream.strip():
                    print(stream.rstrip(), flush=True)

    save_cache(cache_path, cache)
    return ok, summary


def _print_failures(summary: ExecutionSummary) -> None:
    """Restate which targets failed, just above the counts.

    Not a summarizing layer over test output (a settled non-goal): this
    reprints labels lirk itself already printed and touches nothing about
    the captured stdout/stderr. It exists because the per-target FAIL
    line scrolls off above a unittest traceback, leaving a counts-only
    summary on screen -- on a phone terminal, recovering a label you
    already saw means scrolling back through the whole dump.
    """
    if not summary.failures:
        return
    print("lirk: failed:")
    for label in summary.failures:
        print(f"  {label}")


def _resolve_roots(
    root: Path, labels: list[str], mode: str
) -> tuple[Graph, list[str], set[str]] | None:
    """Load the graph and expand `labels`, printing any error."""
    loaded = _load_graph(root)
    if loaded is None:
        return None
    graph, order = loaded
    try:
        roots = _select_roots(graph, labels, mode)
    except LabelError as e:
        print(f"lirk: {e}", file=sys.stderr)
        print(f"lirk: repo root is {root}", file=sys.stderr)
        return None
    return graph, order, roots


def cmd_build(root: Path, labels: list[str], force: bool = False) -> int:
    resolved = _resolve_roots(root, labels, "build")
    if resolved is None:
        return 1
    graph, order, roots = resolved

    closure = transitive_closure(graph, roots)
    subset_order = [l for l in order if l in closure]

    ok, summary = _execute(root, graph, subset_order, mode="build", force=force)
    _print_failures(summary)
    print(
        f"lirk: {summary.built} built, {summary.cached} cached, "
        f"{summary.failed} failed, {summary.skipped} skipped"
    )
    print("lirk: OK" if ok else "lirk: FAILED")
    return 0 if ok else 1


def cmd_test(root: Path, labels: list[str], force: bool = False) -> int:
    resolved = _resolve_roots(root, labels, "test")
    if resolved is None:
        return 1
    graph, order, roots = resolved

    if not roots:
        # Only reachable through wildcards: an explicit label is either
        # a test target or already an error. A pattern that matched
        # targets, none of them tests, is not a failure -- there was
        # simply nothing to run.
        print("lirk: no test targets found")
        return 0

    closure = transitive_closure(graph, roots)
    subset_order = [l for l in order if l in closure]

    ok, summary = _execute(root, graph, subset_order, mode="test", force=force)
    _print_failures(summary)
    passed = summary.tests_passed + summary.tests_cached
    print(f"lirk: {passed}/{summary.tests_total} tests passed")
    print("lirk: OK" if ok else "lirk: FAILED")
    return 0 if ok else 1


def cmd_clean(root: Path) -> int:
    """Delete the incremental-build cache, and any temp file an
    interrupted save left beside it.

    The next run rebuilds and reruns everything. Unlike `--force`, which
    bypasses the cache for one run without touching it, this discards
    it. Nothing outside the cache files is touched: lirk writes nothing
    else into the repo (the __pycache__ directories are Python's own).
    """
    cache_path = root / CACHE_FILENAME
    removed = []
    for path in [cache_path, *sorted(root.glob(f"{CACHE_FILENAME}.*.tmp"))]:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(path.name)
    if removed:
        print(f"lirk: removed {', '.join(removed)}")
    else:
        print(f"lirk: no cache to remove in {root}")
    return 0


class _VersionAction(argparse.Action):
    """`--version`, with the lookup deferred until it's actually asked for.

    argparse's built-in version action needs the string up front, which
    would import importlib.metadata and stat the installed distribution
    on every single invocation. Startup cost is already the dominant
    per-invocation expense (DESIGN.md S6), so it isn't paid for a flag
    almost no run uses.
    """

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        from importlib.metadata import PackageNotFoundError, version

        try:
            print(f"lirk {version('lirk')}")
        except PackageNotFoundError:
            # Running from a checkout via bin/lirk rather than an
            # install. Saying so beats printing a version that would be
            # a guess about which source tree is in use.
            print("lirk (not installed; running from a source checkout)")
        parser.exit()


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lirk")
    # On the top-level parser, so `lirk --version` works without naming
    # a subcommand -- the subparser is required, and the whole point of
    # the flag is that it answers before you know what you're running.
    parser.add_argument(
        "--version", action=_VersionAction, help="print the installed version and exit"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    root_help = (
        "repo root (default: nearest ancestor of cwd containing a "
        f"{ROOT_MARKER} marker file, else cwd itself)"
    )

    label_help = "one or more of //pkg:name, //pkg:all, //pkg/..., //..."

    build_p = sub.add_parser("build", help="validate targets and their deps")
    build_p.add_argument("labels", nargs="+", metavar="label", help=label_help)
    build_p.add_argument(
        "--force", "--rebuild", action="store_true", dest="force",
        help="bypass the cache and re-validate every target in scope",
    )
    build_p.add_argument("--root", type=Path, default=None, help=root_help)

    test_p = sub.add_parser("test", help="run test targets")
    test_p.add_argument("labels", nargs="+", metavar="label", help=label_help)
    test_p.add_argument(
        "--force", "--rerun", action="store_true", dest="force",
        help="bypass the cache and re-run every test in scope",
    )
    test_p.add_argument("--root", type=Path, default=None, help=root_help)

    clean_p = sub.add_parser("clean", help="delete the incremental-build cache")
    clean_p.add_argument("--root", type=Path, default=None, help=root_help)

    args = parser.parse_args(argv)
    if root is None:
        if args.root is not None:
            root = args.root
        else:
            root = _discover_root(Path.cwd())
            if not (root / ROOT_MARKER).is_file():
                # Announced, not silent: without a marker, `//` means
                # whatever directory you happen to be standing in, and
                # from the repo root that looks identical to working
                # correctly. The failure it produces one directory down
                # points at a dependency, never at the root -- which has
                # now confused two separate projects.
                print(
                    f"lirk: no {ROOT_MARKER} found in any parent directory; "
                    f"using the current directory as the repo root: {root}",
                    file=sys.stderr,
                )

    if args.command == "build":
        return cmd_build(root, args.labels, force=args.force)
    if args.command == "clean":
        return cmd_clean(root)
    return cmd_test(root, args.labels, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
