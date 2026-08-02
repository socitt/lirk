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
import os
from pathlib import Path

from lirk.graph import Graph

CACHE_FILENAME = ".lirk-cache.json"


class CacheError(Exception):
    """A file needed to compute a fingerprint could not be read."""


# Bump this whenever the behaviour of `validate_target` or `run_test`
# changes, so existing caches are invalidated instead of trusting a
# green result computed under different rules.
ACTION_VERSION = 8


def _hash_file(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as e:
        raise CacheError(f"{label}: cannot read {path}: {e}") from e


def _directory_entries(directory: Path) -> list[tuple[str, Path]]:
    """Every file under a `data` directory, as (posix relative path, path),
    sorted by that path so the fingerprint doesn't depend on filesystem
    iteration order.

    Skips dot-prefixed and __pycache__ segments. Both are generated
    rather than declared: a fixture tree containing Python accumulates
    .pyc files as a side effect of *running the very tests* whose
    fingerprint this feeds, which would change the input on every run
    and mean nothing was ever cached.
    """
    entries = []
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(directory)
        if any(p.startswith(".") or p == "__pycache__" for p in rel.parts):
            continue
        entries.append((rel.as_posix(), path))
    return sorted(entries)


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
            if data_path.is_dir():
                # The relative path of each file goes into the hash, not
                # just its contents, so adding or removing a file in the
                # tree changes the fingerprint even if nothing is edited.
                for rel, file_path in _directory_entries(data_path):
                    h.update(rel.encode())
                    h.update(_hash_file(file_path, label).encode())
            else:
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
    # Write to a sibling temp file and rename it into place, so an
    # interrupted write can never leave a truncated cache -- os.replace
    # is atomic, unlike write_text directly to `path`.
    #
    # The PID is in the temp filename because two concurrent lirk runs
    # would otherwise write the same path and could replace each
    # other's partially-written file. That does not make concurrent
    # runs safe -- load/save is still an unlocked read-modify-write, so
    # overlapping runs can lose one run's entries -- but a lost entry
    # only costs a redundant rebuild, whereas a torn temp file is a
    # corrupt cache.
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(fingerprints, indent=2, sort_keys=True) + "\n")
    os.replace(tmp_path, path)


def needs_build(cache_key: str, fingerprint: str, cache: dict[str, str]) -> bool:
    """`cache_key` is "<mode>:<label>", not a bare label -- build and
    test results for one target are cached separately."""
    return cache.get(cache_key) != fingerprint
