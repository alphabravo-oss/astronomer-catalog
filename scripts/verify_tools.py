#!/usr/bin/env python3
"""Verify installed versions against uv.lock and record the tooling environment."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import pathlib
import platform
import sys
import tomllib

import yaml
from jsonschema import FormatChecker
from sync_tools import ROOT, locked_names, package_name


def installed_versions() -> dict[str, str]:
    result = {}
    for distribution in importlib.metadata.distributions():
        name = package_name(distribution.metadata["Name"])
        if name in result:
            raise ValueError("duplicate installed tool distribution")
        result[name] = distribution.version
    return result


def verify_versions(expected: dict[str, str], installed: dict[str, str]) -> None:
    if installed != expected:
        raise ValueError("installed full tool graph differs from uv.lock")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if sys.version_info[:3] != (3, 15, 0):
        raise ValueError("tool environment must use Python 3.15.0")
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    names = locked_names(lock)
    expected = {package_name(row["name"]): row["version"]
                for row in lock["package"] if "registry" in row["source"]}
    if set(expected) != set(names):
        raise ValueError("lock name/version graph mismatch")
    installed = installed_versions()
    verify_versions(expected, installed)
    if yaml.SafeLoader.__module__ != "yaml.loader":
        raise ValueError("PyYAML SafeLoader must remain the pure Python loader")
    FormatChecker().check("https://example.com/catalog", "uri")
    if FormatChecker().conforms("not a URI", "uri"):
        raise ValueError("JSON Schema URI format checker is unavailable")
    value = {"schema_version": 1, "scope": "catalog-tooling-environment",
             "python": platform.python_version(), "system": platform.system(),
             "architecture": platform.machine(), "pure_safe_loader": True,
             "uri_format_checker": True, "distributions": installed}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    print(f"verified all {len(installed)} installed tool versions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
