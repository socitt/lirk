"""Content-hash fingerprints and the local incremental-build cache.

A target's fingerprint covers its own declared shape (name, type,
deps) plus the contents of its source files plus the fingerprints of
its dependencies, so any change propagates to every dependent target.
Every fingerprint also folds in the Python environment the actions run
under (see environment_fingerprint).
Fingerprints are compared against a cache of the last successful
build/test run (.lirk-cache.json) to decide what can be skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import site
import sys
from pathlib import Path

from lirk.graph import Graph
from lirk.targets import DEFAULT_RUNNER, pytest_inputs

CACHE_FILENAME = ".lirk-cache.json"


class CacheError(Exception):
    """A file needed to compute a fingerprint could not be read."""


# Bump this whenever the behaviour of `validate_target` or `run_test`
# changes, so existing caches are invalidated instead of trusting a
# green result computed under different rules.
ACTION_VERSION = 14


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


def _site_dirs() -> list[str]:
    """The interpreter's site-packages directories, system and user.

    getattr-guarded: some embedded and very old virtualenv builds of
    `site` lack one or both functions.
    """
    dirs: list[str] = []
    get_global = getattr(site, "getsitepackages", None)
    if get_global is not None:
        dirs.extend(get_global())
    get_user = getattr(site, "getusersitepackages", None)
    if get_user is not None:
        dirs.append(get_user())
    return dirs


def _installed_distributions(site_dirs: list[str]) -> list[str]:
    """Every installed distribution, as its metadata directory name.

    Those names carry the version (`requests-2.31.0.dist-info`), so a
    listing is enough to see an install, an upgrade or a removal --
    one directory read per site dir, rather than importlib.metadata,
    which would add to the startup cost DESIGN.md §6 keeps off the
    common path. A missing or unreadable directory contributes nothing:
    it holds no packages to go stale.
    """
    found: set[str] = set()
    for directory in site_dirs:
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        found.update(
            n for n in names if n.endswith((".dist-info", ".egg-info"))
        )
    return sorted(found)


def environment_fingerprint(site_dirs: list[str] | None = None) -> str:
    """A hash of the Python environment that builds and tests run under.

    Tests execute under sys.executable, so the interpreter and the
    packages installed for it are as much inputs as the srcs are -- but
    none of them are files in the repo. Without this, upgrading Python
    or a library left every target `cached` and green: a stale PASS
    that --force could turn into a FAIL, the exact defect class v1
    criterion 2 forbids. ast.parse depends on the interpreter version
    too (new syntax), so build results are covered as well as tests.

    Conservative by design: any patch release or any package change
    reruns everything once. Erring toward redundant work, never toward
    a false pass, is the direction DESIGN.md §4 requires.
    """
    h = hashlib.sha256()
    h.update(sys.implementation.name.encode())
    h.update(".".join(map(str, sys.version_info[:3])).encode())
    dirs = _site_dirs() if site_dirs is None else site_dirs
    for dist in _installed_distributions(dirs):
        h.update(dist.encode())
        h.update(b"\0")
    return h.hexdigest()


def compute_fingerprints(
    graph: Graph, root: Path, order: list[str], environment: str | None = None
) -> dict[str, str]:
    """Compute a content fingerprint per target.

    `order` must be a topological order (dependencies before
    dependents) so each dependency's fingerprint is already known
    when its dependents are processed.

    `environment` defaults to environment_fingerprint(), computed once
    per call; it is a parameter so tests can hold it fixed or vary it.
    """
    if environment is None:
        environment = environment_fingerprint()
    fingerprints: dict[str, str] = {}

    for label in order:
        target = graph.targets[label]
        h = hashlib.sha256()
        h.update(target.name.encode())
        h.update(target.type.encode())
        h.update(str(ACTION_VERSION).encode())
        h.update(environment.encode())
        if target.timeout is not None:
            # Folded in only when set, so targets without one keep the
            # fingerprint shape they always had. A pass under a 600s
            # budget says nothing about a 5s one, so changing it must
            # invalidate the cached result.
            h.update(f"timeout={target.timeout}".encode())
        if target.runner != DEFAULT_RUNNER:
            # Same rule as timeout: absent for default-runner targets, so
            # their fingerprints are unchanged. A pytest target also
            # folds in the conftest/config files pytest reads, which are
            # not srcs but change what the tests do.
            h.update(f"runner={target.runner}".encode())
            for path in pytest_inputs(target, root):
                rel = path.relative_to(root.resolve()).as_posix()
                h.update(f"pytest-input={rel}".encode())
                h.update(_hash_file(path, label).encode())

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
    """`cache_key` is "build:<label>" (the target validates, whichever
    command checked it) or "test:<label>" (a test target's tests ran
    and passed) -- never a bare label."""
    return cache.get(cache_key) != fingerprint
