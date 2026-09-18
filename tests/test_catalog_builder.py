from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "build_catalog", ROOT / "scripts/build_catalog.py"
)
assert SPEC and SPEC.loader
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class CatalogBuilderTest(unittest.TestCase):
    def test_build_is_deterministic_and_sorted(self) -> None:
        first, first_aux = BUILD.build_document()
        second, second_aux = BUILD.build_document()
        self.assertEqual(BUILD.canonical_bytes(first), BUILD.canonical_bytes(second))
        self.assertEqual(first_aux, second_aux)
        self.assertEqual(
            [entry["slug"] for entry in first["applications"]],
            sorted(entry["slug"] for entry in first["applications"]),
        )

    def test_release_manifest_binds_every_entry(self) -> None:
        catalog, auxiliary = BUILD.build_document()
        self.assertEqual(
            set(auxiliary["manifest"]["entries"]),
            {entry["slug"] for entry in catalog["applications"]},
        )
        self.assertRegex(auxiliary["manifest"]["indexDigest"], r"^sha256:[a-f0-9]{64}$")

    def test_compatibility_summary_accounts_for_every_entry(self) -> None:
        catalog, auxiliary = BUILD.build_document()
        for counts in auxiliary["compatibility"].values():
            self.assertEqual(sum(counts.values()), len(catalog["applications"]))


if __name__ == "__main__":
    unittest.main()
