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


class CacheError(Exception):
    """A file needed to compute a fingerprint could not be read."""


# Bump this whenever the behaviour of `validate_target` or `run_test`
# changes, so existing caches are invalidated instead of trusting a
# green result computed under different rules.
ACTION_VERSION = 4


def _hash_file(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as e:
        raise CacheError(f"{label}: cannot read {path}: {e}") from e


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
        h.update(str(ACTION_VERSION).encode())

        for src in sorted(target.srcs):
            src_path = root / target.package / src
            h.update(src.encode())
            h.update(_hash_file(src_path, label).encode())

        for data_file in sorted(target.data):
            data_path = root / target.package / data_file
            h.update(data_file.encode())
            h.update(_hash_file(data_path, label).encode())

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
