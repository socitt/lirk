"""`lirk verify --mutate`: find dependencies a test has but doesn't declare.

The import check proves `deps` covers every `import` and every module a
test runs with `-m`. It can't see code loaded by a computed file path
(`importlib.util.spec_from_file_location(name, HERE / "runner.py")`), or
any other indirection. Such an edge is missing from the fingerprint, so
breaking the code leaves the dependent test `cached` and green. That
happened in terminal-projects (furminal loads region-explorer by path),
whose own sweep script this command is based on.

So this checks behaviour instead of reading code. In a throwaway copy
of the repo, each library source is broken in turn, and every test that
claims *not* to depend on it is run. A test that fails anyway does
depend on it, without declaring so.

Cost is roughly (library sources) x (tests per source that don't depend
on it) test runs, so it is a periodic audit rather than an every-run
check; `--sample N` limits it to N random sources. Like everything else
in lirk, the runs are serial, one subprocess per test file.
"""

from __future__ import annotations

import hashlib
import random
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from lirk.actions import owner_index, run_test
from lirk.cache import CACHE_FILENAME, compute_fingerprints, load_cache, save_cache
from lirk.graph import Graph, build_graph, topological_sort, transitive_closure

# Cache keys for pairs that checked clean: "mutate:<test label>|<src>".
MUTATE_PREFIX = "mutate:"

# Prepended to a source to break it. A top-level raise fails any import
# or load of the file, however it is reached. (Before a `from __future__`
# import it is a SyntaxError instead, which fails the load just as well.)
BREAK = 'raise RuntimeError("deliberately broken by lirk verify --mutate")\n'


@dataclass
class Edge:
    test: str       # label of the test that failed
    src: str        # repo-relative path of the broken source
    owners: list[str]  # targets declaring that source


def _copy_repo(root: Path, dest: Path) -> None:
    """Copy the repo, minus what can't matter and could be huge: hidden
    directories (.git, .venv), caches and lirk's own cache files."""

    def ignore(directory: str, names: list[str]) -> list[str]:
        here = Path(directory)
        return [
            n for n in names
            if n == "__pycache__"
            or n.endswith(".pyc")
            or n.startswith(".lirk-cache")
            or (n.startswith(".") and (here / n).is_dir())
        ]

    shutil.copytree(root, dest, ignore=ignore, symlinks=True)


def _pair_stamp(src_bytes: bytes, test_fingerprint: str) -> str:
    return hashlib.sha256(src_bytes + b"\0" + test_fingerprint.encode()).hexdigest()


def find_undeclared_edges(
    root: Path,
    tests: list[str],
    sample: int | None = None,
    seed: int | None = None,
    force: bool = False,
    report=print,
) -> tuple[list[Edge], list[str]]:
    """Run the audit. Returns (undeclared edges, tests excluded because
    they fail even unbroken). `tests` are labels of test targets.

    Incremental unless `force`: a (source, test) pair that checked clean
    is recorded in .lirk-cache.json with a stamp of the source's bytes
    and the test's fingerprint, and skipped while both are unchanged.
    The test's fingerprint covers everything it declares (plus the
    Python environment); anything it loads *without* declaring is what
    this command reports, so once a run comes back clean the stamp
    covers all the test can reach. Only clean pairs are recorded: a
    finding is always rechecked.
    """
    with tempfile.TemporaryDirectory(prefix="lirk-mutate-") as tmp:
        copy = Path(tmp) / "repo"
        _copy_repo(root, copy)
        graph: Graph = build_graph(copy)

        cache_path = root / CACHE_FILENAME
        cache = load_cache(cache_path)
        fingerprints = compute_fingerprints(graph, copy, topological_sort(graph))

        report(f"lirk: baseline: running {len(tests)} test target(s) unchanged")
        passing, failing = [], []
        for label in tests:
            (passing if run_test(graph.targets[label], copy).ok else failing).append(label)

        owners = owner_index(graph.targets, copy)
        closures = {t: transitive_closure(graph, {t}) for t in passing}
        sources = sorted(
            {
                (copy / target.package / src).resolve()
                for target in graph.targets.values()
                if target.type == "library"
                for src in target.srcs
            }
        )
        if sample is not None and sample < len(sources):
            if seed is None:
                seed = random.SystemRandom().randrange(2**32)
            report(f"lirk: sampling {sample} of {len(sources)} sources (seed {seed})")
            sources = sorted(random.Random(seed).sample(sources, sample))

        copy_resolved = copy.resolve()
        plan = []
        skipped_pairs = 0
        for path in sources:
            rel = path.relative_to(copy_resolved).as_posix()
            data = path.read_bytes()
            candidates = []
            for t in passing:
                if closures[t] & owners[path]:
                    continue
                key = f"{MUTATE_PREFIX}{t}|{rel}"
                if not force and cache.get(key) == _pair_stamp(data, fingerprints[t]):
                    skipped_pairs += 1
                    continue
                candidates.append(t)
            if candidates:
                plan.append((path, rel, data, candidates))
        runs = sum(len(c) for *_, c in plan)
        if skipped_pairs:
            report(f"lirk: skipping {skipped_pairs} pair(s) unchanged since they "
                   "last checked clean (--force rechecks them)")
        report(f"lirk: breaking {len(plan)} source(s) in turn: {runs} test run(s)")

        edges: list[Edge] = []
        clean: dict[str, str] = {}
        for index, (path, rel, data, candidates) in enumerate(plan, start=1):
            started = time.monotonic()
            original = data.decode("utf-8")
            path.write_text(BREAK + original, encoding="utf-8")
            found_here = 0
            try:
                for test in candidates:
                    if run_test(graph.targets[test], copy).ok:
                        clean[f"{MUTATE_PREFIX}{test}|{rel}"] = _pair_stamp(data, fingerprints[test])
                        continue
                    edge = Edge(test, rel, sorted(owners[path]))
                    edges.append(edge)
                    found_here += 1
                    report(
                        f"  STALE  {test} depends on {rel} "
                        f"({', '.join(edge.owners)}) without declaring it"
                    )
            finally:
                path.write_text(original, encoding="utf-8")
            # One line per source, so a long run never looks hung -- on a
            # phone this can take a long time.
            report(
                f"  [{index}/{len(plan)}] {rel}: {len(candidates)} test(s), "
                f"{found_here} finding(s), {time.monotonic() - started:.1f}s"
            )

        # Re-read before writing: a lirk run may have saved meanwhile.
        if clean:
            latest = load_cache(cache_path)
            latest.update(clean)
            save_cache(cache_path, latest)
        return edges, failing
