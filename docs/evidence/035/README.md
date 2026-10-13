# Longhorn artifact review and catalog configuration validation

Longhorn 1.12.1 is available again after an explicit artifact review. The current
upstream Helm index, GitHub release-asset metadata and downloaded archive all
identify SHA-256 `c8cf4b35a9d872cd5f7e44fd26d8e6ac7c2abaee42f4e2f2a0b0ebbc6e3a6116`
and 79,079 bytes. The package contains 42 files: 41 match the release source
commit byte for byte; `Chart.yaml` has identical parsed YAML with serialization
differences. The release commit is `3d8e92c88396a53591eef3b0859a759a336c57ed`.

The [review receipt](longhorn-review.json) retains the old lock, accepted lock,
upstream identities and per-file comparison hashes. The old lock bytes could not
be located. We therefore cannot establish that upstream changed an artifact;
the earlier quarantine correctly detected a mismatch, and this review corrects
the unverified lock using corroborated upstream evidence.

The visual configuration offers three-replica storage and single-node evaluation
presets, both preserving existing default StorageClasses and retaining released
volumes. Host preparation is still required. Longhorn remains Community-supported
and is not promoted to Assured.

All 49 catalog tests, Ruff and Mypy pass. The render receipts cover 24 presets
across all 21 offerings for Kubernetes 1.31 and 1.35. These checks establish
archive identity, configuration schema validity and template rendering, not live
workload lifecycle qualification. Evidence in `../034/` remains historical.
