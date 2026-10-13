#!/usr/bin/env python3
"""Verify immutable chart bytes and render every available configuration preset."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import tarfile
import tempfile

import yaml
from build_catalog import build_document
from jsonschema import Draft202012Validator
from resolve_artifacts import MAX_CHART_BYTES, fetch
from validate_schema import ROOT, load_json


def qualify(archive_dir: pathlib.Path, *, download: bool, kubernetes: str) -> list[dict]:
    catalog, _ = build_document()
    lock = load_json(ROOT / "artifact-lock.json")["entries"]
    results: list[dict] = []
    for entry in catalog["applications"]:
        for record in entry["artifact"].get("versions", []):
            if not record["available"]:
                results.append({"chart": entry["slug"], "version": record["version"], "status": "unavailable"})
                continue
            # Additional retained versions need an archive in archive_dir with the
            # digest declared in their version record; never resolve a moving tag.
            name = f"{record['artifact']['name']}-{record['version']}.tgz"
            path = archive_dir / name
            local = ROOT / "charts" / name
            if local.exists():
                path = local
            if not path.exists() and download:
                locked = lock[entry["slug"]]
                if record["version"] != locked["version"]:
                    raise ValueError(f"supply retained archive {name} explicitly")
                content, _ = fetch(locked["url"], MAX_CHART_BYTES)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            content = path.read_bytes()
            digest = "sha256:" + hashlib.sha256(content).hexdigest()
            if digest != record["artifact"]["digest"]:
                raise ValueError(f"{name}: archive digest differs from reviewed configuration")
            with tarfile.open(path) as archive:
                member = archive.extractfile(record["artifact"]["name"] + "/values.yaml")
                if member is None:
                    raise ValueError("chart has no values.yaml")
                defaults = yaml.safe_load(member) or {}
            for preset in record["configuration"]["presets"]:
                Draft202012Validator(record["configuration"]["schema"]).validate(
                    merge_values(defaults, preset["values"])
                )
                with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as values:
                    yaml.safe_dump(preset["values"], values)
                    values.flush()
                    run = subprocess.run(
                        ["helm", "template", "configuration-check", str(path), "--namespace",
                         record["configuration"]["namespace"], "--kube-version", kubernetes,
                         "-f", values.name], capture_output=True, timeout=120, check=False,
                    )
                results.append({
                    "chart": entry["slug"], "version": record["version"], "preset": preset["id"],
                    "chartDigest": digest, "kubernetes": kubernetes,
                    "status": "pass" if run.returncode == 0 else "fail",
                    "renderDigest": "sha256:" + hashlib.sha256(run.stdout).hexdigest(),
                    "diagnostic": run.stderr.decode(errors="replace")[:4000],
                })
    return results


def merge_values(base: dict, overrides: dict) -> dict:
    merged = dict(base)
    for key, value in overrides.items():
        merged[key] = merge_values(merged[key], value) if isinstance(merged.get(key), dict) and isinstance(value, dict) else value
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=pathlib.Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--kubernetes", default="1.34.0")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    results = qualify(args.archive_dir, download=args.fetch, kubernetes=args.kubernetes)
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    return int(any(row["status"] == "fail" for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
