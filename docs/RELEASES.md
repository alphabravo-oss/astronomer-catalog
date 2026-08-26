# Releases and OCI naming

Catalog releases use `vMAJOR.MINOR.PATCH`. The canonical OCI artifact is
`ghcr.io/alphabravo-oss/astronomer-application-catalog:vMAJOR.MINOR.PATCH` and
is also addressable by its immutable manifest digest. Static HTTPS mirrors keep
the same catalog bytes and chart filenames.

Release automation validates both JSON Schemas, canonicalizes JSON with sorted
keys, publishes one catalog layer, attaches checksums, SBOM/provenance evidence,
and signs the digest with the tagged GitHub Actions identity. Trust-policy
placeholders contain no private keys or tokens.
