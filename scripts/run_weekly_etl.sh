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

# Registry-driven INCREMENTAL path: billboard_stats.etl.updater loops the chart
# registry and dual-writes via load_chart per chart (Plan 10-03). This is
# incremental-only — it never triggers the multi-decade backfill. See
# docs/ETL-REGISTRY.md for the operator validation gate before prod relies on it.
#
# CR-02: the weekly cron must run the INCREMENTAL update ONLY, never the historical
# gap scan. With no args the updater would default to repair + update, which (a)
# triggers a whole-history gap scan every week and (b) rebuilds the stats tables
# TWICE per run — doubling the window the live v1.0 site could read a mid-rebuild
# stats table. Gap repair is an operator action (run this script with --repair
# explicitly), not a weekly one. So when invoked with NO args (the cron path),
# default to --update; an operator can still pass --repair / --repair --update.
if [[ "$#" -eq 0 ]]; then
  set -- --update
fi

python -m billboard_stats.etl.updater "$@"
