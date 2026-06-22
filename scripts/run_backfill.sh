#!/usr/bin/env bash
#
# Operator entrypoint for the OFFLINE, MANUAL multi-decade chart backfill.
#
# This is SEPARATE from scripts/run_weekly_etl.sh — the weekly ETL is the
# incremental updater that runs on the cron; THIS runner drives the long,
# operator-run backfill and must never be invoked from a schedule.
#
# It sets the BACKFILL_ALLOW=1 marker the backfill guardrail checks, loads the
# project .env (no DB vars required — the backfill is Postgres-free), then
# forwards all flags to the backfill module:
#
#   scripts/run_backfill.sh --smoke --allow      # proof-of-path (a few weeks)
#   scripts/run_backfill.sh --full --allow       # full multi-decade scrape
#   scripts/run_backfill.sh --full --slug artist-100 --allow
#
# Resumable: re-run after a crash; the on-disk cache skips finished weeks.
# Hard-stops on HTTP 403/429 (rate-limit / IP-block) — do NOT tight-retry.
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

# Mark this as a legitimate manual run for the backfill guardrail. The backfill
# refuses to run unless BACKFILL_ALLOW=1 (and never on GITHUB_EVENT_NAME=schedule).
export BACKFILL_ALLOW=1

python -m billboard_stats.etl.backfill "$@"
