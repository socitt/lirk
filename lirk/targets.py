"""Parsing of BUILD.lirk target-declaration files (TOML syntax).

See docs/design/target-format.md for the schema and the format
tradeoff behind choosing TOML.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

BUILD_FILENAME = "BUILD.lirk"
VALID_TYPES = {"library", "test"}
KNOWN_KEYS = {"name", "type", "srcs", "deps", "data"}


class ConfigError(Exception):
    """A BUILD.lirk file is missing, malformed, or invalid."""


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
