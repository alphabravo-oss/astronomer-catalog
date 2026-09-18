# Astronomer Catalog

Signed application discovery and qualification metadata for Astronomer.

This repository references upstream Helm and OCI artifacts by immutable
version. It does not vendor Rancher, Fleet, or third-party application source.
Catalog metadata adds Astronomer presentation, compatibility, prerequisite,
resource, storage, and lifecycle information around those upstream artifacts.

The development index is [`catalog.json`](catalog.json). All entries are
experimental until automated install, upgrade, rollback, uninstall, security,
and air-gap qualification is enabled.

## Validate

```sh
python3 -m pip install --requirement requirements-dev.txt
python3 scripts/resolve_artifacts.py
python3 scripts/build_catalog.py
./scripts/validate.sh
```

The builder discovers optional `entries/**/application.{json,yaml,yml}` source
documents, orders repositories and applications deterministically, validates
cross-references, and emits a canonical index, per-entry payloads, dependency
and image inventories, immutable digests, and a static HTTPS mirror under
`generated/`. When no split entry sources exist, the applications embedded in
`catalog.json` remain the source of truth.

`resolve_artifacts.py` downloads bounded, public-HTTPS Helm indexes and chart
archives, rejects credential-bearing/private-network redirects, and records
the exact archive digest and size in `artifact-lock.json`. Routine validation
uses `--check` and performs no network access.
