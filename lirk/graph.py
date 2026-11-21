"""Dependency graph construction and topological sort over BUILD.lirk
targets.

A repo is scanned for BUILD.lirk files; each declares targets scoped
to its own package (the directory it lives in, relative to the repo
root). Dependencies reference other targets by label:

- ``//path/to/pkg:name`` — absolute, from the repo root.
- ``:name``              — relative, another target in the same package.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from lirk.targets import BUILD_FILENAME, Target, load_ignores, parse_build_file


class GraphError(Exception):
    """Bad labels, missing dependencies, self-deps, or dependency cycles."""


def find_build_files(root: Path, ignore: Sequence[str] = ()) -> list[Path]:
    """Every BUILD.lirk under root, except under a dot-prefixed
    directory (.venv, node_modules/.bin, a nested checkout of lirk
    itself, etc.) -- checked relative to root, so root itself living
    under a dotted ancestor directory doesn't matter.

    `ignore` additionally excludes the given root-relative directories
    and everything beneath them; see targets.load_ignores.

    Excluded directories are pruned from the walk, not filtered out
    afterwards: a `.git` or `.venv` can hold tens of thousands of
    entries, and on iSH-AOK every stat is slow, so descending into a
    tree only to discard everything found there is the dominant cost
    of the scan. Symlinked directories are not followed, as before.
    """
    ignored = {Path(entry.strip("/")) for entry in ignore if entry.strip("/")}
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".") and (rel_dir / d) not in ignored
        ]
        if BUILD_FILENAME in filenames:
            found.append(Path(dirpath) / BUILD_FILENAME)
    return sorted(found)


def package_for(build_file: Path, root: Path) -> str:
    rel_dir = build_file.parent.relative_to(root)
    return "" if rel_dir == Path(".") else rel_dir.as_posix()


def load_targets(root: Path) -> dict[str, Target]:
    """Parse every BUILD.lirk under root, keyed by fully-qualified label."""
    targets: dict[str, Target] = {}
    for build_file in find_build_files(root, load_ignores(root)):
        package = package_for(build_file, root)
        for target in parse_build_file(build_file, package):
            if target.label in targets:
                raise GraphError(f"duplicate target label {target.label!r}")
            targets[target.label] = target
    return targets


def resolve_label(raw_dep: str, package: str) -> str:
    """Resolve a dep string to a fully-qualified ``//pkg:name`` label."""
    if raw_dep.startswith("//"):
        label = raw_dep
    elif raw_dep.startswith(":"):
        label = f"//{package}{raw_dep}"
    else:
        raise GraphError(
            f"invalid dependency {raw_dep!r}: must start with '//' (absolute "
            f"label) or ':' (relative to its own package)"
        )

    # A well-formed label is //pkg:name, where pkg may be empty (the
    # root package, e.g. //:name) but name may not.
    rest = label[2:]
    if rest.count(":") != 1:
        raise GraphError(
            f"malformed label {raw_dep!r}: expected exactly one ':' "
            "separating package from name"
        )
    if not rest.rpartition(":")[2]:
        raise GraphError(f"malformed label {raw_dep!r}: name part must not be empty")

    return label


@dataclass
class Graph:
    targets: dict[str, Target]
    edges: dict[str, tuple[str, ...]]  # label -> resolved dependency labels


def build_graph(root: Path) -> Graph:
    targets = load_targets(root)
    edges: dict[str, tuple[str, ...]] = {}

    for label, target in targets.items():
        resolved = []
        for raw_dep in target.deps:
            dep_label = resolve_label(raw_dep, target.package)
            if dep_label not in targets:
                raise GraphError(f"{label}: dependency {dep_label!r} does not exist")
            if dep_label == label:
                raise GraphError(f"{label}: target cannot depend on itself")
            resolved.append(dep_label)
        edges[label] = tuple(resolved)

    return Graph(targets=targets, edges=edges)


def topological_sort(graph: Graph) -> list[str]:
    """Order target labels so every dependency precedes its dependents.

    Raises GraphError (naming the full cycle) if the graph isn't a DAG.

    An iterative depth-first search with an explicit stack, producing
    exactly the order the obvious recursive version would. Recursion
    overflowed Python's ~1000-frame limit on a long enough dependency
    chain and escaped as a RecursionError traceback.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {label: WHITE for label in graph.targets}
    order: list[str] = []

    for start in sorted(graph.targets):
        if color[start] != WHITE:
            continue
        color[start] = GRAY
        # path[i] is the label at depth i, frames[i] its pending deps;
        # path doubles as the GRAY chain used to name a cycle.
        path = [start]
        frames = [iter(graph.edges[start])]
        while frames:
            dep = next(frames[-1], None)
            if dep is None:
                frames.pop()
                done = path.pop()
                color[done] = BLACK
                order.append(done)
            elif color[dep] == WHITE:
                color[dep] = GRAY
                path.append(dep)
                frames.append(iter(graph.edges[dep]))
            elif color[dep] == GRAY:
                cycle = path[path.index(dep):] + [dep]
                raise GraphError("circular dependency: " + " -> ".join(cycle))

    return order


def transitive_closure(graph: Graph, roots: set[str]) -> set[str]:
    """All labels reachable from `roots` by following dependency edges.

    `roots` themselves are included in the result.
    """
    closure: set[str] = set()
    stack = list(roots)
    while stack:
        label = stack.pop()
        if label in closure:
            continue
        closure.add(label)
        stack.extend(graph.edges[label])
    return closure
