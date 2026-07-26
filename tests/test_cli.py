import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from lirk.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _run(argv, root):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(argv, root=root)
    return code, out.getvalue()


class BuildCommandTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "sample_repo", self.root)

    def test_build_single_target_builds_only_its_closure(self):
        code, out = _run(["build", "//a:a_lib"], self.root)

        self.assertEqual(code, 0)
        self.assertIn("//a:a_lib", out)
        self.assertIn("//b:b_lib", out)
        self.assertIn("//c:c_lib", out)
        self.assertNotIn("//a:a_test", out)
        self.assertIn("lirk: OK", out)

    def test_build_all_targets(self):
        code, out = _run(["build", "//..."], self.root)

        self.assertEqual(code, 0)
        for label in ("//a:a_lib", "//a:a_test", "//b:b_lib", "//c:c_lib"):
            self.assertIn(label, out)

    def test_second_build_hits_cache(self):
        _run(["build", "//..."], self.root)
        code, out = _run(["build", "//..."], self.root)

        self.assertEqual(code, 0)
        self.assertIn("cached", out)

    def test_unknown_target_fails_clearly(self):
        code, out = _run(["build", "//nope:missing"], self.root)
        self.assertEqual(code, 1)


class TestCommandTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "sample_repo", self.root)

    def test_build_does_not_satisfy_a_later_test_run(self):
        # A `build` only validates that a test target's files exist;
        # it must not let a later `test` run skip actually executing
        # it, since the fingerprint would otherwise look "unchanged"
        # from a run that never called run_test at all.
        _run(["build", "//..."], self.root)
        code, out = _run(["test", "//c:c_test"], self.root)

        self.assertEqual(code, 0)
        self.assertIn("PASS", out)
        self.assertNotIn("cached  //c:c_test", out)

    def test_runs_a_single_test_target(self):
        code, out = _run(["test", "//c:c_test"], self.root)

        self.assertEqual(code, 0)
        self.assertIn("PASS", out)
        self.assertIn("//c:c_test", out)
        self.assertIn("lirk: OK", out)

    def test_rejects_a_non_test_target(self):
        code, out = _run(["test", "//c:c_lib"], self.root)
        self.assertEqual(code, 1)

    def test_runs_all_test_targets(self):
        code, out = _run(["test", "//..."], self.root)

        self.assertEqual(code, 0)
        for label in ("//a:a_test", "//b:b_test", "//c:c_test"):
            self.assertIn(label, out)

    def test_second_run_skips_unchanged_passing_test(self):
        _run(["test", "//c:c_test"], self.root)
        code, out = _run(["test", "//c:c_test"], self.root)

        self.assertEqual(code, 0)
        self.assertIn("cached", out)

    def test_failing_test_is_retried_even_though_unchanged(self):
        failing_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, failing_root, ignore_errors=True)
        shutil.copytree(FIXTURES / "failing_test_repo", failing_root, dirs_exist_ok=True)

        code1, out1 = _run(["test", "//a:a_test"], failing_root)
        code2, out2 = _run(["test", "//a:a_test"], failing_root)

        self.assertEqual(code1, 1)
        self.assertEqual(code2, 1)
        self.assertIn("FAIL", out1)
        self.assertIn("FAIL", out2)
        # a_lib succeeded both times so it's cached on the second run,
        # but a_test failed and must be retried, not skipped.
        self.assertIn("cached  //a:a_lib", out2)
        self.assertNotIn("cached  //a:a_test", out2)


if __name__ == "__main__":
    unittest.main()
