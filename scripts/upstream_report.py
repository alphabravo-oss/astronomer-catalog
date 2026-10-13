"""Read upstream indexes and report candidate versions without changing pins."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from http.client import HTTPException
from pathlib import Path
from typing import Any

import yaml
from resolve_artifacts import MAX_INDEX_BYTES, fetch
from validate_schema import ROOT, load_json


def stable_version(value: str) -> tuple[int, int, int] | None:
    # Helm chart SemVer: exclude prereleases, allow a v prefix and build metadata.
    match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\+[\w.-]+)?", value)
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def compare_versions(selected: str, versions: list[str]) -> dict[str, Any]:
    selected_key = stable_version(selected)
    candidates = [(key, version) for version in versions if (key := stable_version(version))]
    if selected_key is None or not candidates:
        return {"status": "unknown", "reason": "no comparable stable SemVer versions"}
    latest_key, latest = max(candidates)
    present = selected in versions
    return {"status": "update-available" if latest_key > selected_key else "no-newer-stable",
            "latest": latest, "selectedPresent": present,
            "reason": "selected version absent from current upstream index" if not present else ""}


def report(catalog: dict[str, Any]) -> dict[str, Any]:
    repositories = {item["name"]: item for item in catalog["repositories"]}
    indexes: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for app in catalog["applications"]:
        artifact = app["artifact"]
        repo = repositories[artifact["repository"]]
        row = {"application": app["slug"], "selected": artifact["version"],
               "repository": artifact["repository"], "chart": artifact["chart"]}
        try:
            if repo["name"] == "astronomer-first-party" or repo["type"] != "helm":
                row.update(status="manual-review", reason="first-party or non-HTTP Helm source")
            else:
                if repo["name"] not in indexes:
                    data, _ = fetch(repo["url"].rstrip("/") + "/index.yaml", MAX_INDEX_BYTES)
                    indexes[repo["name"]] = yaml.safe_load(data)
                index = indexes[repo["name"]]
                if not isinstance(index, dict) or not isinstance(index.get("entries"), dict):
                    raise ValueError("index entries must be a mapping")
                entries = index["entries"].get(artifact["chart"], [])
                row.update(compare_versions(artifact["version"], [str(item["version"]) for item in entries]))
        except (ValueError, KeyError, TypeError, OSError, HTTPException, yaml.YAMLError) as error:
            row.update(status="unknown", reason=f"upstream index unavailable or invalid: {type(error).__name__}")
        rows.append(row)
    return {"schemaVersion": 1, "observedAt": dt.datetime.now(dt.UTC).isoformat(),
            "scope": "chart-version discovery only; security, EOL and application dependencies require review",
            "applications": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = report(load_json(ROOT / "catalog.json"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    return int(any(row["status"] == "unknown" for row in result["applications"]))


if __name__ == "__main__":
    raise SystemExit(main())
