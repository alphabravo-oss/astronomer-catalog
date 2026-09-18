#!/bin/sh
set -eu
export PYTHONDONTWRITEBYTECODE=1

python3 scripts/validate_schema.py
python3 scripts/resolve_artifacts.py --check
python3 scripts/build_catalog.py --check

jq -e '
  .apiVersion == "catalog.astronomer.dev/v1alpha1" and
  .kind == "ApplicationCatalog" and
  (.repositories | length > 0) and
  (.applications | length > 0) and
  ([.applications[].slug] | length == (unique | length)) and
  ([.repositories[].name] as $repositories |
    all(.applications[]; .artifact.repository as $repository | $repositories | index($repository) != null))
' catalog.json >/dev/null

echo "catalog.json is structurally valid"

python3 -m unittest discover -s tests -p 'test_*.py'
