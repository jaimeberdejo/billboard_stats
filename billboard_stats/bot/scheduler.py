"""Weekly auto-update scheduler for the Telegram bot."""

import logging
import os
import asyncio

from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID")


async def weekly_update_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run the weekly chart update and notify the admin."""
    logger.info("Starting weekly chart update job")
    try:
        from billboard_stats.etl.updater import run_update

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_update)

        repair = result.get("repair", {})
        update = result.get("update", {})
        msg = (
            "✅ <b>Weekly update complete</b>\n\n"
            f"Repair — Hot 100: {repair.get('hot-100', 0)}, "
            f"B200: {repair.get('billboard-200', 0)}\n"
            f"Update — Hot 100: {update.get('hot100_loaded', 0)}, "
            f"B200: {update.get('b200_loaded', 0)} new charts loaded"
        )
    except Exception:
        logger.exception("Weekly update job failed")
        msg = "❌ <b>Weekly update failed</b> — check server logs."

    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_ID),
                text=msg,
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Failed to notify admin after weekly update")
