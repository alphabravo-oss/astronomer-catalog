# Releases and OCI naming

Catalog releases use `vMAJOR.MINOR.PATCH`. The canonical OCI artifact is
`ghcr.io/alphabravo-oss/astronomer-application-catalog:vMAJOR.MINOR.PATCH` and
is also addressable by its immutable manifest digest. Static HTTPS mirrors keep
the same catalog bytes and chart filenames.

Release automation keeps the existing v1 single catalog layer and its media type.
It validates all shipped schemas and the unchanged catalog regression suite,
checks lint/types and the complete locked Python tool graph, and refuses a
nonzero dependency audit. ORAS remains 1.2.2 under the existing parent W17
compatibility exception; cosign is explicitly 3.1.3. Action implementations are
pinned to immutable commits. Updating those versions requires renewed qualification.

The release artifacts retain the canonical catalog, checksums, immutable push
result, generated entry/compatibility manifests, full installed-version record,
audit report and CycloneDX 1.6 tooling SBOM. The SBOM covers the Python build
and validation environment. It does not claim to inventory Helm workload images
or upstream chart dependencies. `catalog-build-evidence.json` binds the actual
OCI distribution digest, catalog payload digest, source commit, lock and exact
evidence files. The workflow signs that document using a Sigstore blob bundle
and signs the immutable catalog digest. The evidence document is not a SLSA
level assessment. Signing/publication and the resulting identity must be
qualified separately; a local test pass is not a deployment or release approval.

No credential, signing key or customer data is stored in catalog source. The
workflow uses its scoped GitHub OIDC identity and preserves the existing GHCR
publication repository and tag trigger. Released v1 reader/schema compatibility
remains required after any producer change.
