#!/usr/bin/env python3
"""Resolve catalog Helm chart versions to immutable archive digests."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import pathlib
import re
import socket
import sys
import urllib.parse
from typing import Any

import yaml
from artifact_http import fetch_public_https
from validate_schema import ROOT, load_json

LOCK_PATH = ROOT / "artifact-lock.json"
MAX_INDEX_BYTES = 20 * 1024 * 1024
MAX_CHART_BYTES = 256 * 1024 * 1024


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def validate_public_https(url: str, *, allow_transient_signature: bool = False) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("artifact URL must be credential-free HTTPS")
    sensitive_query_keys = {
        "access_token", "authorization", "credential", "jwt", "key",
        "password", "sig", "signature", "token", "x-amz-credential",
        "x-amz-signature",
    }
    query_keys = {key.lower() for key, _ in urllib.parse.parse_qsl(parsed.query)}
    if not allow_transient_signature and query_keys & sensitive_query_keys:
        raise ValueError("artifact URL contains credential-like query parameters")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError(f"artifact URL resolves to a non-public address: {parsed.hostname}")


def fetch(url: str, maximum: int) -> tuple[bytes, str]:
    return fetch_public_https(url, maximum)


def chart_url(index_url: str, index: dict, chart: str, version: str) -> str:
    versions = index.get("entries", {}).get(chart, [])
    match = next((item for item in versions if str(item.get("version")) == version), None)
    if not match:
        raise ValueError(f"chart {chart} version {version} is absent from the Helm index")
    urls = match.get("urls") or []
    if not urls:
        raise ValueError(f"chart {chart} version {version} has no archive URL")
    return urllib.parse.urljoin(index_url, str(urls[0]))


def resolve() -> dict:
    catalog = load_json(ROOT / "catalog.json")
    repositories = {item["name"]: item for item in catalog["repositories"]}
    indexes: dict[str, tuple[dict, str]] = {}
    entries: dict[str, dict[str, Any]] = {}
    for application in sorted(catalog["applications"], key=lambda item: item["slug"]):
        slug = application["slug"]
        artifact = application["artifact"]
        chart = artifact["chart"]
        version = artifact["version"]
        local_archive = ROOT / "charts" / f"{chart}-{version}.tgz"
        if local_archive.is_file():
            content = local_archive.read_bytes()
            entries[slug] = {
                "type": "helm",
                "repository": artifact["repository"],
                "chart": chart,
                "version": version,
                "url": local_archive.relative_to(ROOT).as_posix(),
                "digest": sha256(content),
                "size": len(content),
            }
            continue
        repository = repositories[artifact["repository"]]
        if repository["type"] != "helm":
            raise ValueError(f"{slug}: resolver does not support repository type {repository['type']}")
        repository_url = repository["url"].rstrip("/") + "/"
        if repository_url not in indexes:
            requested_index_url = urllib.parse.urljoin(repository_url, "index.yaml")
            index_content, resolved_index_url = fetch(requested_index_url, MAX_INDEX_BYTES)
            parsed = yaml.safe_load(index_content)
            if not isinstance(parsed, dict):
                raise ValueError("Helm index is not an object")
            indexes[repository_url] = (parsed, resolved_index_url)
        index, resolved_index_url = indexes[repository_url]
        requested_chart_url = chart_url(resolved_index_url, index, chart, version)
        content, _ = fetch(requested_chart_url, MAX_CHART_BYTES)
        entries[slug] = {
            "type": "helm",
            "repository": artifact["repository"],
            "chart": chart,
            "version": version,
            "url": requested_chart_url,
            "digest": sha256(content),
            "size": len(content),
        }
    return {"schemaVersion": 1, "entries": entries}


def validate_lock(lock: dict, *, catalog: dict | None = None) -> list[str]:
    if catalog is None:
        catalog = load_json(ROOT / "catalog.json")
    expected = {
        item["slug"]: (
            item["artifact"]["repository"],
            item["artifact"]["chart"],
            item["artifact"]["version"],
        )
        for item in catalog["applications"]
    }
    errors: list[str] = []
    if not isinstance(lock, dict):
        return ["artifact lock must be an object"]
    if type(lock.get("schemaVersion")) is not int or lock["schemaVersion"] != 1:
        errors.append("artifact lock schemaVersion must be 1")
    entries = lock.get("entries")
    if not isinstance(entries, dict):
        return errors + ["artifact lock entries must be an object"]
    if set(entries) != set(expected):
        errors.append("artifact lock entry set does not match catalog applications")
    sensitive_query_keys = {
        "access_token", "authorization", "credential", "jwt", "key",
        "password", "sig", "signature", "token", "x-amz-credential", "x-amz-signature",
    }
    for slug, identity in expected.items():
        entry = entries.get(slug)
        if not isinstance(entry, dict):
            errors.append(f"{slug}: locked artifact must be an object")
            continue
        actual = (entry.get("repository"), entry.get("chart"), entry.get("version"))
        if entry.get("type") != "helm" or actual != identity:
            errors.append(f"{slug}: locked artifact identity does not match catalog")
        digest_value = entry.get("digest")
        if not isinstance(digest_value, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest_value):
            errors.append(f"{slug}: invalid locked digest")
        size = entry.get("size")
        if type(size) is not int or not 0 < size <= MAX_CHART_BYTES:
            errors.append(f"{slug}: invalid locked size")
        url = entry.get("url")
        if not isinstance(url, str) or not url:
            errors.append(f"{slug}: locked URL must be a nonempty string")
            continue
        if url.startswith("charts/"):
            canonical_local = f"charts/{identity[1]}-{identity[2]}.tgz"
            archive = ROOT / url
            if url != canonical_local or len(pathlib.PurePosixPath(url).parts) != 2 or any(part in (".", "..") for part in pathlib.PurePosixPath(url).parts):
                errors.append(f"{slug}: local archive path is not canonical")
                continue
            if (ROOT / "charts").is_symlink() or archive.is_symlink() or not archive.is_file():
                errors.append(f"{slug}: local archive must be an owned regular file")
                continue
            with archive.open("rb") as stream:
                content = stream.read(MAX_CHART_BYTES + 1)
            if len(content) > MAX_CHART_BYTES or len(content) != size or sha256(content) != digest_value:
                errors.append(f"{slug}: local archive does not match locked digest and size")
        else:
            try:
                parsed = urllib.parse.urlsplit(url)
                # Offline validation does not resolve DNS or fetch artifacts.
                if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                        or parsed.fragment or parsed.port == 0
                        or any(ord(character) < 32 for character in url)
                        or {key.lower() for key, _ in urllib.parse.parse_qsl(parsed.query)} & sensitive_query_keys):
                    errors.append(f"{slug}: locked URL is not credential-free HTTPS")
            except ValueError:
                errors.append(f"{slug}: locked URL is invalid")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate the committed lock without network access")
    args = parser.parse_args()
    if args.check:
        if not LOCK_PATH.is_file():
            print("artifact-lock.json is missing", file=sys.stderr)
            return 1
        errors = validate_lock(load_json(LOCK_PATH))
        if errors:
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print("artifact lock covers every catalog application")
        return 0
    lock = resolve()
    errors = validate_lock(lock)
    if errors:
        raise ValueError("resolved artifact lock is invalid:\n" + "\n".join(errors))
    LOCK_PATH.write_bytes(canonical_bytes(lock))
    print(f"resolved {len(lock['entries'])} immutable Helm artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
