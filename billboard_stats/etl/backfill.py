"""Offline, operator-run backfill orchestrator over verified curated slugs.

This module turns the verified-slug list + ``first_date`` sidecar written by
``charts.verify_slugs`` (Plan 01) into actual on-disk raw JSON, by calling the
``fetcher.download_chart`` primitive once per verified chart. It has two modes:

  - ``smoke``: download only the most recent few Saturdays per verified slug.
    This is the phase's PROOF-OF-PATH — small, fast, no multi-decade scrape.
  - ``full``: download each chart's history from its captured ``first_date``
    through the latest publishable week. This is the OPERATOR's long-running
    job; resumability is free from ``download_chart``'s on-disk cache skip.

GUARDRAIL (success criterion #4): ``run_backfill`` refuses to run on the weekly
cron. It aborts when ``GITHUB_EVENT_NAME == "schedule"`` OR when the marker env
var ``BACKFILL_ALLOW`` is not exactly ``"1"``. The CLI ``--allow`` flag (and the
manual ``backfill.yml`` workflow) set ``BACKFILL_ALLOW=1`` for legitimate manual
runs. The multi-decade backfill is therefore impossible to trigger from a cron.

This module is deliberately SEPARATE from ``updater.py`` (the incremental weekly
path) — it is never imported there, and the weekly cron never invokes it.

NOTHING here touches Postgres.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from typing import Optional

from billboard_stats.etl.fetcher import (
    DATA_DIR,
    HardStopError,
    download_chart,
    get_latest_publishable_chart_week,
)

# The verified-slug sidecar written by ``charts.verify_slugs`` (Plan 01).
from billboard_stats.etl.charts import VERIFIED_CHARTS_PATH

# EXACT marker env var name — Task 2's backfill.yml workflow sets this to "1".
ALLOW_ENV_VAR = "BACKFILL_ALLOW"

# Default smoke window: a few recent Saturdays per chart (proof-of-path only).
DEFAULT_SMOKE_WEEKS = 4


class BackfillGuardrailError(Exception):
    """The backfill was invoked in a context where it must not run.

    Raised when ``run_backfill`` is called on the weekly schedule
    (``GITHUB_EVENT_NAME == "schedule"``) or without the explicit manual marker
    (``BACKFILL_ALLOW != "1"`` and no ``allow=True``). This keeps the
    multi-decade scrape off the cron (success criterion #4).
    """


def _check_guardrail(env, allow: bool) -> None:
    """Refuse to run on an automated/cron context / without the manual marker.

    The guardrail is defense-in-depth against the multi-decade scrape ever
    starting automatically (success criterion #4). It has two layers:

      1. **Automated-context refusal (NOT rescuable by the marker).** Any
         GitHub Actions run whose triggering event is not ``workflow_dispatch``
         (``schedule``, ``push``, ``repository_dispatch`` ...) is refused even
         if ``BACKFILL_ALLOW=1`` is present, because only the manual
         ``workflow_dispatch`` path is a legitimate operator action. The
         original ``GITHUB_EVENT_NAME == 'schedule'`` check is the canonical
         subset of this.

      2. **Manual-marker requirement.** For every other context (local shell,
         a non-GitHub cron, a systemd timer) the run is refused unless the
         operator explicitly opted in via ``allow=True`` (the ``--allow`` flag)
         or by exporting ``BACKFILL_ALLOW=1``. ``run_backfill.sh`` no longer
         exports the marker unconditionally, so a bare cron-driven
         ``run_backfill.sh --full`` falls through to this refusal.

    Args:
        env: The environment mapping to inspect (defaults to ``os.environ``).
        allow: When True, the caller (``--allow``) explicitly permits the run,
            equivalent to ``BACKFILL_ALLOW=1``.

    Raises:
        BackfillGuardrailError: on an automated GitHub-Actions context, or when
            neither the ``allow`` flag nor ``BACKFILL_ALLOW=1`` is present.
    """
    event_name = env.get("GITHUB_EVENT_NAME", "")
    is_github_actions = env.get("GITHUB_ACTIONS", "") == "true" or bool(event_name)

    # Layer 1: under GitHub Actions, ONLY the manual workflow_dispatch event may
    # run the backfill. Every other event (schedule/push/etc.) is refused
    # outright and the manual marker does NOT override this.
    if is_github_actions and event_name and event_name != "workflow_dispatch":
        raise BackfillGuardrailError(
            f"Refusing to run the backfill from a non-manual GitHub Actions "
            f"event (GITHUB_EVENT_NAME == {event_name!r}). The multi-decade "
            "backfill is operator-run/manual only (workflow_dispatch) and must "
            "never fire automatically from a schedule or other trigger."
        )

    # Layer 2: outside that path, require the explicit manual marker / flag.
    marker = env.get(ALLOW_ENV_VAR, "")
    if not allow and marker != "1":
        raise BackfillGuardrailError(
            f"Refusing to run the backfill without the manual marker. Set "
            f"{ALLOW_ENV_VAR}=1 (or pass --allow / allow=True) to confirm this "
            "is a legitimate local/manual run. The backfill must never be "
            "triggered automatically from a schedule, cron, or systemd timer."
        )


def load_verified_charts(sidecar_path: Optional[str] = None) -> list:
    """Load the verified (slug, first_date) records from the sidecar.

    Args:
        sidecar_path: Path to ``verified_charts.json``. Defaults to
            ``charts.VERIFIED_CHARTS_PATH``.

    Returns:
        A list of dicts each with ``slug`` and ``first_date`` keys.

    Raises:
        FileNotFoundError: if the sidecar is missing — verification (Plan 01)
            must be run first. The error names the expected path.
    """
    if sidecar_path is None:
        sidecar_path = VERIFIED_CHARTS_PATH

    if not os.path.exists(sidecar_path):
        raise FileNotFoundError(
            f"Verified-charts sidecar not found at {sidecar_path}. Run the slug "
            "verification first: "
            "python -m billboard_stats.etl.charts verify"
        )

    with open(sidecar_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _smoke_window(latest_week: datetime.date, smoke_weeks: int) -> tuple:
    """Compute the (start_date, end_date) for a small recent smoke window."""
    end = latest_week
    start = latest_week - datetime.timedelta(weeks=smoke_weeks)
    return start.isoformat(), end.isoformat()


def run_backfill(
    mode: str = "smoke",
    slug: Optional[str] = None,
    data_dir: Optional[str] = None,
    sidecar_path: Optional[str] = None,
    smoke_weeks: int = DEFAULT_SMOKE_WEEKS,
    delay: float = 1.5,
    allow: bool = False,
    env: Optional[dict] = None,
) -> dict:
    """Download raw chart JSON for verified curated slugs.

    Args:
        mode: ``"smoke"`` (a few recent weeks per chart — the phase's
            proof-of-path) or ``"full"`` (each chart's history from its captured
            ``first_date`` — the operator's long job).
        slug: If given, restrict the run to this single verified slug. It must be
            present in the sidecar, else ``ValueError``.
        data_dir: Root data directory. Defaults to ``fetcher.DATA_DIR``.
        sidecar_path: Path to the verified-charts sidecar. Defaults to
            ``charts.VERIFIED_CHARTS_PATH``.
        smoke_weeks: Number of recent Saturdays for smoke mode (default ~4).
        delay: Polite seconds between requests, passed to ``download_chart``.
        allow: Explicitly permit the run (equivalent to ``BACKFILL_ALLOW=1``).
        env: Environment mapping for the guardrail check (defaults to
            ``os.environ``) — injectable for tests.

    Returns:
        A dict mapping each processed slug to its ``(start_date, end_date)``.

    Raises:
        BackfillGuardrailError: on a scheduled-cron context or missing marker.
        ValueError: for an unknown mode, or a ``--slug`` not in the sidecar.
        FileNotFoundError: if the sidecar is missing.
        HardStopError: propagated from ``download_chart`` on a 403/429.
    """
    if env is None:
        env = os.environ
    if data_dir is None:
        data_dir = DATA_DIR
    if mode not in ("smoke", "full"):
        raise ValueError(f"Unknown backfill mode {mode!r}; expected 'smoke' or 'full'.")

    # GUARDRAIL: never run on the weekly schedule / without the manual marker.
    _check_guardrail(env, allow)

    verified = load_verified_charts(sidecar_path)
    verified_by_slug = {rec["slug"]: rec for rec in verified}

    if slug is not None:
        if slug not in verified_by_slug:
            raise ValueError(
                f"slug '{slug}' is not in the verified-charts sidecar; refusing "
                "to scrape an unverified slug. Verify it first."
            )
        targets = [verified_by_slug[slug]]
    else:
        targets = list(verified)

    latest_week = get_latest_publishable_chart_week()

    ranges = {}
    for rec in targets:
        chart_slug = rec["slug"]
        if mode == "smoke":
            start_date, end_date = _smoke_window(latest_week, smoke_weeks)
        else:  # full
            first_date = rec.get("first_date")
            if not first_date:
                # No captured first_date -> do not silently scrape an empty range.
                print(
                    f"  SKIP {chart_slug}: no captured first_date in sidecar "
                    "(re-run verification).",
                    file=sys.stderr,
                )
                continue
            start_date, end_date = first_date, latest_week.isoformat()

        ranges[chart_slug] = (start_date, end_date)
        # HardStopError (403/429) propagates — do NOT swallow it.
        download_chart(
            chart_slug,
            start_date,
            end_date,
            data_dir=data_dir,
            delay=delay,
        )

    return ranges


def _build_arg_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Offline backfill orchestrator over verified curated slugs. "
            "SMOKE = a few recent weeks per chart (proof-of-path); "
            "FULL = each chart's history from first_date (operator job)."
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--smoke",
        action="store_const",
        dest="mode",
        const="smoke",
        help="Download a few recent weeks per verified chart (proof-of-path).",
    )
    group.add_argument(
        "--full",
        action="store_const",
        dest="mode",
        const="full",
        help="Download each verified chart's full history from its first_date.",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="Restrict the run to a single verified slug.",
    )
    parser.add_argument(
        "--allow",
        action="store_true",
        help=(
            "Confirm this is a legitimate manual run (sets the guardrail marker "
            f"{ALLOW_ENV_VAR}=1)."
        ),
    )
    parser.add_argument(
        "--smoke-weeks",
        type=int,
        default=DEFAULT_SMOKE_WEEKS,
        help="Number of recent Saturdays for smoke mode (default ~4).",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Data directory override.",
    )
    parser.set_defaults(mode="smoke")
    return parser


def main(argv=None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # The --allow flag sets the marker for legitimate manual runs.
    if args.allow:
        os.environ[ALLOW_ENV_VAR] = "1"

    try:
        ranges = run_backfill(
            mode=args.mode,
            slug=args.slug,
            data_dir=args.data_dir,
            smoke_weeks=args.smoke_weeks,
            allow=args.allow,
        )
    except BackfillGuardrailError as exc:
        print(f"GUARDRAIL: {exc}", file=sys.stderr)
        return 2
    except HardStopError as exc:
        print(f"HARD STOP: {exc}", file=sys.stderr)
        return 3
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\nBackfill ({args.mode}) complete over {len(ranges)} chart(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
