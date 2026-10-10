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
# Install the selected Python 3.15.0 and uv 0.13.0 tools first.
python3 scripts/sync_tools.py --python "$(command -v python3)"
.venv/bin/python scripts/verify_tools.py --output qualification/installed-tools.json
.venv/bin/python scripts/resolve_artifacts.py
.venv/bin/python scripts/build_catalog.py
PATH="$PWD/.venv/bin:$PATH" ./scripts/validate.sh
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

The canonical dependency source is `pyproject.toml` plus the committed `uv.lock`.
The retained `requirements-all.txt` is a hashed export for audit and independent
graph comparison. Use the locked synchronizer instead of an unpinned pip install.
The synchronizer first installs the locked setuptools/Cython backend wheels,
then the full tool groups, permitting only PyYAML 6.0.3 to build from source with
its pure Python loader. It rejects a different interpreter, resolver, index or
source-build package and verifies that synchronization preserves the lock.

See [tooling and qualification](docs/TOOLING.md) for the selected platform scope,
lint/type/audit commands and the separate GitHub publication boundary.
