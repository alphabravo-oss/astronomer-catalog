# Locked catalog tooling

The selected runtime is Python 3.15.0 with uv 0.13.0. The repository manifest
selects build/test, Ruff, Mypy, pip-audit, CycloneDX and source-build-backend groups.
`uv.lock` is the actual resolved 62-record graph: one virtual project and 61
exact distribution versions with all 384 upstream distribution hashes. The
hashed requirements export has the same graph; its machine-specific command
header is omitted from the committed reference. `verify_export.py` ignores only
the known two-line uv command header and compares every remaining byte.

On Linux, run `scripts/sync_tools.py` with an explicit selected interpreter.
Automatic interpreter downloads and inherited alternative resolver/index/build
configuration are disabled. Backend wheels are installed first under `--no-build`.
The final locked sync requires wheels for every package except PyYAML 6.0.3,
which builds from its hash-pinned source using the installed locked setuptools
and Cython versions, without isolated unpinned build dependencies. The environment
check requires every installed package/version to equal the full lock, the pure
SafeLoader and the JSON Schema URI format capability.

The executed Plan032 local environment is x86_64 Linux using the selected
standalone Python 3.15.0 distribution. Its 61-version installation is already
qualified against the retained lock. The aarch64 Linux interpreter/uv artifacts
have static primary size/hash metadata; no aarch64 installation or runtime test
is claimed. The workflow selects x86_64 `ubuntu-24.04`, Python 3.15.0 and uv 0.13.0.
GitHub setup-python supplies a different interpreter distribution from the
local standalone build, so workflow execution and that platform still require
separate actual qualification. Other platforms are not supported by the artifact
resolver's owned Linux DNS process model.

After synchronization:

```sh
PATH="$PWD/.venv/bin:$PATH" ./scripts/validate.sh
.venv/bin/ruff check scripts tests
.venv/bin/mypy --config-file pyproject.toml
uv --no-config export --locked --offline --all-groups --no-default-groups --no-emit-project --format requirements-txt --output-file qualification/requirements-all.txt --python "$(command -v python3)"
.venv/bin/python scripts/verify_export.py --reference requirements-all.txt --candidate qualification/requirements-all.txt
.venv/bin/python -m pip_audit --strict --disable-pip --require-hashes --requirement qualification/requirements-all.txt --format json --output qualification/pip-audit.json --timeout 15 --progress-spinner off
.venv/bin/python -m cyclonedx_py environment .venv/bin/python --pyproject pyproject.toml --output-reproducible --validate --spec-version 1.6 --output-format JSON --output-file qualification/tooling-sbom.cdx.json
```

Routine catalog validation remains offline. Dependency auditing queries the
advisory service and fails if a dependency cannot be collected or has an
unaccepted finding. The SBOM and audit must cover exactly the complete installed
version graph before release evidence is emitted; no generic dependency exception
or vulnerability-ignore flag is added. The strict Mypy/Ruff gates are source
requirements; their actual results on this proposed composition are still pending.
In particular, the selected jsonschema distribution lacks a py.typed marker,
so the Mypy import boundary needs actual measurement and a precise dependency
or typed-adapter decision if it fails; no broad missing-import ignore is authorized.

Primary references: [uv locked synchronization](https://docs.astral.sh/uv/concepts/projects/sync/),
[uv dependency groups](https://docs.astral.sh/uv/concepts/projects/dependencies/#dependency-groups),
[pip-audit CLI/security model](https://github.com/pypa/pip-audit/blob/v2.10.1/README.md),
[CycloneDX environment SBOM](https://cyclonedx-bom-tool.readthedocs.io/en/latest/usage.html),
[Python package-name normalization](https://packaging.python.org/en/latest/specifications/name-normalization/),
[setup-uv pinned inputs](https://github.com/astral-sh/setup-uv/blob/bec219d24cd3e171d82865faccec33120bb574f4/action.yml),
[setup-oras pinned inputs](https://github.com/oras-project/setup-oras/blob/1d808f7d7f6995cc68b7bf507bfe5c5446e1dc9d/action.yml),
and [cosign installer inputs](https://github.com/sigstore/cosign-installer/blob/6f9f17788090df1f26f669e9d70d6ae9567deba6/action.yml).
