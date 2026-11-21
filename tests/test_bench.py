import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from bench.generate import generate
from lirk.cli import main


class GeneratedRepoTests(unittest.TestCase):
    """The benchmark's repos must stay valid lirk repos, or the numbers
    measure error paths instead of real work."""

    def _build(self, shape):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "repo"
        counts = generate(root, shape, packages=8, with_tests=True, data_files=2)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["build", "//..."], root=root)
        return root, counts, code, out.getvalue()

    def test_every_shape_builds_clean(self):
        for shape in ("wide", "deep", "mesh"):
            with self.subTest(shape=shape):
                _, counts, code, out = self._build(shape)
                self.assertEqual(code, 0, out)
                self.assertEqual(counts["targets"], 16)
                self.assertIn("16 built", out)

    def test_generation_is_deterministic(self):
        a, *_ = self._build("mesh")
        b, *_ = self._build("mesh")
        for path in sorted(a.rglob("BUILD.lirk")):
            rel = path.relative_to(a)
            self.assertEqual(path.read_text(), (b / rel).read_text(), rel)

    def test_declared_deps_are_exactly_the_imports(self):
        # `lirk fix` finding nothing to add proves every import is
        # declared; the build passing proves every declaration resolves.
        root, *_ = self._build("mesh")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["fix", "--dry-run"], root=root)
        self.assertEqual(code, 0)
        self.assertIn("would add 0 dep(s)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
