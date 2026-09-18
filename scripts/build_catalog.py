#!/usr/bin/env python3
"""Build deterministic catalog release and static-mirror payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys
from typing import Any

from validate_schema import ROOT, load_json, validate_catalog, validate_revocations


GENERATED = ROOT / "generated"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def load_document(path: pathlib.Path) -> dict:
    if path.suffix == ".json":
        return load_json(path)
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - actionable local diagnostic
        raise RuntimeError("PyYAML is required to build YAML catalog entries") from error
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain an object")
    return value


def discover_entries() -> list[dict]:
    paths: list[pathlib.Path] = []
    for pattern in ("entries/**/application.json", "entries/**/application.yaml", "entries/**/application.yml"):
        paths.extend(ROOT.glob(pattern))
    return [load_document(path) for path in sorted(set(paths))]


def dependency_slug(value: Any) -> str:
    return value if isinstance(value, str) else str(value.get("slug", ""))


def build_document() -> tuple[dict, dict]:
    catalog = load_json(ROOT / "catalog.json")
    artifact_lock = load_json(ROOT / "artifact-lock.json")
    locked_artifacts = artifact_lock.get("entries", {})
    discovered = discover_entries()
    if discovered:
        catalog["applications"] = discovered
    catalog["repositories"] = sorted(catalog["repositories"], key=lambda row: row["name"])
    catalog["applications"] = sorted(catalog["applications"], key=lambda row: row["slug"])

    repository_names = [row["name"] for row in catalog["repositories"]]
    slugs = [row["slug"] for row in catalog["applications"]]
    if len(repository_names) != len(set(repository_names)):
        raise ValueError("repository names must be unique")
    if len(slugs) != len(set(slugs)):
        raise ValueError("application slugs must be unique")
    known_repositories = set(repository_names)
    known_slugs = set(slugs)
    dependencies: dict[str, list[str]] = {}
    images: set[str] = set()
    entry_digests: dict[str, str] = {}
    artifacts: dict[str, dict[str, str]] = {}
    compatibility_summary: dict[str, dict[str, int]] = {
        "kubernetes": {},
        "supportTier": {},
        "category": {},
    }

    for entry in catalog["applications"]:
        slug = entry["slug"]
        repository = entry["artifact"]["repository"]
        if repository not in known_repositories:
            raise ValueError(f"{slug}: unknown repository {repository}")
        dependency_names = sorted(dependency_slug(item) for item in entry.get("dependencies", []))
        unknown = [name for name in dependency_names if name not in known_slugs]
        if unknown:
            raise ValueError(f"{slug}: unknown dependencies: {', '.join(unknown)}")
        dependencies[slug] = dependency_names
        version = entry["artifact"]["version"]
        chart = entry["artifact"]["chart"]
        locked = locked_artifacts.get(slug)
        if not isinstance(locked, dict):
            raise ValueError(f"{slug}: artifact-lock.json has no entry")
        if (locked.get("repository"), locked.get("chart"), locked.get("version")) != (
            repository,
            chart,
            version,
        ):
            raise ValueError(f"{slug}: artifact lock identity mismatch")
        artifacts[slug] = {
            "chart": chart,
            "version": version,
            "digest": locked["digest"],
            "size": locked["size"],
        }
        version_metadata = entry.get("versionMetadata", {})
        images.update(version_metadata.get("identities", {}).get("images", []))
        entry_digests[slug] = digest(canonical_bytes(entry))
        for facet, value in (
            ("kubernetes", entry["compatibility"]["kubernetes"]),
            ("supportTier", entry["supportTier"]),
            ("category", entry["category"]),
        ):
            compatibility_summary[facet][value] = compatibility_summary[facet].get(value, 0) + 1

    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("catalog schema validation failed:\n" + "\n".join(errors))
    index_bytes = canonical_bytes(catalog)
    manifest = {
        "schemaVersion": 1,
        "indexDigest": digest(index_bytes),
        "applicationCount": len(catalog["applications"]),
        "repositoryCount": len(catalog["repositories"]),
        "entries": entry_digests,
        "artifacts": artifacts,
    }
    auxiliary = {
        "manifest": manifest,
        "dependencies": dependencies,
        "images": sorted(images),
        "compatibility": compatibility_summary,
    }
    return catalog, auxiliary


def expected_files() -> dict[pathlib.Path, bytes]:
    catalog, auxiliary = build_document()
    revocations = load_json(ROOT / "policies/revocations.json")
    revocation_errors = validate_revocations(revocations)
    if revocation_errors:
        raise ValueError("revocation schema validation failed:\n" + "\n".join(revocation_errors))
    files = {
        GENERATED / "catalog.canonical.json": canonical_bytes(catalog),
        GENERATED / "release-manifest.json": canonical_bytes(auxiliary["manifest"]),
        GENERATED / "dependencies.json": canonical_bytes(auxiliary["dependencies"]),
        GENERATED / "compatibility-summary.json": canonical_bytes(auxiliary["compatibility"]),
        GENERATED / "images.txt": ("\n".join(auxiliary["images"]) + ("\n" if auxiliary["images"] else "")).encode(),
        GENERATED / "revocations.json": canonical_bytes(revocations),
        GENERATED / "static/catalog.json": canonical_bytes(catalog),
        GENERATED / "static/revocations.json": canonical_bytes(revocations),
    }
    for entry in catalog["applications"]:
        files[GENERATED / "entries" / f"{entry['slug']}.json"] = canonical_bytes(entry)
    for schema in sorted((ROOT / "schemas").glob("*.json")):
        files[GENERATED / "static/schemas" / schema.name] = schema.read_bytes()
    return files


def write_outputs(files: dict[pathlib.Path, bytes]) -> None:
    if GENERATED.exists():
        shutil.rmtree(GENERATED)
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def check_outputs(files: dict[pathlib.Path, bytes]) -> bool:
    stale = [path for path, content in files.items() if not path.is_file() or path.read_bytes() != content]
    existing = {path for path in GENERATED.rglob("*") if path.is_file()} if GENERATED.exists() else set()
    stale.extend(sorted(existing - set(files)))
    if stale:
        print("generated catalog output is stale:", file=sys.stderr)
        for path in sorted(set(stale)):
            print(f"- {path.relative_to(ROOT)}", file=sys.stderr)
        print("run: python3 scripts/build_catalog.py", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = expected_files()
    if args.check:
        if not check_outputs(files):
            return 1
        print(f"generated catalog output is current ({len(files)} files)")
        return 0
    write_outputs(files)
    print(f"generated {len(files)} deterministic catalog release files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
