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
./scripts/validate.sh
```

