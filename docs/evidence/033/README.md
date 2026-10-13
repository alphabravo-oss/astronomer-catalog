# Catalog assurance implementation validation — 2026-10-12

These artifacts validate tooling and catalog metadata. They do not qualify any
application workload or establish an Assured support commitment.

- `installed-tools.json`: the exact installed Python 3.15.0 environment checked
  against all 62 locked tool distributions by `scripts/verify_tools.py`.
- `tooling-audit.json`: strict hash-pinned pip-audit output, no known vulnerabilities.
- `tooling-sbom.cdx.json`: validated CycloneDX 1.6 build-tool environment SBOM;
  this is not the workload/image SBOM required for an Assured application.
- `upstream-report.json`: observed upstream chart-version candidates; 15 updates,
  5 without a newer stable version, 1 first-party manual review, no unknowns.
  No selected pin, deployment or support tier was changed by discovery.

Executed checks:

```sh
PATH="$PWD/.venv/bin:$PATH" ./scripts/validate.sh
.venv/bin/ruff check scripts tests
.venv/bin/mypy --config-file pyproject.toml
.venv/bin/python scripts/verify_tools.py --output qualification/installed-tools.json
.venv/bin/python scripts/upstream_report.py --output qualification/upstream-report.json
```

Result: 45 tests pass, schema and locked artifacts valid, 35 generated outputs
current, Ruff clean and Mypy clean (10 scripts). The requirements export matched
the retained hash-pinned export. CycloneDX validated its output while warning
that the root project's direct dependency graph is empty; independent installed
package verification covers all 62 tools.

The Astronomer repository's existing `catalogproducerinterop` test accepted the
actual regenerated catalog and rejected tampered identities/signatures and
unsupported reader/schema versions. Its retained result and the complete
implementation plan live in the Astronomer repository under
`docs/assurance/platform-offerings/2026-10-12/` and
`advisor-plans/033-platform-tools-applications-assurance.md` respectively.

Initial attempts under system Python 3.14 failed five existing transport tests
because that interpreter lacks the required Python 3.15 HTTP API. Final checks
used the exact reviewed 3.15.0/uv 0.13.0 toolchain; no tests were skipped to hide
that incompatibility. No dependency pins were changed.
