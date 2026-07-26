import unittest
from pathlib import Path

from lirk.graph import GraphError, build_graph, topological_sort

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


if __name__ == "__main__":
    unittest.main()
