"""Validate support claims against immutable, reviewed qualification receipts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

CHECKS = ("install", "functional", "upgrade", "rollback", "uninstall", "security",
          "isolation", "airgap")


def validate_assurance(catalog: dict[str, Any], lock: dict[str, Any], root: Path,
                       now: dt.datetime | None = None) -> list[str]:
    """The signed catalog is the publisher's claim, not proof that tests ran here."""
    now = now or dt.datetime.now(dt.UTC)
    errors: list[str] = []
    for entry in catalog["applications"]:
        profile = entry["artifact"].get("assurance")
        slug = entry["slug"]
        if entry["supportTier"] != "astronomer":
            if profile is not None:
                errors.append(f"{slug}: assurance requires an astronomer support tier")
            continue
        if not isinstance(profile, dict):
            errors.append(f"{slug}: astronomer assurance requires a qualification profile")
            continue
        try:
            validate_profile(entry, profile, lock["entries"][slug], root, now)
        except (ValueError, KeyError, TypeError, OSError) as error:
            errors.append(f"{slug}: {error}")
    return errors


def validate_profile(entry: dict[str, Any], profile: dict[str, Any],
                     artifact: dict[str, Any], root: Path, now: dt.datetime) -> None:
    if (profile["chartVersion"] != entry["artifact"]["version"]
            or profile["chartDigest"] != artifact["digest"]):
        raise ValueError("qualification does not match the locked chart version/digest")
    qualified = dt.datetime.fromisoformat(profile["qualifiedAt"].replace("Z", "+00:00"))
    until = dt.datetime.fromisoformat(profile["supportUntil"].replace("Z", "+00:00"))
    if not qualified <= now < until:
        raise ValueError("qualification is future-dated or the support window has expired")
    for check in CHECKS:
        result = profile["checks"][check]
        if check == "rollback" and not entry["lifecycle"]["rollback"]:
            if result != "not-supported":
                raise ValueError("unsupported rollback must be recorded as not-supported")
        elif result != "pass":
            raise ValueError(f"{check} requires a passing qualification")
    # The digest-derived filename cannot escape the repository evidence directory.
    digest = profile["evidenceDigest"]
    hexadecimal = digest.removeprefix("sha256:")
    if len(hexadecimal) != 64 or any(c not in "0123456789abcdef" for c in hexadecimal):
        raise ValueError("invalid qualification evidence digest")
    receipt_path = root / "assurance-evidence" / f"{hexadecimal}.json"
    data = receipt_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != hexadecimal:
        raise ValueError("qualification evidence digest mismatch")
    receipt = json.loads(data)
    if receipt.get("application") != entry["slug"] or receipt.get("schemaVersion") != 1:
        raise ValueError("qualification receipt application/schema mismatch")
    for field in ("chartVersion", "chartDigest", "valuesDigest", "images", "environments",
                  "qualifiedAt", "owner", "checks", "profile"):
        if receipt.get(field) != profile[field]:
            raise ValueError(f"qualification receipt {field} mismatch")
    if not receipt.get("executionReports") or not isinstance(receipt["executionReports"], list):
        raise ValueError("qualification receipt requires retained execution report identities")
    for report in receipt["executionReports"]:
        if not isinstance(report, dict) or not str(report.get("url", "")).startswith("https://"):
            raise ValueError("execution report requires an HTTPS evidence URL")
        report_digest = str(report.get("digest", ""))
        if (not report_digest.startswith("sha256:") or len(report_digest) != 71
                or any(c not in "0123456789abcdef" for c in report_digest[7:])):
            raise ValueError("execution report requires an immutable SHA256 digest")
