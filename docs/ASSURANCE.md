# Offering assurance and upstream maintenance

Platform Tools are guided cluster capabilities. Applications are catalog
applications and the shared installed-release inventory. These entry points do
not determine support. The v1 wire enums remain compatible:

| Wire value | Operator label | Commitment |
| --- | --- | --- |
| `astronomer` with valid evidence | Assured profile | Exact tested chart/configuration, images, environments, owner and support window |
| `upstream` | Community | Astronomer deployment integration; no Astronomer application assurance |
| `experimental`, or an unproven legacy claim | Experimental | Evaluation without a production assurance commitment |

No current catalog entries are Assured. Product ownership, a preset, a pinned
chart, a signature or a successful build cannot promote an application. Community
does not promise that its upstream supplies commercial support.

## Qualification and promotion

1. Select one monitoring profile and one logging profile initially. Use existing
   upstream artifacts; keep local chart changes small and contribute fixes
   upstream where possible. Maintain the current pin until the replacement is
   qualified; security fixes, EOL and compatibility can require updates without
   new features. Never automatically update installed workloads.
2. Build an owned test estate using astronomer-testbed or the existing local
   astronomer-full-test-iac. Record the exact Astronomer candidate, Kubernetes
   version/distribution, architecture, storage and networking. Do not substitute
   a different provider or architecture for missing evidence.
3. Run Astronomer's `scripts/qualify-offerings` inventory, preflight, run and
   verify against the selected estate. Also collect workload image SBOM and
   vulnerability results. Catalog build-tool SBOMs do not cover workload images.
4. Review installation, functional canaries, upgrade with existing data,
   rollback/recovery, uninstall/storage retention, isolation, security, and
   air-gap behavior. Each required result must pass; a declared unsupported
   rollback must be recorded as `not-supported`, with a documented recovery path.
5. Retain original reports in access-controlled immutable artifact storage and
   publish sanitized reports at HTTPS URLs with SHA256 digests. Do not retain
   secrets, credentials or customer data in this repository.
6. Create a reviewed receipt in `assurance-evidence/<sha256-hex>.json`. Its content
   contains `schemaVersion: 1`, `application` (slug), and all the profile fields
   listed below except `supportUntil`, `evidenceURL`, `evidenceDigest`. Include a
   nonempty `executionReports` array of `{url, digest}` for the original results.
   A receipt records a review of actual execution; this validator cannot prove
   remote reports are truthful merely because the hash and metadata match.
7. Set `supportTier: astronomer` and `artifact.assurance` using the
   [profile schema](../schemas/assurance-profile-v1.schema.json). Fields: profile,
   owner, chartVersion, chartDigest, valuesDigest, images (immutable image refs),
   environments, qualifiedAt, supportUntil, evidenceURL, evidenceDigest, checks.
   The values digest identifies the tested effective configuration. Support is
   limited to that profile; arbitrary values or a different chart version do not
   inherit assurance. Multi-chart tool composition needs its own qualification;
   individual chart results do not certify the composed tool.
8. Run validation and regeneration, review the evidence and support window, then
   publish through the signed catalog release workflow. Keep previous artifacts
   available for supported upgrades/recovery. Stage customer adoption separately.

The builder rejects absent or mismatched receipts, wrong locked chart identities,
expired/future qualification, unsupported rollback claims and incomplete checks.
The UI only describes an Assured profile from a trusted, nonrevoked catalog with
matching version and an unexpired window. It never asserts that edited values or
an arbitrary target cluster are themselves qualified.

## Ongoing updates

The daily `Upstream version review` workflow writes a read-only report. It never
edits pins, opens a PR or deploys. Unknown results fail the job and remain in its
retained report. The report is chart-version discovery, not a CVE/EOL service.

Assign a release owner to review the report at least weekly and triage security
advisories and EOL notices promptly. Review chart dependencies, application
versions and image advisories separately. Record held updates with an owner,
reason and next review date. A support response SLA requires a separately
approved support agreement; none is invented by this policy.

For each candidate: update source metadata -> resolve immutable artifacts ->
qualify exact profiles -> review evidence -> sign/publish -> stage installations.
If a profile expires, requalify or downgrade it; revoke compromised artifacts
through the existing revocation policy. Do not silently rewrite old evidence.
