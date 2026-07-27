import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lirk import cache as cache_module
from lirk.cache import (
    compute_fingerprints,
    load_cache,
    needs_build,
    save_cache,
)
from lirk.graph import build_graph, topological_sort

FIXTURES = Path(__file__).parent / "fixtures"


class ComputeFingerprintsTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "sample_repo", self.root)

    def _fingerprints(self):
        graph = build_graph(self.root)
        order = topological_sort(graph)
        return graph, order, compute_fingerprints(graph, self.root, order)

    def test_deterministic_across_runs(self):
        _, _, fp1 = self._fingerprints()
        _, _, fp2 = self._fingerprints()
        self.assertEqual(fp1, fp2)

    def test_covers_every_target(self):
        graph, _, fingerprints = self._fingerprints()
        self.assertEqual(set(fingerprints), set(graph.targets))

    def test_editing_a_source_file_changes_its_own_and_dependents(self):
        _, _, before = self._fingerprints()

        (self.root / "c" / "c.py").write_text("def greet():\n    return 'changed'\n")

        _, _, after = self._fingerprints()

        # c_lib changed directly; b_lib and a_lib depend on it
        # transitively and must change too.
        for label in ("//c:c_lib", "//b:b_lib", "//a:a_lib"):
            self.assertNotEqual(before[label], after[label], label)

        # c_test depends on c_lib so it changes too, but a_test/b_test
        # are unaffected by an edit in a target they don't depend on.
        self.assertNotEqual(before["//c:c_test"], after["//c:c_test"])

    def test_unrelated_target_is_unaffected(self):
        before_graph, before_order, before = self._fingerprints()

        (self.root / "a" / "a.py").write_text("def greet():\n    return 'changed'\n")

        _, _, after = self._fingerprints()

        for label in ("//b:b_lib", "//b:b_test", "//c:c_lib", "//c:c_test"):
            self.assertEqual(before[label], after[label], label)
        self.assertNotEqual(before["//a:a_lib"], after["//a:a_lib"])

    def test_action_version_change_invalidates_every_target_unchanged(self):
        with patch.object(cache_module, "ACTION_VERSION", 1):
            _, _, before = self._fingerprints()
        with patch.object(cache_module, "ACTION_VERSION", 2):
            _, _, after = self._fingerprints()

        for label in before:
            self.assertNotEqual(before[label], after[label], label)


class DiamondFingerprintTests(unittest.TestCase):
    # d -> b, d -> c, both b and c -> a. compute_fingerprints sorts a
    # target's deps specifically so declaration order doesn't matter
    # (cache.py:47); sample_repo's linear chain never gives a target
    # more than one dep, so this was untested.
    def _fingerprint_for_d(self, deps_order: str) -> str:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "diamond_repo", root)

        build_file = root / "pkg" / "BUILD.lirk"
        text = build_file.read_text()
        text = text.replace(
            'deps = [":b_lib", ":c_lib"]', f"deps = {deps_order}"
        )
        build_file.write_text(text)

        graph = build_graph(root)
        order = topological_sort(graph)
        fingerprints = compute_fingerprints(graph, root, order)
        return fingerprints["//pkg:d_lib"]

    def test_swapping_declared_dep_order_produces_an_identical_fingerprint(self):
        fp_bc = self._fingerprint_for_d('[":b_lib", ":c_lib"]')
        fp_cb = self._fingerprint_for_d('[":c_lib", ":b_lib"]')

        self.assertEqual(fp_bc, fp_cb)


class CacheFileTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.cache_path = Path(tmpdir.name) / ".lirk-cache.json"

    def test_load_missing_cache_is_empty(self):
        self.assertEqual(load_cache(self.cache_path), {})

    def test_save_then_load_round_trips(self):
        fingerprints = {"//a:a_lib": "deadbeef", "//b:b_lib": "cafef00d"}
        save_cache(self.cache_path, fingerprints)
        self.assertEqual(load_cache(self.cache_path), fingerprints)

    def test_corrupt_cache_file_is_treated_as_empty(self):
        self.cache_path.write_text("not valid json {{{")
        self.assertEqual(load_cache(self.cache_path), {})

    def test_save_leaves_no_temp_file_behind(self):
        save_cache(self.cache_path, {"//a:a_lib": "deadbeef"})

        tmp_path = self.cache_path.with_name(self.cache_path.name + ".tmp")
        self.assertFalse(tmp_path.exists())
        self.assertTrue(self.cache_path.exists())


class NeedsBuildTests(unittest.TestCase):
    def test_true_when_label_absent_from_cache(self):
        self.assertTrue(needs_build("//a:a_lib", "abc123", {}))

    def test_true_when_fingerprint_differs(self):
        cache = {"//a:a_lib": "old"}
        self.assertTrue(needs_build("//a:a_lib", "new", cache))

    def test_false_when_fingerprint_matches(self):
        cache = {"//a:a_lib": "same"}
        self.assertFalse(needs_build("//a:a_lib", "same", cache))


if __name__ == "__main__":
    unittest.main()
