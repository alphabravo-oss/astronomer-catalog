# Contributing

Open a pull request that changes catalog metadata and schemas together. Run
`./scripts/validate.sh` before submitting. Every application version must name
an exact upstream chart version; mutable branches and floating `latest` tags
are not accepted.

Do not copy a vendor catalog or chart unless its license explicitly permits
redistribution. Prefer upstream artifacts plus original Astronomer metadata.

Use the locked Python 3.15.0/uv 0.13.0 tool graph documented in `docs/TOOLING.md`.
Run the unchanged catalog unittest suite, Ruff and Mypy before submitting.
Dependency changes require a reviewed `pyproject.toml`/`uv.lock`/hashed-export
update, a complete installed-version check and a fresh dependency audit. Do not
silence audit findings or replace exact package versions with floating ranges.
