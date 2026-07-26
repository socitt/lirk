"""Content-hash fingerprints and the local incremental-build cache.

A target's fingerprint covers its own declared shape (name, type,
deps) plus the contents of its source files plus the fingerprints of
its dependencies, so any change propagates to every dependent target.
Fingerprints are compared against a cache of the last successful
build/test run (.lirk-cache.json) to decide what can be skipped.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lirk.graph import Graph

CACHE_FILENAME = ".lirk-cache.json"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_fingerprints(
    graph: Graph, root: Path, order: list[str]
) -> dict[str, str]:
    """Compute a content fingerprint per target.

    `order` must be a topological order (dependencies before
    dependents) so each dependency's fingerprint is already known
    when its dependents are processed.
    """
    fingerprints: dict[str, str] = {}

    for label in order:
        target = graph.targets[label]
        h = hashlib.sha256()
        h.update(target.name.encode())
        h.update(target.type.encode())

        for src in sorted(target.srcs):
            src_path = root / target.package / src
            h.update(src.encode())
            h.update(_hash_file(src_path).encode())

        for dep in sorted(graph.edges[label]):
            h.update(dep.encode())
            h.update(fingerprints[dep].encode())

        fingerprints[label] = h.hexdigest()

    return fingerprints


def load_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_cache(path: Path, fingerprints: dict[str, str]) -> None:
    path.write_text(json.dumps(fingerprints, indent=2, sort_keys=True) + "\n")


def needs_build(label: str, fingerprint: str, cache: dict[str, str]) -> bool:
    return cache.get(label) != fingerprint
