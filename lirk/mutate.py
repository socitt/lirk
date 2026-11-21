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

import random
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from lirk.actions import owner_index, run_test
from lirk.graph import Graph, build_graph, transitive_closure

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


def find_undeclared_edges(
    root: Path,
    tests: list[str],
    sample: int | None = None,
    seed: int | None = None,
    report=print,
) -> tuple[list[Edge], list[str]]:
    """Run the audit. Returns (undeclared edges, tests excluded because
    they fail even unbroken). `tests` are labels of test targets."""
    with tempfile.TemporaryDirectory(prefix="lirk-mutate-") as tmp:
        copy = Path(tmp) / "repo"
        _copy_repo(root, copy)
        graph: Graph = build_graph(copy)

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

        plan = [
            (path, [t for t in passing if not (closures[t] & owners[path])])
            for path in sources
        ]
        runs = sum(len(candidates) for _, candidates in plan)
        report(f"lirk: breaking {len(plan)} source(s) in turn: {runs} test run(s)")

        copy_resolved = copy.resolve()
        edges: list[Edge] = []
        for path, candidates in plan:
            if not candidates:
                continue
            rel = path.relative_to(copy_resolved).as_posix()
            original = path.read_text(encoding="utf-8")
            path.write_text(BREAK + original, encoding="utf-8")
            try:
                for test in candidates:
                    if not run_test(graph.targets[test], copy).ok:
                        edge = Edge(test, rel, sorted(owners[path]))
                        edges.append(edge)
                        report(
                            f"  STALE  {test} depends on {rel} "
                            f"({', '.join(edge.owners)}) without declaring it"
                        )
            finally:
                path.write_text(original, encoding="utf-8")
        return edges, failing
