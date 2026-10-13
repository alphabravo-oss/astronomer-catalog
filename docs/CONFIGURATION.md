# Version-specific application configuration

Author `configurations/<application-slug>/<exact-chart-version>.json`. JSON is the
canonical format; adding YAML authoring must compile to this same contract. The
builder merges these files into `artifact.versions` in the deterministic release
payload. Do not hand-edit generated files.

Each record binds repository name, chart name, version and SHA-256 archive digest.
It declares availability, the recommended version, support tier, compatibility,
optional `upgradeFrom` SemVer constraints, and a configuration schema with named
presets and a default namespace. Keep old supported records when introducing a
new recommended version; the consumer retains these pins outside its upstream
rolling window. Exactly the primary artifact pin is recommended, unless every
record is unavailable. Revoked/deprecated versions cannot be recommended.

The reviewed schema supplies field order, titles, descriptions, types, defaults,
required fields, enums, bounds and patterns. `x-astronomer-show-when` takes a value
path and string equality condition. `x-astronomer-advanced` collapses optional
object sections. `x-astronomer-resource` may select `storageclasses`,
`ingressclasses` or `secrets`; choices come from authorized cluster/namespace
metadata APIs. Never include credentials in published schemas or preset values.
Local schema references are allowed; remote references are rejected.

Before publishing a configuration change:

1. Obtain and inspect the exact chart archive and verify its digest against the
   record and `artifact-lock.json`. Review optional nested paths against chart
   templates and upstream schemas, including embedded Kubernetes objects.
2. Validate configuration schemas, declared defaults, preset IDs and preset value
   types. Current record identity must match the artifact lock. An older record
   needs its retained archive and digest, never a newly resolved moving tag.
3. Run `python3 scripts/build_catalog.py` and `scripts/validate.sh` with the pinned
   tool environment. Commit source and deterministic generated output together.
4. Run `python3 scripts/validate_configurations.py --archive-dir <archives>
   --kubernetes 1.31.0 --output <receipt.json>` and repeat for the supported upper
   Kubernetes version. `--fetch` downloads missing primary archives using the
   existing bounded public-HTTPS fetcher. Filenames are `<chart>-<version>.tgz`.
   The script verifies bytes, validates effective values, then renders every
   available preset with Helm. Any mismatch or failed render fails the command.
5. Test the UI, invalid values, resource permissions, version changes and upgrade
   paths. Perform the retained lifecycle qualification in `docs/ASSURANCE.md`
   before claiming Assured support. Template rendering alone cannot establish
   workload readiness, storage behavior, image architecture or supportability.

Other upstream versions do not inherit these forms, presets or compatibility
promises. Updating upstream does not automatically update a reviewed catalog pin.
