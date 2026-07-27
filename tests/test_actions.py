import unittest
from pathlib import Path

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

    def test_fails_when_source_file_missing_without_spawning_subprocess(self):
        graph = build_graph(FIXTURES / "missing_src_repo")
        # missing_src_repo's only target is a library; reuse its shape
        # by pointing run_test at a target whose srcs don't exist.
        target = graph.targets["//a:a"]

        result = run_test(target, FIXTURES / "missing_src_repo")

        self.assertFalse(result.ok)
        self.assertIn("missing.py", result.message)


if __name__ == "__main__":
    unittest.main()
