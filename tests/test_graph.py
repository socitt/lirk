import shutil
import tempfile
import unittest
from pathlib import Path

from lirk.graph import (
    Graph,
    GraphError,
    build_graph,
    resolve_label,
    topological_sort,
    transitive_closure,
)
from lirk.targets import Target

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

    def test_ignore_list_excludes_a_directory_and_its_subtree(self):
        # ignore_repo's .lirk-root ignores "vendor". Both vendor/BUILD.lirk
        # and vendor/nested/BUILD.lirk declare deps on targets that don't
        # exist, so if either is scanned, build_graph raises.
        graph = build_graph(FIXTURES / "ignore_repo")

        self.assertEqual(set(graph.targets), {"//real:real_lib"})

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

    def test_a_build_file_at_the_repo_root_uses_the_bare_label_form(self):
        graph = build_graph(FIXTURES / "root_package_repo")

        self.assertEqual(set(graph.targets), {"//:root_lib"})
        self.assertEqual(graph.targets["//:root_lib"].package, "")


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


class DeepChainTests(unittest.TestCase):
    """The sort is iterative: a chain longer than Python's recursion
    limit used to escape as a RecursionError traceback."""

    DEPTH = 3000

    def _graph(self, close_cycle=False):
        targets, edges = {}, {}
        for i in range(self.DEPTH):
            label = f"//p:t{i:05d}"
            targets[label] = Target(f"t{i:05d}", "library", (), (), (), "p")
            # t0 -> t1 -> ... so the first label visited is the top of
            # the chain and the walk must go the whole depth.
            nxt = i + 1 if i + 1 < self.DEPTH else (0 if close_cycle else None)
            edges[label] = (f"//p:t{nxt:05d}",) if nxt is not None else ()
        return Graph(targets=targets, edges=edges)

    def test_long_chain_sorts_dependencies_first(self):
        order = topological_sort(self._graph())
        self.assertEqual(len(order), self.DEPTH)
        self.assertEqual(order[0], f"//p:t{self.DEPTH - 1:05d}")
        self.assertEqual(order[-1], "//p:t00000")

    def test_long_cycle_is_still_named_in_full(self):
        with self.assertRaises(GraphError) as caught:
            topological_sort(self._graph(close_cycle=True))
        message = str(caught.exception)
        self.assertIn("circular dependency", message)
        self.assertEqual(message.count("->"), self.DEPTH)


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
