import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from lirk.actions import validate_target
from lirk.cli import main
from lirk.graph import build_graph

# app loads engine by a *computed* file path, the way terminal-projects'
# furminal loads region-explorer: invisible to any import scan.
APP = """import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_engine():
    spec = importlib.util.spec_from_file_location("eng", HERE.parent / "engine" / "engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
"""
APP_TEST = """import unittest

from app.loader import load_engine


class T(unittest.TestCase):
    def test_engine(self):
        self.assertEqual(load_engine().POWER, 9)
"""


class MutateTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name)
        (self.root / ".lirk-root").write_text("")
        for d in ("engine", "app", "other"):
            (self.root / d).mkdir()
        (self.root / "engine" / "engine.py").write_text("POWER = 9\n")
        (self.root / "engine" / "BUILD.lirk").write_text(
            '[[target]]\nname = "engine"\ntype = "library"\nsrcs = ["engine.py"]\n'
        )
        (self.root / "app" / "loader.py").write_text(APP)
        (self.root / "app" / "test_app.py").write_text(APP_TEST)
        (self.root / "other" / "values.py").write_text("X = 1\n")
        (self.root / "other" / "test_other.py").write_text(
            "import unittest\nfrom other.values import X\n\n"
            "class T(unittest.TestCase):\n    def test(self):\n        self.assertEqual(X, 1)\n"
        )
        (self.root / "other" / "BUILD.lirk").write_text(
            '[[target]]\nname = "other"\ntype = "library"\nsrcs = ["values.py"]\n\n'
            '[[target]]\nname = "other_test"\ntype = "test"\nsrcs = ["test_other.py"]\ndeps = [":other"]\n'
        )
        self._app_build(declared=False)

    def _app_build(self, declared):
        dep = ', "//engine:engine"' if declared else ""
        (self.root / "app" / "BUILD.lirk").write_text(
            '[[target]]\nname = "app"\ntype = "library"\nsrcs = ["loader.py"]\n'
            f'deps = []\n\n'
            '[[target]]\nname = "app_test"\ntype = "test"\nsrcs = ["test_app.py"]\n'
            f'deps = [":app"{dep}]\n'
        )

    def _verify_mutate(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["verify", "--mutate", *extra], root=self.root)
        return code, out.getvalue()

    def test_an_undeclared_path_load_is_found(self):
        code, out = self._verify_mutate()
        self.assertEqual(code, 1, out)
        self.assertIn(
            "STALE  //app:app_test depends on engine/engine.py (//engine:engine) "
            "without declaring it",
            out,
        )
        self.assertIn("1 undeclared dependency found", out)

    def test_this_is_a_real_stale_pass_without_it(self):
        # The bug the command exists for: cached green over broken code.
        with contextlib.redirect_stdout(io.StringIO()):
            main(["test", "//..."], root=self.root)
        (self.root / "engine" / "engine.py").write_text("POWER = 0\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["test", "//app:app_test"], root=self.root)
        self.assertIn("cached  //app:app_test", out.getvalue())

    def test_declaring_the_dep_clears_it(self):
        self._app_build(declared=True)
        code, out = self._verify_mutate()
        self.assertEqual(code, 0, out)
        self.assertIn("0 undeclared dependencies found", out)

    def test_the_working_tree_is_never_touched(self):
        # Only lirk's own cache file may change (it records clean pairs).
        def snapshot():
            return {p: p.read_bytes() for p in self.root.rglob("*")
                    if p.is_file() and not p.name.startswith(".lirk-cache")}
        before = snapshot()
        self._verify_mutate()
        self.assertEqual(before, snapshot())

    def test_every_test_passes_at_baseline(self):
        # Guards the fixture itself: a test failing unbroken is skipped,
        # which would quietly hollow out every other test here.
        _, out = self._verify_mutate()
        self.assertNotIn("fails even unbroken", out)

    def test_a_second_run_skips_pairs_that_checked_clean(self):
        self._app_build(declared=True)
        _, first = self._verify_mutate()
        self.assertIn("breaking 3 source(s)", first)
        _, second = self._verify_mutate()
        self.assertIn("skipping", second)
        self.assertIn("breaking 0 source(s) in turn: 0 test run(s)", second)

    def test_changing_a_source_rechecks_its_pairs(self):
        self._app_build(declared=True)
        self._verify_mutate()
        (self.root / "engine" / "engine.py").write_text("POWER = 9  # edited\n")
        _, out = self._verify_mutate()
        # engine's own pairs are rechecked, and so are app_test's (its
        # fingerprint includes engine); only the unaffected pair is skipped.
        self.assertIn("engine/engine.py: 1 test(s)", out)
        self.assertIn("skipping 1 pair(s)", out)

    def test_force_rechecks_everything(self):
        self._app_build(declared=True)
        self._verify_mutate()
        _, out = self._verify_mutate("--force")
        self.assertNotIn("skipping", out)
        self.assertIn("breaking 3 source(s)", out)

    def test_findings_are_never_skipped(self):
        self._verify_mutate()
        code, out = self._verify_mutate()
        self.assertEqual(code, 1)
        self.assertIn("STALE  //app:app_test", out)

    def test_progress_is_reported_per_source(self):
        _, out = self._verify_mutate()
        self.assertRegex(out, r"  \[1/\d+\] \S+\.py: \d+ test\(s\), \d+ finding\(s\), [\d.]+s")

    def test_a_test_failing_unbroken_is_skipped_not_blamed(self):
        (self.root / "other" / "test_other.py").write_text(
            "import unittest\n\nclass T(unittest.TestCase):\n"
            "    def test(self):\n        self.fail('already red')\n"
        )
        _, out = self._verify_mutate()
        self.assertIn("skipped //other:other_test: fails even unbroken", out)
        self.assertNotIn("STALE  //other:other_test", out)

    def test_sample_limits_the_sources_broken(self):
        _, out = self._verify_mutate("--sample", "1", "--seed", "3")
        self.assertIn("sampling 1 of 3 sources (seed 3)", out)
        self.assertIn("breaking 1 source(s)", out)

    def test_labels_limit_which_tests_are_checked(self):
        code, out = self._verify_mutate("//other/...")
        self.assertEqual(code, 0, out)
        self.assertIn("running 1 test target(s)", out)


class PathLoadNoteTests(unittest.TestCase):
    def test_loading_code_by_path_is_noted(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "app").mkdir()
        (root / "app" / "app.py").write_text(APP)
        (root / "app" / "BUILD.lirk").write_text(
            '[[target]]\nname = "app"\ntype = "library"\nsrcs = ["app.py"]\n'
        )
        graph = build_graph(root)
        result = validate_target(graph.targets["//app:app"], root)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.notes), 1)
        self.assertIn("app.py loads code by file path (spec_from_file_location)", result.notes[0])

    def test_ordinary_code_has_no_note(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "a").mkdir()
        (root / "a" / "a.py").write_text("import json\nX = json.dumps(1)\n")
        (root / "a" / "BUILD.lirk").write_text(
            '[[target]]\nname = "a"\ntype = "library"\nsrcs = ["a.py"]\n'
        )
        graph = build_graph(root)
        self.assertEqual(validate_target(graph.targets["//a:a"], root).notes, [])

    def test_the_note_is_printed_on_rebuild_only(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "app").mkdir()
        (root / "app" / "app.py").write_text(APP)
        (root / "app" / "BUILD.lirk").write_text(
            '[[target]]\nname = "app"\ntype = "library"\nsrcs = ["app.py"]\n'
        )
        def build():
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                main(["build", "//..."], root=root)
            return out.getvalue()
        self.assertIn("note   //app:app: app.py loads code by file path", build())
        self.assertNotIn("note", build())


if __name__ == "__main__":
    unittest.main()
