"""
Telegram Bot entry point.

Run with:
    python -m billboard_stats.bot
"""

import datetime
import logging
import os

import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler

from billboard_stats.bot.handlers import chart, search, records, admin
from billboard_stats.bot.scheduler import weekly_update_job

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "<b>Billboard Stats Bot</b> 🎵\n\n"
    "Explore chart history, artists, and records.\n\n"
    "<b>Commands:</b>\n"
    "/chart — Browse weekly charts\n"
    "/search — Search artists, songs &amp; albums\n"
    "/records — Leaderboards &amp; records\n"
    "/status — Database status\n"
    "/update — Trigger data update (admin only)\n"
)


async def start_command(update: Update, context) -> None:
    await update.message.reply_text(WELCOME_TEXT, parse_mode="HTML")


async def error_handler(update: object, context) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Something went wrong. Please try again later."
            )
        except Exception:
            pass


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    app = Application.builder().token(token).build()

    # Core command
    app.add_handler(CommandHandler("start", start_command))

    # Feature handlers
    for handler in chart.get_handlers():
        app.add_handler(handler)
    for handler in search.get_handlers():
        app.add_handler(handler)
    for handler in records.get_handlers():
        app.add_handler(handler)
    for handler in admin.get_handlers():
        app.add_handler(handler)

    # Global error handler
    app.add_error_handler(error_handler)

    # Weekly auto-update scheduler (Saturday 08:00 UTC)
    if app.job_queue is not None:
        app.job_queue.run_daily(
            weekly_update_job,
            time=datetime.time(hour=8, minute=0, tzinfo=pytz.UTC),
            days=(5,),  # 5 = Saturday (Mon=0)
            name="weekly_update",
        )
        logger.info("Scheduled weekly update job for Saturdays 08:00 UTC")
    else:
        logger.warning(
            "JobQueue not available. Install python-telegram-bot[job-queue] for auto-updates."
        )

    logger.info("Starting billboard_stats bot (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
