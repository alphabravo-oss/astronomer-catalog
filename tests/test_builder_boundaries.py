from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("build_catalog", ROOT / "scripts/build_catalog.py")
assert SPEC and SPEC.loader
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class CatalogBuilderBoundaryTest(unittest.TestCase):
    def rejected(self, catalog: dict, artifact_lock: dict) -> None:
        def document(path: pathlib.Path) -> dict:
            return copy.deepcopy(artifact_lock if path.name == "artifact-lock.json" else catalog)
        with mock.patch.object(BUILD, "load_json", side_effect=document), mock.patch.object(BUILD, "discover_entries", return_value=[]):
            try:
                BUILD.build_document()
            except ValueError:
                return
            except (TypeError, AttributeError, KeyError) as error:
                self.fail("malformed owned input reached builder traversal: " + type(error).__name__)
            self.fail("malformed artifact lock reached generated release payload")

    def test_wrong_catalog_shape_is_rejected_before_traversal(self) -> None:
        catalog = json.loads((ROOT / "catalog.json").read_text())
        artifact_lock = json.loads((ROOT / "artifact-lock.json").read_text())
        catalog["applications"] = None
        self.rejected(catalog, artifact_lock)

    def test_invalid_locked_digest_is_rejected_before_release_generation(self) -> None:
        catalog = json.loads((ROOT / "catalog.json").read_text())
        artifact_lock = json.loads((ROOT / "artifact-lock.json").read_text())
        first = catalog["applications"][0]["slug"]
        artifact_lock["entries"][first]["digest"] = "sha256:" + "z" * 64
        self.rejected(catalog, artifact_lock)


if __name__ == "__main__":
    unittest.main()
