#!/bin/sh
set -eu

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

