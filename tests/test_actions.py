import unittest
from pathlib import Path
from unittest.mock import patch

from lirk import actions
from lirk.actions import run_test, validate_target
from lirk.graph import build_graph
from lirk.targets import Target

FIXTURES = Path(__file__).parent / "fixtures"


class ValidateTargetTests(unittest.TestCase):
    def test_ok_when_source_files_exist(self):
        graph = build_graph(FIXTURES / "sample_repo")
        target = graph.targets["//c:c_lib"]

        result = validate_target(target, FIXTURES / "sample_repo")

        self.assertTrue(result.ok)

    def test_fails_when_source_file_missing(self):
        graph = build_graph(FIXTURES / "missing_src_repo")
        target = graph.targets["//a:a"]

        result = validate_target(target, FIXTURES / "missing_src_repo")

        self.assertFalse(result.ok)
        self.assertIn("missing.py", result.message)

    def test_fails_when_source_file_has_a_syntax_error(self):
        graph = build_graph(FIXTURES / "syntax_error_repo")
        target = graph.targets["//a:a"]

        result = validate_target(target, FIXTURES / "syntax_error_repo")

        self.assertFalse(result.ok)
        self.assertIn("broken.py", result.message)
        self.assertIn("syntax error", result.message)

    def test_every_src_of_a_multi_src_library_is_syntax_checked(self):
        # A mutant limiting validate_target to target.srcs[:1] would
        # never reach three.py (the third src, which has a syntax
        # error) and report this target as ok.
        graph = build_graph(FIXTURES / "multisrc_repo")
        target = graph.targets["//a:lib3"]

        result = validate_target(target, FIXTURES / "multisrc_repo")

        self.assertFalse(result.ok)
        self.assertIn("three.py", result.message)

    def test_ok_when_data_file_exists_and_is_not_syntax_checked(self):
        graph = build_graph(FIXTURES / "data_dep_repo")
        target = graph.targets["//a:lib"]

        result = validate_target(target, FIXTURES / "data_dep_repo")

        self.assertTrue(result.ok)

    def test_fails_cleanly_on_a_binary_source_file(self):
        graph = build_graph(FIXTURES / "binary_src_repo")
        target = graph.targets["//a:a"]

        result = validate_target(target, FIXTURES / "binary_src_repo")

        self.assertFalse(result.ok)
        self.assertIn("broken.py", result.message)
        self.assertIn("not readable as Python source", result.message)

    def test_fails_when_data_file_missing(self):
        graph = build_graph(FIXTURES / "data_dep_repo")
        target = graph.targets["//a:lib"]
        broken = Target(
            name=target.name,
            type=target.type,
            srcs=target.srcs,
            deps=target.deps,
            data=("nope.txt",),
            package=target.package,
        )

        result = validate_target(broken, FIXTURES / "data_dep_repo")

        self.assertFalse(result.ok)
        self.assertIn("nope.txt", result.message)


class RunTestTests(unittest.TestCase):
    def test_passes_for_a_passing_test(self):
        graph = build_graph(FIXTURES / "sample_repo")
        target = graph.targets["//c:c_test"]

        result = run_test(target, FIXTURES / "sample_repo")

        self.assertTrue(result.ok, result.stderr)
        self.assertEqual(result.message, "passed")

    def test_fails_for_a_failing_test_and_captures_output(self):
        graph = build_graph(FIXTURES / "failing_test_repo")
        target = graph.targets["//a:a_test"]

        result = run_test(target, FIXTURES / "failing_test_repo")

        self.assertFalse(result.ok)
        self.assertIn("failed", result.message)
        self.assertIn("FAILED", result.stderr)

    def test_passes_for_a_root_relative_import(self):
        # thing_test.py does `from pkg.thing import value`, which only
        # resolves if the repo root is on PYTHONPATH -- every other
        # fixture uses a flat sibling import, so this is the only
        # regression test for run_test's env=env PYTHONPATH fix
        # (428c517), the one production bug this tool has ever had.
        graph = build_graph(FIXTURES / "rootimport_repo")
        target = graph.targets["//pkg:thing_test"]

        result = run_test(target, FIXTURES / "rootimport_repo")

        self.assertTrue(result.ok, result.stderr)
        self.assertEqual(result.message, "passed")

    def test_second_src_of_a_multi_src_test_target_is_run_and_reported(self):
        # A mutant limiting run_test to target.srcs[:1] would never
        # invoke test_second.py (which fails) and report this target
        # as passing, since target.srcs[0] (test_first.py) passes.
        graph = build_graph(FIXTURES / "multisrc_repo")
        target = graph.targets["//a:multi_test"]

        result = run_test(target, FIXTURES / "multisrc_repo")

        self.assertFalse(result.ok)
        self.assertIn("test_second", result.message)

    def test_child_does_not_inherit_lirks_stdin(self):
        graph = build_graph(FIXTURES / "stdin_repo")
        target = graph.targets["//a:stdin_test"]

        result = run_test(target, FIXTURES / "stdin_repo")

        self.assertTrue(result.ok, result.stderr)

    def test_all_srcs_run_even_after_an_earlier_one_fails(self):
        # multi_test's srcs are test_first (passes), test_second
        # (fails), test_third (fails). Stopping at the first failure
        # would silently hide test_third entirely -- run_test must
        # keep going and report every failure, not just the first.
        graph = build_graph(FIXTURES / "multisrc_repo")
        target = graph.targets["//a:multi_test"]

        result = run_test(target, FIXTURES / "multisrc_repo")

        self.assertFalse(result.ok)
        self.assertIn("2 of 3", result.message)
        self.assertIn("test_second", result.message)
        self.assertIn("test_third", result.message)

    def test_hung_test_is_killed_and_reported_as_a_clean_failure(self):
        graph = build_graph(FIXTURES / "hang_repo")
        target = graph.targets["//a:hang_test"]

        with patch.object(actions, "TEST_TIMEOUT_SECONDS", 0.5):
            result = run_test(target, FIXTURES / "hang_repo")

        self.assertFalse(result.ok)
        self.assertIn("timed out", result.message)

    def test_timeout_does_not_abandon_the_remaining_srcs(self):
        # srcs are [test_hang.py, test_after.py]; test_after fails on
        # purpose. If the timeout returned early, only test_hang would
        # appear -- seeing both proves the src after a timeout still ran.
        graph = build_graph(FIXTURES / "hang_repo")
        target = graph.targets["//a:hang_then_more_test"]

        with patch.object(actions, "TEST_TIMEOUT_SECONDS", 0.5):
            result = run_test(target, FIXTURES / "hang_repo")

        self.assertFalse(result.ok)
        self.assertIn("2 of 2", result.message)
        self.assertIn("timed out", result.message)
        self.assertIn("test_hang", result.message)
        self.assertIn("test_after", result.message)

    def test_module_containing_zero_tests_is_a_failure(self):
        # Exits 5 on 3.12+ but 0 on 3.11, which pyproject still
        # supports, so an exit-code-only check passes a file that tests
        # nothing. Detected from the "Ran 0 tests" summary instead.
        root = FIXTURES / "no_tests_repo"
        graph = build_graph(root)

        result = run_test(graph.targets["//a:empty_test"], root)

        self.assertFalse(result.ok)
        self.assertIn("no tests", result.message)

    def test_fails_defensively_on_a_test_target_with_no_srcs(self):
        # _parse_target already rejects this at parse time, but
        # run_test must never silently report success if it somehow
        # receives an empty srcs list (e.g. constructed directly, as
        # here) -- looping over zero srcs must not fall through to ok.
        empty_test = Target(
            name="empty_test",
            type="test",
            srcs=(),
            deps=(),
            data=(),
            package="a",
        )

        result = run_test(empty_test, FIXTURES / "sample_repo")

        self.assertFalse(result.ok)

    def test_fails_when_source_file_missing_without_spawning_subprocess(self):
        graph = build_graph(FIXTURES / "missing_src_repo")
        # missing_src_repo's only target is a library; reuse its shape
        # by pointing run_test at a target whose srcs don't exist.
        target = graph.targets["//a:a"]

        result = run_test(target, FIXTURES / "missing_src_repo")

        self.assertFalse(result.ok)
        self.assertIn("missing.py", result.message)

    def test_data_directory_counts_as_present(self):
        # `data` may name a directory; only srcs must be files.
        root = FIXTURES / "datadir_repo"
        graph = build_graph(root)
        target = graph.targets["//pkg:lib_with_data_dir"]

        self.assertEqual(actions.missing_files(target, root), [])

    def test_missing_data_directory_is_reported(self):
        root = FIXTURES / "datadir_repo"
        graph = build_graph(root)
        target = graph.targets["//pkg:lib_with_data_dir"]
        absent = Target(
            name=target.name,
            type=target.type,
            srcs=target.srcs,
            deps=target.deps,
            data=("no_such_dir",),
            package=target.package,
        )

        self.assertEqual(actions.missing_files(absent, root), ["no_such_dir"])

    def test_runs_a_test_src_in_a_package_subdirectory(self):
        # "sub/test_nested.py" must run as the module `sub.test_nested`;
        # deriving the stem alone made it an unexplained ModuleNotFoundError.
        root = FIXTURES / "subdir_test_repo"
        graph = build_graph(root)
        target = graph.targets["//pkg:subdir_test"]

        result = run_test(target, root)

        self.assertTrue(result.ok, result.message)

    def test_same_stem_in_different_subdirectories_does_not_collide(self):
        # Both srcs are named test_dup.py; under the stem-only derivation
        # they became one module name and only one of the two ever ran.
        root = FIXTURES / "stem_collision_repo"
        graph = build_graph(root)
        target = graph.targets["//pkg:collide_test"]

        result = run_test(target, root)

        self.assertFalse(result.ok)
        # The failing one is one/test_dup.py; two/test_dup.py passes.
        self.assertIn("one.test_dup", result.message)
        self.assertNotIn("two.test_dup", result.message)


if __name__ == "__main__":
    unittest.main()
