"""Time lirk on a generated repo, scenario by scenario.

Runs the real `lirk` CLI as a subprocess for each scenario, so the
numbers include interpreter startup, exactly as a user experiences them.
A fresh repo is generated first (see generate.py), so every run starts
from the same state.

Usage:
  python3 bench/run.py --shape mesh --packages 200
  python3 bench/run.py --shape deep --packages 500 --no-tests
  python3 bench/run.py --preset         # the standard set, as a table

Scenarios (in order, each on the state the previous one left):
  build-cold     first `lirk build //...`: every library checked
  build-cached   the same again: scan + fingerprint + all cached
  build-edit     one file edited at the bottom of the graph
  test-cold      first `lirk test //...`: every test file run
  test-cached    the same again
  verify-5       `lirk verify --sample 5`
  fix-dry        `lirk fix --dry-run`: the import check over the repo
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate import generate  # noqa: E402  (sibling module, run as a script)

LIRK = [sys.executable, "-m", "lirk"]
REPO_ROOT = Path(__file__).resolve().parent.parent


def _lirk(args: list[str], cwd: Path) -> tuple[float, int, str]:
    env = {"PYTHONPATH": str(REPO_ROOT)}
    import os

    env = {**os.environ, **env}
    started = time.monotonic()
    proc = subprocess.run(
        LIRK + args, cwd=cwd, capture_output=True, text=True, env=env,
        stdin=subprocess.DEVNULL,
    )
    elapsed = time.monotonic() - started
    last = (proc.stdout.strip().splitlines() or [""])[-2:]
    return elapsed, proc.returncode, " | ".join(last)


def run_scenarios(repo: Path, with_tests: bool) -> list[dict]:
    results = []

    def step(name: str, args: list[str]) -> None:
        seconds, code, tail = _lirk(args, repo)
        results.append({"scenario": name, "seconds": round(seconds, 2), "exit": code, "tail": tail})

    step("build-cold", ["build", "//..."])
    step("build-cached", ["build", "//..."])
    leaf = repo / "p0000" / "m0.py"
    leaf.write_text(leaf.read_text() + "\n# edited\n")
    step("build-edit", ["build", "//..."])
    if with_tests:
        step("test-cold", ["test", "//..."])
        step("test-cached", ["test", "//..."])
        step("verify-5", ["verify", "--sample", "5", "--seed", "1"])
    step("fix-dry", ["fix", "--dry-run"])
    return results


def bench(shape: str, packages: int, with_tests: bool, **gen) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        counts = generate(repo, shape, packages, with_tests=with_tests, **gen)
        return {"shape": shape, "packages": packages, **counts,
                "results": run_scenarios(repo, with_tests)}


PRESET = [
    ("wide", 100, True),
    ("mesh", 100, True),
    ("mesh", 500, False),
    ("mesh", 1000, False),
    ("deep", 500, False),
]


def _print_table(runs: list[dict]) -> None:
    scenarios = []
    for run in runs:
        for r in run["results"]:
            if r["scenario"] not in scenarios:
                scenarios.append(r["scenario"])
    header = f"{'repo':<22}" + "".join(f"{s:>13}" for s in scenarios)
    print(header)
    print("-" * len(header))
    for run in runs:
        by = {r["scenario"]: r for r in run["results"]}
        name = f"{run['shape']} {run['targets']} targets"
        cells = ""
        for s in scenarios:
            r = by.get(s)
            cells += f"{'':>13}" if r is None else f"{r['seconds']:>12.2f}{'!' if r['exit'] else 's'}"
        print(f"{name:<22}{cells}")
    print("(s = seconds, exit 0;  ! = nonzero exit)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shape", choices=["wide", "deep", "mesh"], default="mesh")
    parser.add_argument("--packages", type=int, default=100)
    parser.add_argument("--no-tests", action="store_true")
    parser.add_argument("--data-files", type=int, default=0)
    parser.add_argument("--preset", action="store_true", help="run the standard set")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    args = parser.parse_args(argv)

    if args.preset:
        runs = [bench(shape, n, tests) for shape, n, tests in PRESET]
    else:
        runs = [bench(args.shape, args.packages, not args.no_tests, data_files=args.data_files)]

    if args.json:
        print(json.dumps(runs, indent=2))
    else:
        _print_table(runs)
        failures = [(run["shape"], r) for run in runs for r in run["results"] if r["exit"]]
        for shape, r in failures:
            print(f"nonzero exit: {shape} {r['scenario']}: {r['tail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
