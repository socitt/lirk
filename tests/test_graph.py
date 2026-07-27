import shutil
import tempfile
import unittest
from pathlib import Path

from lirk.graph import (
    GraphError,
    build_graph,
    resolve_label,
    topological_sort,
    transitive_closure,
)

FIXTURES = Path(__file__).parent / "fixtures"


class BuildGraphTests(unittest.TestCase):
    def test_loads_all_targets_with_qualified_labels(self):
        graph = build_graph(FIXTURES / "sample_repo")

        self.assertEqual(
            set(graph.targets),
            {
                "//a:a_lib", "//a:a_test",
                "//b:b_lib", "//b:b_test",
                "//c:c_lib", "//c:c_test",
            },
        )

    def test_resolves_absolute_and_relative_deps(self):
        graph = build_graph(FIXTURES / "sample_repo")

        self.assertEqual(graph.edges["//a:a_lib"], ("//b:b_lib",))
        self.assertEqual(graph.edges["//a:a_test"], ("//a:a_lib",))
        self.assertEqual(graph.edges["//c:c_lib"], ())

    def test_missing_dependency_raises_graph_error(self):
        with self.assertRaisesRegex(GraphError, "//b:nonexistent"):
            build_graph(FIXTURES / "missing_dep_repo")

    def test_self_dependency_raises_graph_error(self):
        with self.assertRaisesRegex(GraphError, "cannot depend on itself"):
            build_graph(FIXTURES / "self_dep_repo")


class ResolveLabelTests(unittest.TestCase):
    def test_absolute_label_without_a_colon_is_malformed_not_missing(self):
        # Previously this fell through to "does not exist" downstream,
        # which sends a reader hunting for a missing target instead of
        # a typo -- it should be reported as malformed at the source.
        with self.assertRaisesRegex(GraphError, "malformed"):
            resolve_label("//a", "pkg")

    def test_label_with_two_colons_is_malformed(self):
        with self.assertRaisesRegex(GraphError, "malformed"):
            resolve_label("//a:b:c", "pkg")

    def test_empty_name_part_is_malformed(self):
        with self.assertRaisesRegex(GraphError, "malformed"):
            resolve_label(":", "pkg")

    def test_root_package_label_still_resolves(self):
        self.assertEqual(resolve_label("//:name", "pkg"), "//:name")

    def test_relative_label_still_resolves(self):
        self.assertEqual(resolve_label(":sibling", "pkg"), "//pkg:sibling")


class FindBuildFilesTests(unittest.TestCase):
    def test_ignores_a_build_file_under_a_dot_directory(self):
        # A BUILD.lirk under .venv/, node_modules/, a nested checkout,
        # etc. must not be picked up -- it belongs to something
        # vendored, not this repo, and (per review D2/Probe O) could
        # otherwise crash an unrelated repo-wide build if it declares
        # a missing source file.
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "sample_repo", root)

        hidden = root / ".hidden" / "vendored"
        hidden.mkdir(parents=True)
        (hidden / "BUILD.lirk").write_text(
            '[[target]]\nname = "vendored"\ntype = "library"\n'
            'srcs = ["nope.py"]\n'
        )

        graph = build_graph(root)

        self.assertEqual(
            set(graph.targets),
            {
                "//a:a_lib", "//a:a_test",
                "//b:b_lib", "//b:b_test",
                "//c:c_lib", "//c:c_test",
            },
        )


class TopologicalSortTests(unittest.TestCase):
    def test_dependencies_precede_dependents(self):
        graph = build_graph(FIXTURES / "sample_repo")
        order = topological_sort(graph)

        self.assertEqual(set(order), set(graph.targets))
        self.assertLess(order.index("//c:c_lib"), order.index("//b:b_lib"))
        self.assertLess(order.index("//b:b_lib"), order.index("//a:a_lib"))
        self.assertLess(order.index("//c:c_lib"), order.index("//c:c_test"))
        self.assertLess(order.index("//a:a_lib"), order.index("//a:a_test"))

    def test_cycle_raises_graph_error_naming_the_cycle(self):
        graph = build_graph(FIXTURES / "cycle_repo")
        with self.assertRaisesRegex(GraphError, "circular dependency"):
            topological_sort(graph)

    def test_diamond_dependency_produces_a_valid_order(self):
        # d -> b, d -> c, both b and c -> a. sample_repo's linear chain
        # never gives a target more than one dep, so this is the only
        # coverage for a dependency reached by two distinct paths.
        graph = build_graph(FIXTURES / "diamond_repo")
        order = topological_sort(graph)

        self.assertEqual(set(order), set(graph.targets))
        self.assertLess(order.index("//pkg:a_lib"), order.index("//pkg:b_lib"))
        self.assertLess(order.index("//pkg:a_lib"), order.index("//pkg:c_lib"))
        self.assertLess(order.index("//pkg:b_lib"), order.index("//pkg:d_lib"))
        self.assertLess(order.index("//pkg:c_lib"), order.index("//pkg:d_lib"))


class TransitiveClosureTests(unittest.TestCase):
    def test_includes_roots_and_their_dependencies(self):
        graph = build_graph(FIXTURES / "sample_repo")

        closure = transitive_closure(graph, {"//a:a_lib"})

        self.assertEqual(closure, {"//a:a_lib", "//b:b_lib", "//c:c_lib"})

    def test_excludes_unrelated_targets(self):
        graph = build_graph(FIXTURES / "sample_repo")

        closure = transitive_closure(graph, {"//c:c_test"})

        self.assertEqual(closure, {"//c:c_test", "//c:c_lib"})
        self.assertNotIn("//a:a_lib", closure)

    def test_diamond_shared_dependency_reached_via_two_paths_is_deduplicated(self):
        graph = build_graph(FIXTURES / "diamond_repo")

        closure = transitive_closure(graph, {"//pkg:d_lib"})

        self.assertEqual(
            closure,
            {"//pkg:d_lib", "//pkg:b_lib", "//pkg:c_lib", "//pkg:a_lib"},
        )


if __name__ == "__main__":
    unittest.main()
