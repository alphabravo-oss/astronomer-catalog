from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_schema", ROOT / "scripts/validate_schema.py"
)
assert SPEC and SPEC.loader
VALIDATE_SCHEMA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE_SCHEMA)


class CatalogSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))

    def test_current_catalog_conforms(self) -> None:
        self.assertEqual(VALIDATE_SCHEMA.validate_catalog(self.catalog), [])

    def test_every_entry_is_covered_by_the_entry_schema(self) -> None:
        self.assertGreaterEqual(len(self.catalog["applications"]), 20)
        slugs = [entry["slug"] for entry in self.catalog["applications"]]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_unknown_entry_fields_fail_closed(self) -> None:
        invalid = copy.deepcopy(self.catalog)
        invalid["applications"][0]["unreviewedField"] = True
        errors = VALIDATE_SCHEMA.validate_catalog(invalid)
        self.assertTrue(any("unreviewedField" in error for error in errors), errors)

    def test_invalid_remote_asset_uri_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.catalog)
        invalid["applications"][0]["icon"] = "not a URI"
        errors = VALIDATE_SCHEMA.validate_catalog(invalid)
        self.assertTrue(any("applications.0.icon" in error for error in errors), errors)

    def test_revocation_policy_conforms(self) -> None:
        policy = json.loads(
            (ROOT / "policies/revocations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(VALIDATE_SCHEMA.validate_revocations(policy), [])


if __name__ == "__main__":
    unittest.main()
