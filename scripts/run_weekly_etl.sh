#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/billboard_stats/.env"

cd "${ROOT_DIR}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

required_vars=(PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGSSLMODE)
for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required ETL environment variable: ${var_name}" >&2
    exit 1
  fi
done

# Registry-driven INCREMENTAL path: billboard_stats.etl.updater now loops the
# chart registry and dual-writes via load_chart per chart (Plan 10-03). This is
# incremental-only — it never triggers the multi-decade backfill. See
# docs/ETL-REGISTRY.md for the operator validation gate before prod relies on it.
python -m billboard_stats.etl.updater "$@"
