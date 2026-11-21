import contextlib
import io
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from lirk import fix
from lirk.cli import main
from lirk.fix import EditError, add_deps_to_text, plan_fixes
from lirk.graph import build_graph, topological_sort

FIXTURES = Path(__file__).parent / "fixtures"


def _deps(text, name):
    for t in tomllib.loads(text)["target"]:
        if t["name"] == name:
            return t.get("deps")
    raise AssertionError(name)


class AddDepsToTextTests(unittest.TestCase):
    """The textual editor: must produce valid TOML with exactly the
    intended deps, and leave everything else -- comments included --
    alone."""

    def test_creates_the_key_when_absent(self):
        text = '[[target]]\nname = "a"\ntype = "library"\n'
        out = add_deps_to_text(text, "a", ["//b:b"])
        self.assertEqual(_deps(out, "a"), ["//b:b"])

    def test_empty_single_line_array(self):
        out = add_deps_to_text('[[target]]\nname = "a"\ndeps = []\n', "a", [":x", ":y"])
        self.assertEqual(_deps(out, "a"), [":x", ":y"])

    def test_single_line_array_with_items_and_trailing_comment(self):
        text = '[[target]]\nname = "a"\ndeps = [":x"]  # keep me\n'
        out = add_deps_to_text(text, "a", ["//b:b"])
        self.assertEqual(_deps(out, "a"), [":x", "//b:b"])
        self.assertIn("# keep me", out)

    def test_single_line_trailing_comma(self):
        out = add_deps_to_text('[[target]]\nname = "a"\ndeps = [":x",]\n', "a", [":y"])
        self.assertEqual(_deps(out, "a"), [":x", ":y"])

    def test_multiline_with_trailing_comma_keeps_layout(self):
        text = '[[target]]\nname = "a"\ndeps = [\n    ":x",  # why x\n]\n'
        out = add_deps_to_text(text, "a", [":y"])
        self.assertEqual(_deps(out, "a"), [":x", ":y"])
        self.assertIn('    ":x",  # why x\n    ":y",\n]', out)

    def test_multiline_without_trailing_comma(self):
        text = '[[target]]\nname = "a"\ndeps = [\n    ":x"\n]\n'
        out = add_deps_to_text(text, "a", [":y"])
        self.assertEqual(_deps(out, "a"), [":x", ":y"])

    def test_multiline_comment_after_last_item_without_comma(self):
        text = '[[target]]\nname = "a"\ndeps = [\n    ":x"  # no comma\n]\n'
        out = add_deps_to_text(text, "a", [":y"])
        self.assertEqual(_deps(out, "a"), [":x", ":y"])
        self.assertIn("# no comma", out)

    def test_empty_multiline_array(self):
        out = add_deps_to_text('[[target]]\nname = "a"\ndeps = [\n]\n', "a", [":y"])
        self.assertEqual(_deps(out, "a"), [":y"])

    def test_closing_bracket_on_the_last_items_line(self):
        text = '[[target]]\nname = "a"\ndeps = [\n    ":x"]\n'
        out = add_deps_to_text(text, "a", [":y"])
        self.assertEqual(_deps(out, "a"), [":x", ":y"])

    def test_first_item_on_the_opening_line(self):
        text = '[[target]]\nname = "a"\ndeps = [":x",\n        ":z"]\n'
        out = add_deps_to_text(text, "a", [":y"])
        self.assertEqual(_deps(out, "a"), [":x", ":z", ":y"])

    def test_only_the_named_target_changes(self):
        text = (
            '# header comment\n[[target]]\nname = "a"\ndeps = [":x"]\n\n'
            '[[target]]\nname = "b"\ndeps = [":x"]\n'
        )
        out = add_deps_to_text(text, "b", [":a"])
        self.assertEqual(_deps(out, "a"), [":x"])
        self.assertEqual(_deps(out, "b"), [":x", ":a"])
        self.assertTrue(out.startswith("# header comment\n"))

    def test_a_bracket_inside_a_string_or_comment_is_not_structure(self):
        text = '[[target]]\nname = "a"\ndeps = [\n    ":x",  # see [notes]\n]\n'
        out = add_deps_to_text(text, "a", [":y"])
        self.assertEqual(_deps(out, "a"), [":x", ":y"])

    def test_unknown_target_raises(self):
        with self.assertRaises(EditError):
            add_deps_to_text('[[target]]\nname = "a"\n', "zzz", [":y"])


class PlanFixesTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name)

    def _pkg(self, name, build, **files):
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "BUILD.lirk").write_text(build)
        for fname, body in files.items():
            (d / f"{fname}.py").write_text(body)

    def _plan(self):
        graph = build_graph(self.root)
        return plan_fixes(self.root, graph, topological_sort(graph))

    def _lib(self, name, deps=()):
        d = f"deps = {list(deps)!r}\n".replace("'", '"') if deps else ""
        return f'[[target]]\nname = "{name}"\ntype = "library"\nsrcs = ["{name}.py"]\n{d}'

    def test_an_edge_that_would_close_a_cycle_is_not_added(self):
        self._pkg("a", self._lib("a", ["//b:b"]), a="X = 1\n")
        self._pkg("b", self._lib("b"), b="from a import a\n")
        plan = self._plan()
        self.assertEqual(plan.additions, {})
        self.assertIn("cycle", plan.manual[0][1])

    def test_mutual_imports_fix_one_side_and_report_the_other(self):
        # Neither edge exists yet; adding both in one run would loop.
        self._pkg("a", self._lib("a"), a="from b import b\n")
        self._pkg("b", self._lib("b"), b="from a import a\n")
        plan = self._plan()
        self.assertEqual(len(plan.additions), 1)
        self.assertEqual(len(plan.manual), 1)
        self.assertIn("cycle", plan.manual[0][1])

    def test_a_file_with_two_owners_is_not_guessed(self):
        self._pkg(
            "s",
            '[[target]]\nname = "one"\ntype = "library"\nsrcs = ["u.py"]\n\n'
            '[[target]]\nname = "two"\ntype = "library"\nsrcs = ["u.py"]\n',
            u="X = 1\n",
        )
        self._pkg("app", self._lib("app"), app="from s import u\n")
        plan = self._plan()
        self.assertEqual(plan.additions, {})
        self.assertIn("several targets", plan.manual[0][1])

    def test_an_addition_reached_through_another_is_dropped(self):
        # app imports both mid and base; mid already depends on base, so
        # adding mid alone satisfies the closure rule.
        self._pkg("base", self._lib("base"), base="X = 1\n")
        self._pkg("mid", self._lib("mid", ["//base:base"]), mid="from base import base\n")
        self._pkg("app", self._lib("app"), app="from mid import mid\nfrom base import base\n")
        plan = self._plan()
        self.assertEqual(plan.additions, {"//app:app": ["//mid:mid"]})

    def test_same_package_deps_use_the_short_spelling(self):
        self._pkg(
            "p",
            self._lib("x") + "\n" + self._lib("y"),
            x="X = 1\n",
            y="from x import X\n",
        )
        self.assertEqual(self._plan().additions, {"//p:y": [":x"]})

    def test_a_syntax_error_is_reported_not_fixed(self):
        self._pkg("a", self._lib("a"), a="def broken(:\n")
        plan = self._plan()
        self.assertIn("cannot check imports", plan.manual[0][1])


class FixCommandTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name) / "repo"
        shutil.copytree(FIXTURES / "import_repo", self.root)
        self.build = self.root / "leaf" / "BUILD.lirk"

    def _run(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(argv, root=self.root)
        return code, out.getvalue()

    def test_fix_then_build_passes_for_everything_fixable(self):
        code, out = self._run(["fix"])
        # orphan_user imports a file no target declares: not auto-fixable.
        self.assertEqual(code, 1)
        self.assertIn("added 3 dep(s) to 3 target(s), 1 need a hand fix", out)
        self.assertIn("MANUAL //leaf:orphan_user", out)
        for label in ("//leaf:undeclared", "//leaf:sibling", "//leaf:undeclared_test"):
            code, out = self._run(["build", label])
            self.assertEqual(code, 0, out)

    def test_fix_is_idempotent(self):
        self._run(["fix"])
        after_first = self.build.read_text()
        _, out = self._run(["fix"])
        self.assertEqual(self.build.read_text(), after_first)
        self.assertIn("added 0 dep(s)", out)

    def test_dry_run_changes_nothing(self):
        before = self.build.read_text()
        code, out = self._run(["fix", "--dry-run"])
        self.assertEqual(self.build.read_text(), before)
        self.assertIn("would fix //leaf:undeclared: would add //base:base", out)
        self.assertNotIn("  fixed ", out)
        self.assertIn("dry run", out)

    def test_scope_limits_what_is_edited(self):
        self._run(["fix", "//leaf:sibling"])
        text = self.build.read_text()
        self.assertEqual(_deps(text, "sibling"), [":helper"])
        self.assertIsNone(_deps(text, "undeclared"))

    def test_exit_zero_when_nothing_needs_a_hand_fix(self):
        code, _ = self._run(["fix", "//leaf:undeclared"])
        self.assertEqual(code, 0)

    def test_an_edit_that_fails_verification_is_not_written(self):
        before = self.build.read_text()
        # Simulate an editor bug: whatever it produces, the re-parse
        # check must catch it and leave the file alone.
        with patch.object(fix, "add_deps_to_text", lambda text, name, deps: text + "\n[[target]]\nname = 1\n"):
            code, out = self._run(["fix", "//leaf:undeclared"])
        self.assertEqual(self.build.read_text(), before)
        self.assertEqual(code, 1)
        self.assertIn("could not edit", out)
        self.assertIn("by hand", out)


if __name__ == "__main__":
    unittest.main()
