#!/usr/bin/env python3
"""Validate the published catalog against its versioned JSON Schemas."""

from __future__ import annotations

import json
import pathlib
import sys

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_json(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def validate_catalog(catalog: dict) -> list[str]:
    index_schema = load_json(ROOT / "schemas/catalog-index-v1.schema.json")
    entry_schema = load_json(ROOT / "schemas/catalog-entry-v1.schema.json")
    version_schema = load_json(ROOT / "schemas/catalog-entry-version-v1.schema.json")
    presentation_schema = load_json(ROOT / "schemas/presentation-v1.schema.json")
    registry = Registry()
    for schema in (entry_schema, version_schema, presentation_schema):
        registry = registry.with_resource(
            schema["$id"], Resource.from_contents(schema)
        )
    validator = Draft202012Validator(
        index_schema,
        registry=registry,
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(catalog), key=lambda error: list(error.path))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


def validate_revocations(document: dict) -> list[str]:
    schema = load_json(ROOT / "schemas/revocations-v1.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


def main() -> int:
    errors = validate_catalog(load_json(ROOT / "catalog.json"))
    errors.extend(validate_revocations(load_json(ROOT / "policies/revocations.json")))
    if errors:
        print("catalog schema validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("catalog and revocation policy conform to their v1 schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
