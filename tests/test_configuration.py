"""Regression checks for catalog-owned versions and configuration."""
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from build_catalog import build_document
from configuration import validate_configuration, validate_versions
from validate_schema import ROOT, load_json


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        catalog, _ = build_document()
        self.entry = next(e for e in catalog["applications"] if e["slug"] == "loki")
        self.records = self.entry["artifact"]["versions"]
        self.locked = load_json(ROOT / "artifact-lock.json")["entries"]["loki"]

    def test_every_offering_declares_version_availability(self):
        catalog, _ = build_document()
        self.assertEqual(len(catalog["applications"]), 21)
        for entry in catalog["applications"]:
            self.assertTrue(entry["artifact"]["versions"])
            for version in entry["artifact"]["versions"]:
                if version["available"]:
                    self.assertTrue(version["configuration"]["schema"]["properties"])
                else:
                    self.assertEqual(entry["slug"], "longhorn")
                    self.assertFalse(version["recommended"])

    def test_version_digest_and_recommendation_cannot_drift(self):
        for mutate in (
            lambda r: r[0]["artifact"].update(digest="sha256:" + "0" * 64),
            lambda r: r[0].update(recommended=False),
            lambda r: r.append(copy.deepcopy(r[0])),
            lambda r: r[0]["artifact"].update(repository="lookalike"),
            lambda r: r[0].update(supportTier="astronomer"),
        ):
            records = copy.deepcopy(self.records)
            mutate(records)
            with self.assertRaises(ValueError):
                validate_versions(self.entry, records, self.locked)

    def test_presets_must_be_valid_and_local(self):
        config = copy.deepcopy(self.records[0]["configuration"])
        config["defaultPreset"] = "missing"
        with self.assertRaises(ValueError):
            validate_configuration(config)
        config["defaultPreset"] = "evaluation"
        config["schema"]["properties"]["bad"] = {"$ref": "https://example.com/schema"}
        with self.assertRaises(ValueError):
            validate_configuration(config)

    def test_bad_preset_values_fail_validation(self):
        config = copy.deepcopy(self.records[0]["configuration"])
        config["presets"][0]["values"]["singleBinary"]["replicas"] = -1
        from jsonschema import ValidationError
        with self.assertRaises(ValidationError):
            validate_configuration(config)
