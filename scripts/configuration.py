"""Version-bound, offline catalog configuration contract validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def attach_configurations(catalog: dict, root: Path, lock: dict) -> None:
    """Materialize reviewed version records, rejecting stale identities before publication."""
    known = {entry["slug"] for entry in catalog["applications"]}
    unknown = {path.name for path in (root / "configurations").glob("*") if path.is_dir()} - known
    if unknown:
        raise ValueError("configuration directories have no catalog entry: " + ", ".join(sorted(unknown)))
    for entry in catalog["applications"]:
        paths = sorted((root / "configurations" / entry["slug"]).glob("*.json"))
        if not paths:
            continue
        records = [json.loads(path.read_text()) for path in paths]
        if any(path.stem != record.get("version") for path, record in zip(paths, records, strict=True)):
            raise ValueError("configuration filename must equal the exact chart version")
        validate_versions(entry, records, lock["entries"][entry["slug"]])
        entry["artifact"]["versions"] = records


def validate_versions(entry: dict, records: list[dict], locked: dict) -> None:
    versions: set[str] = set()
    recommended = []
    for record in records:
        version = record["version"]
        if version in versions:
            raise ValueError(f"{entry['slug']}: duplicate version {version}")
        versions.add(version)
        artifact = record["artifact"]
        if (artifact["repository"], artifact["name"], artifact["version"]) != (
            entry["artifact"]["repository"], entry["artifact"]["chart"], version
        ) or artifact["digest"] != record["identities"]["chartDigest"]:
            raise ValueError(f"{entry['slug']}: configuration identity mismatch")
        if record.get("supportTier") == "astronomer":
            # Qualification is granted through the separately validated primary assurance profile.
            if version != entry["artifact"]["version"] or entry["supportTier"] != "astronomer":
                raise ValueError("version support requires a qualified primary assurance profile")
        if record.get("recommended"):
            recommended.append(version)
            if not record.get("available") or record.get("revoked") or record.get("deprecated"):
                raise ValueError("recommended version must be available, active and not revoked")
        if version == locked["version"] and artifact["digest"] != locked["digest"]:
            raise ValueError(f"{entry['slug']}: configuration digest differs from artifact lock")
        if record.get("available"):
            validate_configuration(record["configuration"])
    if recommended != ([entry["artifact"]["version"]] if any(r.get("available") for r in records) else []):
        raise ValueError(f"{entry['slug']}: exactly the primary pin must be recommended")


def validate_configuration(configuration: dict) -> None:
    schema = configuration["schema"]
    Draft202012Validator.check_schema(schema)
    reject_remote_refs(schema)
    validate_defaults(schema)
    ids = [preset["id"] for preset in configuration["presets"]]
    if len(ids) != len(set(ids)) or configuration["defaultPreset"] not in ids:
        raise ValueError("configuration presets must be unique and defaultPreset must exist")
    validator = Draft202012Validator(schema)
    for preset in configuration["presets"]:
        validator.validate(preset["values"])


def reject_remote_refs(value: Any) -> None:
    if isinstance(value, dict):
        if "x-astronomer-resource" in value and value["x-astronomer-resource"] not in {"storageclasses", "ingressclasses", "secrets"}:
            raise ValueError("unsupported resource selector")
        if "$ref" in value and not str(value["$ref"]).startswith("#/"):
            raise ValueError("configuration schemas may only reference their local document")
        for child in value.values():
            reject_remote_refs(child)
    elif isinstance(value, list):
        for child in value:
            reject_remote_refs(child)


def validate_defaults(schema: dict) -> None:
    if "default" in schema:
        Draft202012Validator(schema).validate(schema["default"])
    for child in schema.get("properties", {}).values():
        validate_defaults(child)
    if isinstance(schema.get("items"), dict):
        validate_defaults(schema["items"])
