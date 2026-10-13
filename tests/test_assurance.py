from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from assurance import CHECKS, validate_assurance  # noqa: E402
from upstream_report import compare_versions, report  # noqa: E402


class AssuranceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.now = dt.datetime(2026, 10, 12, tzinfo=dt.UTC)
        self.profile = {
            "profile": "monitoring-small", "owner": "platform",
            "chartVersion": "1.0.0", "chartDigest": "sha256:" + "a" * 64,
            "valuesDigest": "sha256:" + "b" * 64,
            "images": ["example/monitor@sha256:" + "c" * 64],
            "environments": ["kind Kubernetes 1.35 amd64"],
            "qualifiedAt": "2026-10-10T00:00:00Z",
            "supportUntil": "2026-11-10T00:00:00Z",
            "checks": dict.fromkeys(CHECKS, "pass"),
        }
        receipt = {**self.profile, "schemaVersion": 1, "application": "monitor",
                   "executionReports": [{"url": "https://example.test/run.json",
                                         "digest": "sha256:" + "d" * 64}]}
        data = json.dumps(receipt).encode()
        digest = hashlib.sha256(data).hexdigest()
        folder = self.root / "assurance-evidence"
        folder.mkdir()
        (folder / f"{digest}.json").write_bytes(data)
        self.profile.update(evidenceDigest="sha256:" + digest,
                            evidenceURL="https://example.test/receipt.json")
        self.catalog = {"applications": [{"slug": "monitor", "supportTier": "astronomer",
                         "artifact": {"version": "1.0.0", "assurance": self.profile},
                         "lifecycle": {"rollback": True}}]}
        self.lock = {"entries": {"monitor": {"digest": self.profile["chartDigest"]}}}

    def validate(self) -> list[str]:
        return validate_assurance(self.catalog, self.lock, self.root, self.now)

    def test_matching_reviewed_receipt(self) -> None:
        self.assertEqual(self.validate(), [])

    def test_missing_receipt_and_mutations_fail_closed(self) -> None:
        for field, value in (("chartVersion", "2.0.0"),
                             ("chartDigest", "sha256:" + "f" * 64),
                             ("valuesDigest", "sha256:" + "f" * 64),
                             ("qualifiedAt", "2026-12-01T00:00:00Z"),
                             ("supportUntil", "2026-10-01T00:00:00Z"),
                             ("evidenceDigest", "sha256:" + "f" * 64)):
            with self.subTest(field=field):
                previous = self.profile[field]
                self.profile[field] = value
                self.assertTrue(self.validate())
                self.profile[field] = previous

    def test_missing_and_wrong_tier(self) -> None:
        entry = self.catalog["applications"][0]
        entry["artifact"].pop("assurance")
        self.assertTrue(self.validate())
        entry["supportTier"] = "experimental"
        self.assertEqual(self.validate(), [])
        entry["artifact"]["assurance"] = self.profile
        self.assertTrue(self.validate())

    def test_no_skipped_checks_or_false_rollback_claim(self) -> None:
        for key in CHECKS:
            with self.subTest(check=key):
                original = copy.deepcopy(self.profile["checks"])
                self.profile["checks"][key] = "not-run"
                self.assertTrue(self.validate())
                self.profile["checks"] = original
        self.catalog["applications"][0]["lifecycle"]["rollback"] = False
        self.assertTrue(self.validate())

    def test_report_is_version_discovery_not_promotion(self) -> None:
        self.assertEqual(compare_versions("1.9.0", ["1.10.0", "2.0.0-rc.1"])["latest"], "1.10.0")
        self.assertEqual(compare_versions("v1.10.0", ["v1.10.0"])["status"], "no-newer-stable")
        self.assertEqual(compare_versions("1.0.0", ["invalid"])["status"], "unknown")
        self.assertFalse(compare_versions("1.0.0", ["1.1.0"])["selectedPresent"])


class UpstreamReportTest(unittest.TestCase):
    def test_invalid_upstream_remains_explicit_without_changing_pins(self) -> None:
        catalog = {"repositories": [{"name": "external", "type": "helm", "url": "https://example.test"}],
                   "applications": [{"slug": "monitor", "artifact": {"chart": "monitor", "repository": "external", "version": "1.0.0"}}]}
        before = copy.deepcopy(catalog)
        with patch("upstream_report.fetch", return_value=(b"entries: null", {})):
            result = report(catalog)
        self.assertEqual(result["applications"][0]["status"], "unknown")
        self.assertEqual(catalog, before)
