import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from lirk.cli import _discover_root, main

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

    def test_build_fails_on_a_syntax_error(self):
        syntax_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, syntax_root, ignore_errors=True)
        shutil.copytree(FIXTURES / "syntax_error_repo", syntax_root, dirs_exist_ok=True)

        code, out = _run(["build", "//a:a"], syntax_root)

        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)
        self.assertIn("syntax error", out)

    def test_force_bypasses_cache_without_deleting_it(self):
        _run(["build", "//..."], self.root)
        code, out = _run(["build", "//...", "--force"], self.root)

        self.assertEqual(code, 0)
        self.assertNotIn("  cached  ", out)
        self.assertTrue((self.root / ".lirk-cache.json").exists())

    def test_build_summary_line_counts_fresh_run(self):
        code, out = _run(["build", "//..."], self.root)

        self.assertEqual(code, 0)
        self.assertIn("lirk: 6 built, 0 cached, 0 failed", out)

    def test_build_summary_line_counts_cached_rerun(self):
        _run(["build", "//..."], self.root)
        code, out = _run(["build", "//..."], self.root)

        self.assertEqual(code, 0)
        self.assertIn("lirk: 0 built, 6 cached, 0 failed", out)

    def test_build_summary_line_counts_a_failure(self):
        syntax_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, syntax_root, ignore_errors=True)
        shutil.copytree(FIXTURES / "syntax_error_repo", syntax_root, dirs_exist_ok=True)

        code, out = _run(["build", "//a:a"], syntax_root)

        self.assertEqual(code, 1)
        self.assertIn("lirk: 0 built, 0 cached, 1 failed", out)


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

    def test_summary_line_counts_a_single_fresh_test(self):
        code, out = _run(["test", "//c:c_test"], self.root)

        self.assertEqual(code, 0)
        self.assertIn("lirk: 1/1 tests passed", out)

    def test_rejects_a_non_test_target(self):
        code, out = _run(["test", "//c:c_lib"], self.root)
        self.assertEqual(code, 1)

    def test_runs_all_test_targets(self):
        code, out = _run(["test", "//..."], self.root)

        self.assertEqual(code, 0)
        for label in ("//a:a_test", "//b:b_test", "//c:c_test"):
            self.assertIn(label, out)

    def test_summary_line_counts_all_fresh_tests(self):
        code, out = _run(["test", "//..."], self.root)

        self.assertEqual(code, 0)
        self.assertIn("lirk: 3/3 tests passed", out)

    def test_second_run_skips_unchanged_passing_test(self):
        _run(["test", "//c:c_test"], self.root)
        code, out = _run(["test", "//c:c_test"], self.root)

        self.assertEqual(code, 0)
        self.assertIn("cached", out)
        # A cached test previously passed, so it should still count
        # toward the "passed" side of the summary, not be dropped.
        self.assertIn("lirk: 1/1 tests passed", out)

    def test_force_reruns_unchanged_test_without_deleting_cache(self):
        _run(["test", "//c:c_test"], self.root)
        code, out = _run(["test", "//c:c_test", "--force"], self.root)

        self.assertEqual(code, 0)
        self.assertNotIn("cached", out)
        self.assertIn("PASS", out)
        self.assertTrue((self.root / ".lirk-cache.json").exists())

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
        # a_lib is a library dep, not a test target, so it must not
        # inflate the test-summary denominator on either run.
        self.assertIn("lirk: 0/1 tests passed", out1)
        self.assertIn("lirk: 0/1 tests passed", out2)


class DataFieldTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "data_dep_repo", self.root)

    def test_editing_a_declared_data_file_invalidates_the_cache(self):
        code1, out1 = _run(["test", "//a:lib_test"], self.root)
        self.assertEqual(code1, 0)
        self.assertIn("PASS", out1)

        (self.root / "a" / "story.txt").write_text(
            "This is not the maze you are looking for.\n"
        )

        code2, out2 = _run(["test", "//a:lib_test"], self.root)

        self.assertEqual(code2, 1)
        self.assertIn("FAIL", out2)
        self.assertNotIn("cached", out2)


class DiscoverRootTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.repo_root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "sample_repo", self.repo_root)

    def test_falls_back_to_start_when_no_marker_present(self):
        nested = self.repo_root / "a"
        self.assertEqual(_discover_root(nested), nested)

    def test_finds_marker_in_an_ancestor(self):
        (self.repo_root / ".lirk-root").touch()
        nested = self.repo_root / "a"

        self.assertEqual(_discover_root(nested), self.repo_root)

    def test_start_itself_can_be_the_marked_root(self):
        (self.repo_root / ".lirk-root").touch()
        self.assertEqual(_discover_root(self.repo_root), self.repo_root)


class RootDiscoveryEndToEndTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.repo_root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "sample_repo", self.repo_root)
        (self.repo_root / ".lirk-root").touch()

        original_cwd = os.getcwd()
        self.addCleanup(os.chdir, original_cwd)

    def test_build_from_a_subdirectory_finds_the_real_root_via_marker(self):
        os.chdir(self.repo_root / "a")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["build", "//a:a_lib"])  # no --root, no root= override

        self.assertEqual(code, 0)
        self.assertIn("//a:a_lib", out.getvalue())
        self.assertIn("//b:b_lib", out.getvalue())
        self.assertIn("lirk: OK", out.getvalue())

    def test_root_flag_overrides_discovery(self):
        os.chdir(self.repo_root / "a")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["build", "//a:a_lib", "--root", str(self.repo_root)])

        self.assertEqual(code, 0)
        self.assertIn("lirk: OK", out.getvalue())


if __name__ == "__main__":
    unittest.main()
