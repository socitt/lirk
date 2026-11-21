import contextlib
import io
import tempfile
import tomllib
import unittest
from pathlib import Path

from lirk.cli import main
from lirk.scaffold import draft_packages

UNITTEST_MODULE = (
    "import unittest\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_ok(self):\n"
    "        self.assertTrue(True)\n"
)


class DraftPackagesTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name) / "myrepo"
        self.root.mkdir()

    def _file(self, rel, body=""):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def _drafts(self):
        drafts, kept, self.skipped = draft_packages(self.root)
        return {d.package: d for d in drafts}, kept

    def test_splits_library_and_test_files(self):
        self._file("pkg/__init__.py")
        self._file("pkg/core.py")
        self._file("pkg/test_core.py", UNITTEST_MODULE)
        self._file("pkg/core_test.py", UNITTEST_MODULE)
        d = self._drafts()[0]["pkg"]
        self.assertEqual(d.name, "pkg")
        self.assertEqual(d.srcs, ["__init__.py", "core.py"])
        self.assertEqual(d.tests, ["core_test.py", "test_core.py"])
        self.assertEqual(d.runner, "unittest")

    def test_plain_function_tests_mean_pytest(self):
        self._file("pkg/test_x.py", "def test_x():\n    assert True\n")
        self.assertEqual(self._drafts()[0]["pkg"].runner, "pytest")

    def test_importing_pytest_means_pytest_even_alongside_unittest(self):
        self._file("pkg/test_x.py", "import pytest\nimport unittest\n")
        self.assertEqual(self._drafts()[0]["pkg"].runner, "pytest")

    def test_conftest_is_neither_src_nor_test(self):
        self._file("pkg/conftest.py")
        self._file("pkg/mod.py")
        d = self._drafts()[0]["pkg"]
        self.assertEqual((d.srcs, d.tests), (["mod.py"], []))

    def test_a_directory_of_only_tests_gets_only_a_test_target(self):
        self._file("tests/test_a.py", UNITTEST_MODULE)
        d = self._drafts()[0]["tests"]
        self.assertIsNone(d.library_label)
        self.assertEqual(d.test_label, "//tests:tests_test")

    def test_root_package_is_named_after_the_repo_directory(self):
        self._file("tool.py")
        self.assertEqual(self._drafts()[0][""].name, "myrepo")

    def test_environments_generated_and_hidden_directories_are_skipped(self):
        self._file("venvlike/pyvenv.cfg")
        self._file("venvlike/lib/site.py")
        for d in ("build", "dist", "node_modules", "__pycache__", ".hidden"):
            self._file(f"{d}/x.py")
        self._file("real/x.py")
        self.assertEqual(set(self._drafts()[0]), {"real"})
        # The ones a person might have meant as code are named, with why.
        self.assertEqual(
            sorted(self.skipped),
            [("build", "looks like build output"), ("dist", "looks like build output"),
             ("venvlike", "a virtualenv")],
        )

    def test_packages_named_env_or_venv_are_ordinary_code(self):
        # slingshot has an env/ package (RL environments); it was dropped
        # silently by name. Only a pyvenv.cfg marks a virtualenv.
        self._file("env/navigation.py")
        self._file("venv/x.py")
        self.assertEqual(set(self._drafts()[0]), {"env", "venv"})

    def test_a_subdirectory_without_python_is_hinted_as_data(self):
        self._file("golden/test_golden.py", UNITTEST_MODULE)
        self._file("golden/data/physics/case1.json", "{}")
        self._file("golden/helpers/util.py")
        self._file("golden/empty/.keep")
        d = self._drafts()[0]["golden"]
        self.assertEqual(d.data_hints, ["data"])

    def test_ignore_list_is_honoured(self):
        self._file(".lirk-root", 'ignore = ["vendor"]\n')
        self._file("vendor/lib/x.py")
        self._file("real/x.py")
        self.assertEqual(set(self._drafts()[0]), {"real"})

    def test_a_package_with_a_build_file_is_kept_not_redrafted(self):
        self._file("done/BUILD.lirk", "")
        self._file("done/x.py")
        drafts, kept = self._drafts()
        self.assertEqual((drafts, kept), ({}, ["done"]))


class InitCommandTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name)

    def _file(self, rel, body=""):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv, root=self.root)
        return code, out.getvalue()

    def _deps(self, package, name):
        data = tomllib.loads((self.root / package / "BUILD.lirk").read_text())
        return next(t for t in data["target"] if t["name"] == name).get("deps")

    def _small_repo(self):
        self._file("lib/__init__.py")
        self._file("lib/shapes.py", "def area(w, h):\n    return w * h\n")
        self._file("app/main.py", "from lib.shapes import area\n\nAREA = area(2, 3)\n")
        self._file(
            "app/test_main.py",
            "import unittest\nfrom main import AREA\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_area(self):\n"
            "        self.assertEqual(AREA, 6)\n",
        )

    def test_init_from_nothing_to_a_passing_test_run(self):
        self._small_repo()
        code, out = self._run(["init"])
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / ".lirk-root").is_file())
        # Deps come from the imports, not from init itself.
        self.assertEqual(self._deps("app", "app"), ["//lib:lib"])
        self.assertEqual(self._deps("app", "app_test"), [":app"])
        self.assertIsNone(self._deps("lib", "lib"))

        code, out = self._run(["test", "//..."])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS   //app:app_test", out)

    def test_rerunning_init_changes_nothing(self):
        self._small_repo()
        self._run(["init"])
        before = (self.root / "app" / "BUILD.lirk").read_text()
        code, out = self._run(["init"])
        self.assertEqual(code, 0)
        self.assertIn("nothing to draft", out)
        self.assertEqual((self.root / "app" / "BUILD.lirk").read_text(), before)

    def test_a_new_package_is_drafted_and_existing_ones_kept(self):
        self._small_repo()
        self._run(["init"])
        self._file("extra/x.py", "from lib.shapes import area\n")
        code, out = self._run(["init"])
        self.assertEqual(code, 0, out)
        self.assertIn("kept   app/BUILD.lirk", out)
        self.assertEqual(self._deps("extra", "extra"), ["//lib:lib"])

    def test_dry_run_writes_nothing(self):
        self._small_repo()
        code, out = self._run(["init", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("would create app/BUILD.lirk", out)
        self.assertEqual(list(self.root.rglob("BUILD.lirk")), [])
        self.assertFalse((self.root / ".lirk-root").exists())

    def test_mutually_importing_packages_are_left_for_a_hand_fix(self):
        self._file("a/a.py", "from b import b\n")
        self._file("b/b.py", "from a import a\n")
        code, out = self._run(["init"])
        self.assertEqual(code, 1)
        self.assertIn("MANUAL", out)
        self.assertIn("cycle", out)
        # Exactly one side got its edge; the other import stays flagged
        # by the build, rather than being "fixed" into a cycle.
        deps = [self._deps("a", "a"), self._deps("b", "b")]
        self.assertEqual(sorted(map(bool, deps)), [False, True])
        code, out = self._run(["build", "//..."])
        self.assertEqual(code, 1)
        self.assertIn("not in deps", out)


if __name__ == "__main__":
    unittest.main()
