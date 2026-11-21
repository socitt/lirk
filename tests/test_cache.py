import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lirk import cache as cache_module
from lirk.cache import (
    compute_fingerprints,
    environment_fingerprint,
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

    def test_test_timeout_is_part_of_the_fingerprint(self):
        # A pass under a generous budget says nothing about a tight one.
        build = self.root / "c" / "BUILD.lirk"
        original = build.read_text()
        _, _, before = self._fingerprints()

        build.write_text(original.replace('name = "c_test"', 'name = "c_test"\ntimeout = 5'))
        _, _, five = self._fingerprints()
        build.write_text(original.replace('name = "c_test"', 'name = "c_test"\ntimeout = 9'))
        _, _, nine = self._fingerprints()

        self.assertNotEqual(before["//c:c_test"], five["//c:c_test"])
        self.assertNotEqual(five["//c:c_test"], nine["//c:c_test"])
        self.assertEqual(before["//c:c_lib"], five["//c:c_lib"])

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


class DataDirectoryFingerprintTests(unittest.TestCase):
    LABEL = "//pkg:lib_with_data_dir"

    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "datadir_repo", self.root)
        self.assets = self.root / "pkg" / "assets"

    def _fingerprint(self):
        graph = build_graph(self.root)
        order = topological_sort(graph)
        return compute_fingerprints(graph, self.root, order)[self.LABEL]

    def test_deterministic_across_runs(self):
        self.assertEqual(self._fingerprint(), self._fingerprint())

    def test_editing_a_nested_data_file_changes_the_fingerprint(self):
        before = self._fingerprint()
        (self.assets / "sub" / "nested.txt").write_text("edited\n")
        self.assertNotEqual(before, self._fingerprint())

    def test_adding_a_data_file_changes_the_fingerprint(self):
        # Contents alone would not catch this -- the relative path of
        # each file is folded into the hash for exactly this case.
        before = self._fingerprint()
        (self.assets / "added.txt").write_text("added\n")
        self.assertNotEqual(before, self._fingerprint())

    def test_removing_a_data_file_changes_the_fingerprint(self):
        before = self._fingerprint()
        (self.assets / "top.txt").unlink()
        self.assertNotEqual(before, self._fingerprint())

    def test_generated_pycache_does_not_change_the_fingerprint(self):
        # Running a test writes .pyc files into a fixture tree. If those
        # counted, the fingerprint would change on every run and nothing
        # would ever stay cached.
        before = self._fingerprint()
        pycache = self.assets / "sub" / "__pycache__"
        pycache.mkdir()
        (pycache / "nested.cpython-312.pyc").write_bytes(b"\x00generated")
        (self.assets / ".hidden").write_text("hidden\n")
        self.assertEqual(before, self._fingerprint())


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


class EnvironmentFingerprintTests(unittest.TestCase):
    """The interpreter and installed packages are inputs too: changing
    either must invalidate cached results, not leave a stale green."""

    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.site = Path(tmpdir.name) / "site-packages"
        self.site.mkdir()
        (self.site / "requests-2.31.0.dist-info").mkdir()
        (self.site / "requests").mkdir()

    def _fp(self):
        return environment_fingerprint([str(self.site)])

    def test_stable_when_nothing_changes(self):
        self.assertEqual(self._fp(), self._fp())

    def test_package_upgrade_changes_it(self):
        before = self._fp()
        (self.site / "requests-2.31.0.dist-info").rename(self.site / "requests-2.32.0.dist-info")
        self.assertNotEqual(before, self._fp())

    def test_install_and_removal_change_it(self):
        before = self._fp()
        (self.site / "attrs-23.1.0.dist-info").mkdir()
        installed = self._fp()
        self.assertNotEqual(before, installed)
        (self.site / "attrs-23.1.0.dist-info").rmdir()
        self.assertEqual(before, self._fp())

    def test_package_contents_and_non_metadata_entries_are_ignored(self):
        # Only metadata names count: the listing must not be perturbed
        # by __pycache__ churn or by files inside a package.
        before = self._fp()
        (self.site / "requests" / "extra.py").write_text("")
        (self.site / "__pycache__").mkdir()
        self.assertEqual(before, self._fp())

    def test_legacy_egg_info_counts(self):
        before = self._fp()
        (self.site / "oldpkg-1.0.egg-info").mkdir()
        self.assertNotEqual(before, self._fp())

    def test_missing_site_dir_is_harmless(self):
        environment_fingerprint([str(self.site / "nope")])

    def test_interpreter_version_changes_it(self):
        before = self._fp()
        with patch.object(cache_module.sys, "version_info", (3, 99, 0)):
            self.assertNotEqual(before, self._fp())

    def test_environment_reaches_every_target_fingerprint(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "repo"
        shutil.copytree(FIXTURES / "sample_repo", root)
        graph = build_graph(root)
        order = topological_sort(graph)

        one = compute_fingerprints(graph, root, order, environment="env-one")
        two = compute_fingerprints(graph, root, order, environment="env-two")

        for label in graph.targets:
            self.assertNotEqual(one[label], two[label], label)


class PytestFingerprintTests(unittest.TestCase):
    """Files pytest reads but which are not srcs must still invalidate."""

    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name)
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "test_x.py").write_text("def test_x():\n    pass\n")
        self._write_build('runner = "pytest"\n')

    def _write_build(self, extra):
        (self.root / "pkg" / "BUILD.lirk").write_text(
            '[[target]]\nname = "t"\ntype = "test"\nsrcs = ["test_x.py"]\n' + extra
        )

    def _fp(self):
        graph = build_graph(self.root)
        return compute_fingerprints(graph, self.root, topological_sort(graph), environment="e")["//pkg:t"]

    def test_editing_a_package_conftest_invalidates(self):
        (self.root / "pkg" / "conftest.py").write_text("A = 1\n")
        before = self._fp()
        (self.root / "pkg" / "conftest.py").write_text("A = 2\n")
        self.assertNotEqual(before, self._fp())

    def test_adding_a_root_conftest_invalidates(self):
        before = self._fp()
        (self.root / "conftest.py").write_text("")
        self.assertNotEqual(before, self._fp())

    def test_editing_root_pytest_config_invalidates(self):
        (self.root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        before = self._fp()
        (self.root / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-x'\n")
        self.assertNotEqual(before, self._fp())

    def test_switching_runner_invalidates(self):
        before = self._fp()
        self._write_build("")
        self.assertNotEqual(before, self._fp())

    def test_unittest_target_ignores_conftest(self):
        self._write_build("")
        before = self._fp()
        (self.root / "conftest.py").write_text("")
        self.assertEqual(before, self._fp())


if __name__ == "__main__":
    unittest.main()
