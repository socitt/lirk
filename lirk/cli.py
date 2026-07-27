"""The `lirk` command line: `build` and `test`, over a single target
label or `//...` for the whole repo. Output is kept compact -- this
runs in a narrow phone terminal.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from lirk.actions import missing_files, run_test, validate_target
from lirk.cache import (
    CACHE_FILENAME,
    CacheError,
    compute_fingerprints,
    load_cache,
    needs_build,
    save_cache,
)
from lirk.graph import Graph, GraphError, build_graph, topological_sort, transitive_closure
from lirk.targets import ConfigError

ALL_TARGETS = "//..."
ROOT_MARKER = ".lirk-root"


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
        return None
    return graph, order


@dataclass
class ExecutionSummary:
    built: int = 0
    cached: int = 0
    failed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_cached: int = 0

    @property
    def tests_total(self) -> int:
        return self.tests_passed + self.tests_failed + self.tests_cached


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

    # Check every target's declared files exist before fingerprinting
    # anything: compute_fingerprints reads file contents unconditionally,
    # so a missing file reached from there would otherwise surface as an
    # unguarded traceback instead of the clean per-target failure below.
    for label in order:
        target = graph.targets[label]
        missing = missing_files(target, root)
        if not missing:
            continue
        ok = False
        summary.failed += 1
        if mode == "test" and target.type == "test":
            summary.tests_failed += 1
        print(f"  FAIL   {label}: missing source file(s): {', '.join(missing)}")
    if not ok:
        return ok, summary

    try:
        fingerprints = compute_fingerprints(graph, root, order)
    except CacheError as e:
        print(f"lirk: {e}", file=sys.stderr)
        summary.failed += 1
        return False, summary

    for label in order:
        target = graph.targets[label]
        fp = fingerprints[label]
        cache_key = f"{mode}:{label}"
        is_test = mode == "test" and target.type == "test"

        if not force and not needs_build(cache_key, fp, cache):
            print(f"  cached  {label}")
            summary.cached += 1
            if is_test:
                summary.tests_cached += 1
            continue

        if is_test:
            result = run_test(target, root)
            verb = "PASS" if result.ok else "FAIL"
        else:
            result = validate_target(target, root)
            verb = "built" if result.ok else "FAIL"

        if result.ok:
            cache[cache_key] = fp
            print(f"  {verb:6} {label}")
            if is_test:
                summary.tests_passed += 1
            else:
                summary.built += 1
        else:
            ok = False
            summary.failed += 1
            if is_test:
                summary.tests_failed += 1
            print(f"  {verb:6} {label}: {result.message}")
            for stream in (result.stdout, result.stderr):
                if stream.strip():
                    print(stream.rstrip())

    save_cache(cache_path, cache)
    return ok, summary


def cmd_build(root: Path, label: str, force: bool = False) -> int:
    loaded = _load_graph(root)
    if loaded is None:
        return 1
    graph, order = loaded

    if label == ALL_TARGETS:
        roots = set(graph.targets)
    elif label in graph.targets:
        roots = {label}
    else:
        print(f"lirk: unknown target: {label}", file=sys.stderr)
        return 1

    closure = transitive_closure(graph, roots)
    subset_order = [l for l in order if l in closure]

    ok, summary = _execute(root, graph, subset_order, mode="build", force=force)
    print(
        f"lirk: {summary.built} built, {summary.cached} cached, "
        f"{summary.failed} failed"
    )
    print("lirk: OK" if ok else "lirk: FAILED")
    return 0 if ok else 1


def cmd_test(root: Path, label: str, force: bool = False) -> int:
    loaded = _load_graph(root)
    if loaded is None:
        return 1
    graph, order = loaded

    if label == ALL_TARGETS:
        roots = {l for l in graph.targets if graph.targets[l].type == "test"}
        if not roots:
            print("lirk: no test targets found")
            return 0
    elif label not in graph.targets:
        print(f"lirk: unknown target: {label}", file=sys.stderr)
        return 1
    elif graph.targets[label].type != "test":
        print(
            f"lirk: {label} is type {graph.targets[label].type!r}, not 'test'",
            file=sys.stderr,
        )
        return 1
    else:
        roots = {label}

    closure = transitive_closure(graph, roots)
    subset_order = [l for l in order if l in closure]

    ok, summary = _execute(root, graph, subset_order, mode="test", force=force)
    passed = summary.tests_passed + summary.tests_cached
    print(f"lirk: {passed}/{summary.tests_total} tests passed")
    print("lirk: OK" if ok else "lirk: FAILED")
    return 0 if ok else 1


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lirk")
    sub = parser.add_subparsers(dest="command", required=True)

    root_help = (
        "repo root (default: nearest ancestor of cwd containing a "
        f"{ROOT_MARKER} marker file, else cwd itself)"
    )

    build_p = sub.add_parser("build", help="validate a target and its deps")
    build_p.add_argument("label", help="//path:target or //...")
    build_p.add_argument(
        "--force", "--rebuild", action="store_true", dest="force",
        help="bypass the cache and re-validate every target in scope",
    )
    build_p.add_argument("--root", type=Path, default=None, help=root_help)

    test_p = sub.add_parser("test", help="run a test target")
    test_p.add_argument("label", help="//path:target or //...")
    test_p.add_argument(
        "--force", "--rerun", action="store_true", dest="force",
        help="bypass the cache and re-run every test in scope",
    )
    test_p.add_argument("--root", type=Path, default=None, help=root_help)

    args = parser.parse_args(argv)
    if root is None:
        root = args.root if args.root is not None else _discover_root(Path.cwd())

    if args.command == "build":
        return cmd_build(root, args.label, force=args.force)
    return cmd_test(root, args.label, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
