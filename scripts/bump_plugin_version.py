#!/usr/bin/env python3
"""Rewrite only the plugin.yaml version: line. Refuse duplicate keys or a wrong name."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin.yaml"
PYPROJECT = ROOT / "pyproject.toml"
PKG_INIT = ROOT / "uirizz_plugin" / "__init__.py"
EXPECTED_NAME = "uirizz"
VERSION_LINE = re.compile(r'^version:\s*"([^"]+)"\s*$')


def _strict_load(text: str):
    from ruamel.yaml import YAML
    from ruamel.yaml.constructor import DuplicateKeyError

    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    try:
        return yaml.load(text), None
    except DuplicateKeyError as exc:
        return None, exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump uirizz plugin.yaml version.")
    parser.add_argument("version", help="New SemVer, for example 0.1.1")
    args = parser.parse_args()
    new = args.version
    if not re.fullmatch(r"\d+\.\d+\.\d+", new):
        print("version must be SemVer like 0.1.1", file=sys.stderr)
        return 1

    text = PLUGIN.read_text(encoding="utf-8")
    data, err = _strict_load(text)
    if err is not None:
        print(f"duplicate key in plugin.yaml: {err}", file=sys.stderr)
        return 1
    if not isinstance(data, dict) or data.get("name") != EXPECTED_NAME:
        print(f"plugin.yaml name must be {EXPECTED_NAME}", file=sys.stderr)
        return 1
    if sum(1 for line in text.splitlines() if line.startswith("version:")) != 1:
        print("plugin.yaml must have exactly one version: line", file=sys.stderr)
        return 1

    lines = []
    replaced = False
    for line in text.splitlines(keepends=True):
        if VERSION_LINE.match(line.rstrip("\n")) and not replaced:
            nl = "\n" if line.endswith("\n") else ""
            lines.append(f'version: "{new}"{nl}')
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        print("could not find version: line", file=sys.stderr)
        return 1
    PLUGIN.write_text("".join(lines), encoding="utf-8")

    if PYPROJECT.is_file():
        py = PYPROJECT.read_text(encoding="utf-8")
        py, n = re.subn(
            r'(?m)^version = "[^"]+"',
            f'version = "{new}"',
            py,
            count=1,
        )
        if n != 1:
            print("could not update pyproject.toml version", file=sys.stderr)
            return 1
        PYPROJECT.write_text(py, encoding="utf-8")

    if PKG_INIT.is_file():
        init = PKG_INIT.read_text(encoding="utf-8")
        init, n = re.subn(
            r'__version__ = "[^"]+"',
            f'__version__ = "{new}"',
            init,
            count=1,
        )
        if n != 1:
            print("could not update uirizz_plugin/__init__.py __version__", file=sys.stderr)
            return 1
        PKG_INIT.write_text(init, encoding="utf-8")

    print(f"bumped {EXPECTED_NAME} to {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
