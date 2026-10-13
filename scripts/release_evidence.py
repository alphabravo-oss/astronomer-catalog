#!/usr/bin/env python3
"""Write explicit source/catalog/tool evidence; this is not a SLSA attestation."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess

from sync_tools import ROOT, package_name


def file_identity(path: pathlib.Path) -> dict[str, str | int]:
    content = path.read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}


def verify_audit(tools: dict, audit: dict) -> None:
    rows = audit.get("dependencies")
    if not isinstance(rows, list) or not rows:
        raise ValueError("dependency audit evidence is malformed")
    graph = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("vulns"), list) or row["vulns"]:
            raise ValueError("dependency audit has unresolved findings")
        name = package_name(row["name"])
        if name in graph:
            raise ValueError("dependency audit has duplicate records")
        graph[name] = row["version"]
    if graph != tools.get("distributions"):
        raise ValueError("dependency audit does not cover every installed locked version")


def verify_sbom(tools: dict, sbom: dict) -> None:
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.6":
        raise ValueError("tooling SBOM format mismatch")
    graph = {}
    for row in sbom.get("components", []):
        name = package_name(row["name"])
        if name in graph:
            raise ValueError("tooling SBOM has duplicate components")
        graph[name] = row["version"]
    if graph != tools.get("distributions"):
        raise ValueError("tooling SBOM does not cover every installed locked version")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--distribution-digest", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", args.distribution_digest):
        raise ValueError("published catalog must have an immutable OCI digest")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=15
    ).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("catalog source commit is invalid")
    # Ignored environment/output files are expected. Tracked source must be clean.
    subprocess.run(["git", "diff", "--exit-code", "HEAD"], cwd=ROOT, check=True, timeout=15)
    manifest = json.loads((ROOT / "generated/release-manifest.json").read_text())
    catalog = file_identity(ROOT / "generated/catalog.canonical.json")
    if manifest.get("schemaVersion") != 1 or manifest.get("indexDigest") != "sha256:" + str(catalog["sha256"]):
        raise ValueError("generated release manifest does not bind the canonical catalog")
    tools = json.loads((ROOT / "qualification/installed-tools.json").read_text())
    if tools.get("scope") != "catalog-tooling-environment" or tools.get("python") != "3.15.0":
        raise ValueError("selected tooling environment evidence is absent")
    audit = json.loads((ROOT / "qualification/pip-audit.json").read_text())
    verify_audit(tools, audit)
    verify_sbom(tools, json.loads((ROOT / "qualification/tooling-sbom.cdx.json").read_text()))
    paths = ["catalog.json", "artifact-lock.json", "pyproject.toml", "uv.lock",
             "requirements-all.txt", "generated/release-manifest.json",
             "qualification/installed-tools.json", "qualification/pip-audit.json",
             "qualification/tooling-sbom.cdx.json"]
    value = {"schema_version": 1, "scope": "catalog-build-evidence",
             "source_commit": commit, "distribution_digest": args.distribution_digest,
             "canonical_catalog": catalog,
             "inputs_and_evidence": {name: file_identity(ROOT / name) for name in paths},
             "limitations": ["tooling SBOM covers the Python build environment; not Helm workloads",
                             "this evidence document is not a SLSA level assessment"]}
    args.output.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
