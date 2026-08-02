import tempfile
import unittest
from pathlib import Path

from lirk.targets import ROOT_MARKER, ConfigError, load_ignores, parse_build_file


class ParseBuildFileTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.dir = Path(self._tmpdir.name)

    def _write(self, contents: str) -> Path:
        path = self.dir / "BUILD.lirk"
        path.write_text(contents)
        return path

    def test_parses_library_and_test_targets(self):
        path = self._write(
            """
            [[target]]
            name = "mylib"
            type = "library"
            srcs = ["mylib.py"]
            deps = ["//other/pkg:othertarget"]

            [[target]]
            name = "mylib_test"
            type = "test"
            srcs = ["test_mylib.py"]
            deps = [":mylib"]
            """
        )

        targets = parse_build_file(path, package="pkg")

        self.assertEqual(len(targets), 2)
        lib, test = targets
        self.assertEqual(lib.name, "mylib")
        self.assertEqual(lib.type, "library")
        self.assertEqual(lib.srcs, ("mylib.py",))
        self.assertEqual(lib.deps, ("//other/pkg:othertarget",))
        self.assertEqual(lib.label, "//pkg:mylib")

        self.assertEqual(test.name, "mylib_test")
        self.assertEqual(test.type, "test")
        self.assertEqual(test.deps, (":mylib",))

    def test_data_field_is_parsed_and_defaults_to_empty(self):
        path = self._write(
            """
            [[target]]
            name = "mylib"
            type = "library"
            srcs = ["mylib.py"]
            data = ["story.txt"]

            [[target]]
            name = "bare"
            type = "library"
            """
        )

        with_data, without_data = parse_build_file(path, package="pkg")

        self.assertEqual(with_data.data, ("story.txt",))
        self.assertEqual(without_data.data, ())

    def test_srcs_and_deps_default_to_empty(self):
        path = self._write(
            """
            [[target]]
            name = "bare"
            type = "library"
            """
        )

        [target] = parse_build_file(path, package="")

        self.assertEqual(target.srcs, ())
        self.assertEqual(target.deps, ())
        self.assertEqual(target.label, "//:bare")

    def test_empty_file_has_no_targets(self):
        path = self._write("")
        self.assertEqual(parse_build_file(path, package="pkg"), [])

    def test_invalid_toml_raises_config_error(self):
        path = self._write("this is not [ valid toml")
        with self.assertRaisesRegex(ConfigError, "invalid TOML"):
            parse_build_file(path, package="pkg")

    def test_missing_name_raises_config_error(self):
        path = self._write(
            """
            [[target]]
            type = "library"
            """
        )
        with self.assertRaisesRegex(ConfigError, "'name'"):
            parse_build_file(path, package="pkg")

    def test_invalid_type_raises_config_error(self):
        path = self._write(
            """
            [[target]]
            name = "x"
            type = "binary"
            """
        )
        with self.assertRaisesRegex(ConfigError, "'type'"):
            parse_build_file(path, package="pkg")

    def test_duplicate_names_raise_config_error(self):
        path = self._write(
            """
            [[target]]
            name = "dup"
            type = "library"

            [[target]]
            name = "dup"
            type = "test"
            srcs = ["test_dup.py"]
            """
        )
        with self.assertRaisesRegex(ConfigError, "duplicate target name"):
            parse_build_file(path, package="pkg")

    def test_non_list_srcs_raises_config_error(self):
        path = self._write(
            """
            [[target]]
            name = "x"
            type = "library"
            srcs = "not_a_list.py"
            """
        )
        with self.assertRaisesRegex(ConfigError, "'srcs'"):
            parse_build_file(path, package="pkg")

    def test_test_target_with_no_srcs_raises_config_error(self):
        path = self._write(
            """
            [[target]]
            name = "empty_test"
            type = "test"
            """
        )
        with self.assertRaisesRegex(ConfigError, "must declare at least one src"):
            parse_build_file(path, package="pkg")

    def test_library_target_with_no_srcs_is_allowed(self):
        path = self._write(
            """
            [[target]]
            name = "empty_lib"
            type = "library"
            """
        )
        [target] = parse_build_file(path, package="pkg")
        self.assertEqual(target.srcs, ())

    def test_unknown_key_raises_config_error(self):
        path = self._write(
            """
            [[target]]
            name = "x"
            type = "library"
            dpes = [":something"]
            """
        )
        with self.assertRaisesRegex(ConfigError, "unknown key\\(s\\): dpes"):
            parse_build_file(path, package="pkg")

    def test_target_table_must_be_array(self):
        path = self._write(
            """
            [target]
            name = "x"
            type = "library"
            """
        )
        with self.assertRaisesRegex(ConfigError, "array of tables"):
            parse_build_file(path, package="pkg")


class LoadIgnoresTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)

    def _write_marker(self, contents: str) -> None:
        (self.root / ROOT_MARKER).write_text(contents)

    def test_absent_marker_yields_no_ignores(self):
        self.assertEqual(load_ignores(self.root), ())

    def test_empty_marker_yields_no_ignores(self):
        # The marker predates carrying any config; an empty one has
        # always meant "the root is here" and must keep meaning that.
        self._write_marker("")
        self.assertEqual(load_ignores(self.root), ())

    def test_reads_the_ignore_list(self):
        self._write_marker('ignore = ["tests/fixtures", "vendor"]\n')
        self.assertEqual(load_ignores(self.root), ("tests/fixtures", "vendor"))

    def test_rejects_unknown_keys(self):
        self._write_marker('ignroe = ["vendor"]\n')
        with self.assertRaisesRegex(ConfigError, r"unknown key\(s\): ignroe"):
            load_ignores(self.root)

    def test_rejects_non_list_ignore(self):
        self._write_marker('ignore = "vendor"\n')
        with self.assertRaisesRegex(ConfigError, "'ignore' must be a list of strings"):
            load_ignores(self.root)

    def test_rejects_invalid_toml(self):
        self._write_marker("ignore = [\n")
        with self.assertRaisesRegex(ConfigError, "invalid TOML"):
            load_ignores(self.root)

    def test_rejects_absolute_and_parent_paths(self):
        # An ignore entry escaping the repo root is meaningless at best
        # and surprising at worst, so it's rejected rather than clamped.
        for bad in ("/etc", "../outside", "a/../../outside"):
            with self.subTest(entry=bad):
                self._write_marker(f'ignore = ["{bad}"]\n')
                with self.assertRaisesRegex(ConfigError, "relative to the repo root"):
                    load_ignores(self.root)


if __name__ == "__main__":
    unittest.main()
