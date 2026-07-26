"""Dependency graph construction and topological sort over BUILD.lirk
targets.

A repo is scanned for BUILD.lirk files; each declares targets scoped
to its own package (the directory it lives in, relative to the repo
root). Dependencies reference other targets by label:

- ``//path/to/pkg:name`` — absolute, from the repo root.
- ``:name``              — relative, another target in the same package.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lirk.targets import BUILD_FILENAME, Target, parse_build_file


class GraphError(Exception):
    """Bad labels, missing dependencies, self-deps, or dependency cycles."""


def find_build_files(root: Path) -> list[Path]:
    return sorted(root.rglob(BUILD_FILENAME))


def package_for(build_file: Path, root: Path) -> str:
    rel_dir = build_file.parent.relative_to(root)
    return "" if rel_dir == Path(".") else rel_dir.as_posix()


def load_targets(root: Path) -> dict[str, Target]:
    """Parse every BUILD.lirk under root, keyed by fully-qualified label."""
    targets: dict[str, Target] = {}
    for build_file in find_build_files(root):
        package = package_for(build_file, root)
        for target in parse_build_file(build_file, package):
            if target.label in targets:
                raise GraphError(f"duplicate target label {target.label!r}")
            targets[target.label] = target
    return targets


def resolve_label(raw_dep: str, package: str) -> str:
    """Resolve a dep string to a fully-qualified ``//pkg:name`` label."""
    if raw_dep.startswith("//"):
        return raw_dep
    if raw_dep.startswith(":"):
        return f"//{package}{raw_dep}"
    raise GraphError(
        f"invalid dependency {raw_dep!r}: must start with '//' (absolute "
        f"label) or ':' (relative to its own package)"
    )


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
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {label: WHITE for label in graph.targets}
    order: list[str] = []
    stack: list[str] = []

    def visit(label: str) -> None:
        color[label] = GRAY
        stack.append(label)
        for dep in graph.edges[label]:
            if color[dep] == WHITE:
                visit(dep)
            elif color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                raise GraphError("circular dependency: " + " -> ".join(cycle))
        stack.pop()
        color[label] = BLACK
        order.append(label)

    for label in sorted(graph.targets):
        if color[label] == WHITE:
            visit(label)

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
