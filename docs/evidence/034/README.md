# Configuration validation — 2026-10-12

The two receipts contain 22 successful preset renders each, across 20 applications,
using Kubernetes 1.31 and 1.35 capabilities. Each receipt binds the exact chart
archive and resulting manifest digest. Effective defaults plus preset overrides
also pass the reviewed configuration schema. The catalog's 49 Python unit tests,
Ruff and Mypy pass using the pinned tool environment. Generated outputs are
current. Runtime dependency audit evidence remains in `../033/`; no dependency
was added by this change.

Longhorn 1.12.1 is explicitly unavailable and has no form generated from
unverified bytes:

- Retained lock: `sha256:d70764e2d6cce673482da4d91da5b44a9791cda842c1914f77e7806ad1cd94bb`
- Downloaded archive: `sha256:c8cf4b35a9d872cd5f7e44fd26d8e6ac7c2abaee42f4e2f2a0b0ebbc6e3a6116`
- Source: `https://github.com/longhorn/charts/releases/download/longhorn-1.12.1/longhorn-1.12.1.tgz`

The original lock remains intact. Resolve the upstream artifact discrepancy and
retain new qualification evidence before re-enabling this version. No entry was
promoted to Assured; these receipts establish configuration and template checks,
not live install/upgrade/rollback or architecture qualification.
