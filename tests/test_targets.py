import tempfile
import unittest
from pathlib import Path

from lirk.targets import ConfigError, parse_build_file


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


if __name__ == "__main__":
    unittest.main()
