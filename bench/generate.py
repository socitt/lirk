"""Generate a synthetic repo for benchmarking lirk at scale.

Every generated module really imports the modules of the targets it
depends on, so lirk's import check does real work and passes, exactly
as in a correctly-declared real repo. Output is fully determined by the
arguments (randomness is seeded), so two runs are comparable.

Shapes:
  wide     independent packages: lots of targets, a shallow graph
  deep     one long dependency chain: the worst case for depth
  mesh     a random DAG, each library depending on up to --fanout
           earlier ones: closest to a real monorepo

Usage:
  python3 bench/generate.py OUT_DIR --shape mesh --packages 200
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

TEST_BODY = """import unittest

from {module} import VALUE


class T(unittest.TestCase):
    def test_value(self):
        self.assertIsInstance(VALUE, int)
"""


def _deps_for(shape: str, i: int, fanout: int, rng: random.Random) -> list[int]:
    if i == 0 or shape == "wide":
        return []
    if shape == "deep":
        return [i - 1]
    return sorted(rng.sample(range(i), min(fanout, i)))


def generate(
    out: Path,
    shape: str,
    packages: int,
    files_per_library: int = 3,
    fanout: int = 3,
    data_files: int = 0,
    with_tests: bool = True,
    seed: int = 0,
) -> dict[str, int]:
    """Write the repo to `out` (replacing it). Returns target counts."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / ".lirk-root").write_text("")
    rng = random.Random(seed)
    libraries = tests = 0

    for i in range(packages):
        pkg = f"p{i:04d}"
        d = out / pkg
        d.mkdir()
        deps = _deps_for(shape, i, fanout, rng)
        srcs = [f"m{j}.py" for j in range(files_per_library)]

        # The first module imports one module from each dependency, so
        # every declared edge is a real import and vice versa.
        imports = "".join(f"from p{dep:04d}.m0 import VALUE as V{dep}\n" for dep in deps)
        total = " + ".join([str(i)] + [f"V{dep}" for dep in deps])
        (d / "m0.py").write_text(f"{imports}\nVALUE = {total}\n")
        for j in range(1, files_per_library):
            (d / f"m{j}.py").write_text(f"from p{i:04d}.m0 import VALUE as BASE\n\nVALUE = BASE + {j}\n")

        dep_labels = ", ".join(f'"//p{dep:04d}:lib"' for dep in deps)
        build = (
            "[[target]]\n"
            'name = "lib"\n'
            'type = "library"\n'
            f"srcs = {srcs!r}\n".replace("'", '"')
            + f"deps = [{dep_labels}]\n"
        )
        libraries += 1

        if with_tests:
            (d / "test_lib.py").write_text(TEST_BODY.format(module=f"{pkg}.m0"))
            data_line = ""
            if data_files:
                data_dir = d / "testdata"
                data_dir.mkdir()
                for k in range(data_files):
                    (data_dir / f"case{k}.txt").write_text(f"{pkg} case {k}\n" * 20)
                data_line = 'data = ["testdata"]\n'
            build += (
                "\n[[target]]\n"
                'name = "lib_test"\n'
                'type = "test"\n'
                'srcs = ["test_lib.py"]\n'
                'deps = [":lib"]\n'
                f"{data_line}"
            )
            tests += 1

        (d / "BUILD.lirk").write_text(build)

    return {"libraries": libraries, "tests": tests, "targets": libraries + tests}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--shape", choices=["wide", "deep", "mesh"], default="mesh")
    parser.add_argument("--packages", type=int, default=100)
    parser.add_argument("--files", type=int, default=3, help="srcs per library")
    parser.add_argument("--fanout", type=int, default=3, help="max deps per library (mesh)")
    parser.add_argument("--data-files", type=int, default=0, help="data files per test")
    parser.add_argument("--no-tests", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    counts = generate(
        args.out, args.shape, args.packages, args.files, args.fanout,
        args.data_files, not args.no_tests, args.seed,
    )
    print(f"generated {args.shape} repo at {args.out}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
