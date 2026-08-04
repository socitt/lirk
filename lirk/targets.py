"""Parsing of BUILD.lirk target-declaration files (TOML syntax).

See docs/build-format.md for the schema, and docs/DESIGN.md for the
target model and the format tradeoff behind choosing TOML.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

BUILD_FILENAME = "BUILD.lirk"
ROOT_MARKER = ".lirk-root"
VALID_TYPES = {"library", "test"}
KNOWN_KEYS = {"name", "type", "srcs", "deps", "data"}
ROOT_CONFIG_KEYS = {"ignore"}


class ConfigError(Exception):
    """A BUILD.lirk file is missing, malformed, or invalid."""


def load_ignores(root: Path) -> tuple[str, ...]:
    """Read the optional `ignore` list from the repo's .lirk-root marker.

    The marker doubles as repo-level config: an empty file means "the
    root is here" and nothing more, which is what it meant before this
    existed, so existing repos are unaffected. TOML content adds to it:

        ignore = ["tests/fixtures", "vendor"]

    Each entry is a directory path relative to the repo root, excluded
    from the BUILD.lirk scan along with everything beneath it. This is
    for directories that legitimately contain BUILD.lirk files that are
    not this repo's targets -- test fixtures, a vendored dependency, a
    nested checkout -- which the dot-prefix rule alone cannot express.
    """
    marker = root / ROOT_MARKER
    if not marker.is_file():
        return ()

    try:
        with marker.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{marker}: invalid TOML: {e}") from e

    unknown = sorted(set(data) - ROOT_CONFIG_KEYS)
    if unknown:
        raise ConfigError(f"{marker}: unknown key(s): {', '.join(unknown)}")

    ignore = _string_list(data.get("ignore", []), "ignore", str(marker))
    for entry in ignore:
        if entry.startswith("/") or ".." in Path(entry).parts:
            raise ConfigError(
                f"{marker}: ignore entry {entry!r} must be a path relative to "
                "the repo root, without '..'"
            )
    return tuple(ignore)


@dataclass(frozen=True)
class Target:
    name: str
    type: str
    srcs: tuple[str, ...]
    deps: tuple[str, ...]
    data: tuple[str, ...]
    package: str  # e.g. "path/to/pkg"; "" for a package at repo root

    @property
    def label(self) -> str:
        return f"//{self.package}:{self.name}"


def parse_build_file(path: Path, package: str) -> list[Target]:
    """Parse one BUILD.lirk file into its declared Targets."""
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e

    raw_targets = data.get("target", [])
    if not isinstance(raw_targets, list):
        raise ConfigError(
            f"{path}: 'target' must be an array of tables ([[target]])"
        )

    targets = [
        _parse_target(raw, path, package, index)
        for index, raw in enumerate(raw_targets)
    ]

    seen = set()
    for t in targets:
        if t.name in seen:
            raise ConfigError(f"{path}: duplicate target name '{t.name}'")
        seen.add(t.name)

    return targets


def _parse_target(raw: dict, path: Path, package: str, index: int) -> Target:
    where = f"{path} (target #{index + 1})"

    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: each [[target]] entry must be a table")

    unknown = sorted(set(raw) - KNOWN_KEYS)
    if unknown:
        raise ConfigError(f"{where}: unknown key(s): {', '.join(unknown)}")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ConfigError(f"{where}: 'name' must be a non-empty string")

    type_ = raw.get("type")
    if type_ not in VALID_TYPES:
        raise ConfigError(
            f"{where}: 'type' must be one of {sorted(VALID_TYPES)}, "
            f"got {type_!r}"
        )

    srcs = _string_list(raw.get("srcs", []), "srcs", where)
    deps = _string_list(raw.get("deps", []), "deps", where)
    data = _string_list(raw.get("data", []), "data", where)

    # Every src is parsed as Python, so a non-.py src is a declaration
    # error rather than something to discover at build time. Catching it
    # by extension is what makes the srcs/data split self-teaching: left
    # to `ast.parse`, whether a text file is caught depends on what it
    # says -- "a rough note" is a syntax error, "hello" parses fine and
    # sails through into srcs, where every consumer assumes it's
    # importable. This cannot catch a *mislabelled* file (a binary named
    # .py), which is why validate_target still guards decoding.
    for src in srcs:
        if not src.endswith(".py"):
            raise ConfigError(
                f"{where}: src {src!r} is not a .py file -- every src is "
                "parsed as Python; declare fixtures and other non-source "
                "inputs as 'data' instead"
            )

    if type_ == "test" and not srcs:
        raise ConfigError(f"{where}: a 'test' target must declare at least one src")

    return Target(
        name=name,
        type=type_,
        srcs=tuple(srcs),
        deps=tuple(deps),
        data=tuple(data),
        package=package,
    )


def _string_list(value: object, field: str, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where}: '{field}' must be a list of strings")
    return value
