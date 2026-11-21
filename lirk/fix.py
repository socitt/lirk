"""`lirk fix`: add the `deps` entries the import check says are missing.

The import check (actions.import_problems) already knows, for every
undeclared cross-package import, exactly which target owns the imported
file. This module turns that diagnosis into an edit, under three rules:

- **Never guess.** A file declared by two targets, or an import of a file
  no target declares, is reported for a hand fix, not resolved by picking.
- **Never introduce a cycle.** Each addition is checked against the graph
  *including the additions already planned in this run*, so two targets
  importing each other cannot both be "fixed" into a loop.
- **Never damage a BUILD file.** There is no TOML writer in the stdlib, so
  edits are textual -- which preserves comments and layout -- and every
  edited file is re-parsed before it is written. If the re-parsed targets
  are not exactly the originals plus the intended deps, nothing is written
  and the change is reported for a hand fix instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lirk.actions import ImportEnv, import_problems, owner_index, parse_target
from lirk.graph import Graph, transitive_closure
from lirk.targets import BUILD_FILENAME, ConfigError, Target, parse_build_text


class EditError(Exception):
    """A BUILD.lirk could not be edited safely by text substitution."""


@dataclass
class FixPlan:
    # label -> deps to add, as they will be written (":x" or "//p:x")
    additions: dict[str, list[str]] = field(default_factory=dict)
    # (label, human-readable reason) for problems needing a hand fix
    manual: list[tuple[str, str]] = field(default_factory=list)


def _dep_spelling(owner: str, target: Target) -> str:
    """`:name` for a same-package dep, the full label otherwise -- the
    form a person would have written."""
    package, _, name = owner[2:].rpartition(":")
    return f":{name}" if package == target.package else owner


def plan_fixes(root: Path, graph: Graph, scope: list[str]) -> FixPlan:
    """Work out which deps to add to which targets in `scope` (a
    topologically ordered list of labels). Writes nothing."""
    plan = FixPlan()
    owners = owner_index(graph.targets, root)
    # A working copy of the edges, extended as additions are planned, so
    # cycle checks see this run's earlier decisions.
    edges = {label: list(deps) for label, deps in graph.edges.items()}
    working = Graph(targets=graph.targets, edges=edges)  # type: ignore[arg-type]  # lists, not tuples

    for label in scope:
        target = graph.targets[label]
        parsed, error = parse_target(target, root)
        if error is not None:
            plan.manual.append((label, f"cannot check imports: {error.message}"))
            continue
        env = ImportEnv(owners=owners, allowed=transitive_closure(working, {label}))
        chosen: list[str] = []
        for problem in import_problems(target, root, env, parsed):
            if not problem.owners:
                plan.manual.append(
                    (label, f"{problem.message()} -- declare it in some target's "
                            "srcs, then run fix again")
                )
                continue
            if len(problem.owners) > 1:
                plan.manual.append(
                    (label, f"{problem.message()} -- declared by several targets; "
                            "pick one and add it to deps")
                )
                continue
            (owner,) = problem.owners
            if owner in chosen:
                continue
            if label in transitive_closure(working, {owner}):
                plan.manual.append(
                    (label, f"{problem.message()} -- adding {owner} would create a "
                            "dependency cycle")
                )
                continue
            chosen.append(owner)
            edges[label].append(owner)

        # Drop any addition another addition already reaches: the check is
        # against the closure, so the narrower edge is redundant.
        minimal = [
            dep for dep in chosen
            if not any(
                dep != other and dep in transitive_closure(working, {other})
                for other in chosen
            )
        ]
        if minimal:
            plan.additions[label] = [_dep_spelling(d, target) for d in minimal]
    return plan


_HEADER = re.compile(r"^[ \t]*\[\[[ \t]*target[ \t]*\]\][ \t]*(?:#.*)?$", re.MULTILINE)


def _scan_array(text: str, open_idx: int) -> tuple[int, list[tuple[int, int]]]:
    """Index of the `]` closing the array opened at `open_idx`, and the
    (start, end) span of each top-level string literal inside it."""
    strings: list[tuple[int, int]] = []
    depth = 0
    i = open_idx
    while i < len(text):
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < len(text) and text[j] != c:
                if c == '"' and text[j] == "\\":
                    j += 1
                if text[j] == "\n":
                    raise EditError("unterminated string in deps")
                j += 1
            if depth == 1:
                strings.append((i, j + 1))
            i = j + 1
            continue
        if c == "#":
            nl = text.find("\n", i)
            i = len(text) if nl == -1 else nl
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i, strings
        i += 1
    raise EditError("unterminated deps array")


def add_deps_to_text(text: str, target_name: str, new_deps: list[str]) -> str:
    """`text` (a BUILD.lirk) with `new_deps` appended to the named
    target's `deps`, creating the key if absent. Raises EditError if the
    target's table cannot be located unambiguously."""
    headers = [m.start() for m in _HEADER.finditer(text)]
    blocks = [
        (start, headers[i + 1] if i + 1 < len(headers) else len(text))
        for i, start in enumerate(headers)
    ]
    name_re = re.compile(r"^[ \t]*name[ \t]*=[ \t]*([\"'])(.*?)\1[ \t]*(?:#.*)?$", re.MULTILINE)
    matches = []
    for start, end in blocks:
        m = name_re.search(text, start, end)
        if m and m.group(2) == target_name:
            matches.append((start, end, m))
    if len(matches) != 1:
        raise EditError(f"could not find exactly one [[target]] named {target_name!r}")
    start, end, name_match = matches[0]
    quoted = [f'"{d}"' for d in new_deps]

    deps_m = re.compile(r"^([ \t]*)deps[ \t]*=[ \t]*\[", re.MULTILINE).search(text, start, end)
    if deps_m is None:
        # Added on the line after `name`, at the same indent. Key order
        # within a TOML table carries no meaning.
        indent = re.match(r"[ \t]*", name_match.group(0)).group(0)
        line_end = name_match.end()
        return text[:line_end] + f"\n{indent}deps = [{', '.join(quoted)}]" + text[line_end:]

    open_idx = deps_m.end() - 1
    close_idx, strings = _scan_array(text, open_idx)
    multiline = "\n" in text[open_idx:close_idx]

    if not strings:
        if not multiline:
            return text[: open_idx + 1] + ", ".join(quoted) + text[close_idx:]
        line_start = text.rfind("\n", 0, close_idx) + 1
        indent = deps_m.group(1) + "    "
        lines = "".join(f"{indent}{q},\n" for q in quoted)
        return text[:line_start] + lines + text[line_start:]

    last_start, last_end = strings[-1]
    if not multiline:
        return text[:last_end] + "".join(f", {q}" for q in quoted) + text[last_end:]

    # Multiline: give the last existing item a comma if it lacks one, and
    # put each new item on its own line after it, matching its indent, so
    # a trailing comment on that line stays where it was.
    line_start = text.rfind("\n", 0, last_start) + 1
    indent = text[line_start:last_start]
    if indent.strip():
        # Something precedes the last item on its line (`deps = ["a",`),
        # so its column is not an indent to copy.
        indent = deps_m.group(1) + "    "
    line_end = text.find("\n", last_end)
    if line_end == -1 or line_end > close_idx:
        # The closing bracket shares the last item's line.
        tail = "".join(f",\n{indent}{q}" for q in quoted)
        return text[:last_end] + tail + text[last_end:]
    after = text[last_end:line_end]
    needs_comma = not after.lstrip().startswith(",")
    head = text[:last_end] + ("," if needs_comma else "") + text[last_end:line_end + 1]
    lines = "".join(f"{indent}{q},\n" for q in quoted)
    return head + lines + text[line_end + 1:]


def apply_plan(root: Path, graph: Graph, plan: FixPlan, write: bool) -> FixPlan:
    """Edit each affected BUILD.lirk. Returns the additions that were (or,
    with write=False, would be) applied; files that fail verification are
    moved to `manual` and left untouched."""
    applied = FixPlan(manual=list(plan.manual))
    by_package: dict[str, list[str]] = {}
    for label in plan.additions:
        by_package.setdefault(graph.targets[label].package, []).append(label)

    for package, labels in sorted(by_package.items()):
        path = root / package / BUILD_FILENAME
        original = path.read_text(encoding="utf-8")
        text = original
        try:
            for label in labels:
                text = add_deps_to_text(text, graph.targets[label].name, plan.additions[label])
            _verify_edit(path, package, original, text, graph, plan, labels)
        except (EditError, ConfigError) as e:
            for label in labels:
                applied.manual.append(
                    (label, f"could not edit {path.relative_to(root)} safely ({e}); "
                            f"add {', '.join(plan.additions[label])} to deps by hand")
                )
            continue
        if write:
            path.write_text(text, encoding="utf-8")
        for label in labels:
            applied.additions[label] = plan.additions[label]
    return applied


def _verify_edit(
    path: Path,
    package: str,
    original: str,
    edited: str,
    graph: Graph,
    plan: FixPlan,
    labels: list[str],
) -> None:
    """Raise EditError unless `edited` parses to exactly the original
    targets, with only the planned deps appended to the planned ones."""
    before = {t.name: t for t in parse_build_text(original, path, package)}
    after = {t.name: t for t in parse_build_text(edited, path, package)}
    if set(before) != set(after):
        raise EditError("the edit changed which targets the file declares")
    wanted = {graph.targets[l].name: plan.additions[l] for l in labels}
    for name, old in before.items():
        expected = old.deps + tuple(wanted.get(name, ()))
        if after[name].deps != expected:
            raise EditError(f"deps of {name!r} did not come out as intended")
        if (after[name].srcs, after[name].data, after[name].type) != (old.srcs, old.data, old.type):
            raise EditError(f"the edit disturbed other fields of {name!r}")
