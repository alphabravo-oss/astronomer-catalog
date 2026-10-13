from __future__ import annotations

import copy
import hashlib
import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("resolve_artifacts", ROOT / "scripts/resolve_artifacts.py")
assert SPEC and SPEC.loader
RESOLVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESOLVE)


class ArtifactLockBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root / "charts").mkdir()
        self.content = b"owned chart fixture"
        (self.root / "charts/chart-1.0.0.tgz").write_bytes(self.content)
        self.catalog = {"applications": [{"slug": "fixture", "artifact": {
            "repository": "upstream", "chart": "chart", "version": "1.0.0"}}]}
        self.entry = {"type": "helm", "repository": "upstream", "chart": "chart",
                      "version": "1.0.0", "url": "charts/chart-1.0.0.tgz",
                      "digest": "sha256:" + hashlib.sha256(self.content).hexdigest(),
                      "size": len(self.content)}
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(RESOLVE, "ROOT", self.root).start()
        mock.patch.object(RESOLVE, "load_json", return_value=self.catalog).start()

    def errors(self, entry: object, schema_version: object = 1) -> list[str]:
        try:
            return RESOLVE.validate_lock({"schemaVersion": schema_version, "entries": {"fixture": entry}})
        except (AttributeError, TypeError) as error:
            self.fail("artifact lock validator crashed for malformed owned input: " + type(error).__name__)

    def test_representable_committed_identity_is_preserved(self) -> None:
        self.assertEqual(self.errors(self.entry), [])

    def test_non_hex_digest_is_rejected(self) -> None:
        entry = copy.deepcopy(self.entry)
        entry.update(url="https://public.invalid/chart.tgz", digest="sha256:" + "z" * 64)
        self.assertTrue(self.errors(entry), "non-hex artifact digest accepted")

    def test_boolean_size_and_schema_are_rejected(self) -> None:
        for field in ("size", "schemaVersion"):
            with self.subTest(field=field):
                entry = copy.deepcopy(self.entry)
                if field == "size":
                    entry.update(url="https://public.invalid/chart.tgz", size=True)
                errors = self.errors(entry, True if field == "schemaVersion" else 1)
                self.assertTrue(errors, "boolean artifact integer accepted")

    def test_absent_or_non_string_url_is_rejected(self) -> None:
        for value in (None, 7, [], {}):
            with self.subTest(value=value):
                entry = copy.deepcopy(self.entry)
                entry["url"] = value
                self.assertTrue(self.errors(entry), "non-string artifact URL accepted")

    def test_non_object_entry_returns_typed_errors(self) -> None:
        for value in (None, [], "entry"):
            with self.subTest(value=value):
                self.assertTrue(self.errors(value), "non-object artifact entry accepted")

    def test_local_traversal_and_symlink_never_read_outside_charts(self) -> None:
        (self.root / "outside.tgz").write_bytes(self.content)
        (self.root / "charts/alias.tgz").symlink_to(self.root / "outside.tgz")
        canonical = self.root / "charts/chart-1.0.0.tgz"
        canonical.unlink()
        canonical.symlink_to(self.root / "outside.tgz")
        for value in ("charts/../outside.tgz", "charts/alias.tgz", "charts/chart-1.0.0.tgz"):
            with self.subTest(url=value):
                entry = copy.deepcopy(self.entry)
                entry["url"] = value
                self.assertTrue(self.errors(entry), "local archive escaped the owned chart directory")

    def test_local_size_is_validated(self) -> None:
        entry = copy.deepcopy(self.entry)
        entry["size"] += 1
        self.assertTrue(self.errors(entry), "locked local size mismatch accepted")

    def test_durable_remote_credential_query_is_rejected(self) -> None:
        entry = copy.deepcopy(self.entry)
        entry.update(url="https://public.invalid/chart.tgz?token=FIXTURE_SENTINEL", size=len(self.content))
        self.assertTrue(self.errors(entry), "durable credential query accepted")


class ArtifactNetworkBoundaryTest(unittest.TestCase):
    def test_credential_bearing_url_errors_are_content_free(self) -> None:
        for url in ("https://user:FIXTURE_SENTINEL@public.invalid/chart.tgz",
                    "https://public.invalid/chart.tgz?token=FIXTURE_SENTINEL"):
            with self.subTest(url=url), mock.patch.object(RESOLVE.socket, "getaddrinfo", side_effect=AssertionError("must reject before DNS")):
                try:
                    RESOLVE.validate_public_https(url)
                except ValueError as error:
                    self.assertNotIn("FIXTURE_SENTINEL", str(error), "credential URL leaked into diagnostic")
                else:
                    self.fail("credential-bearing URL accepted")


if __name__ == "__main__":
    unittest.main()
