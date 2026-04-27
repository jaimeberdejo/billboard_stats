"""Chart browsing handler with pagination and date navigation."""

import logging
import asyncio
import math
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from billboard_stats.services import chart_service
from billboard_stats.bot.formatters import fmt_chart_page
from billboard_stats.bot.keyboards import chart_type_keyboard, chart_nav_keyboard

logger = logging.getLogger(__name__)

PER_PAGE = 20


async def run_sync(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show chart type picker."""
    await update.message.reply_text(
        "Which chart would you like to browse?",
        reply_markup=chart_type_keyboard(),
    )


async def chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle chart:* callbacks."""
    query = update.callback_query
    await query.answer()

    data = query.data  # e.g. "chart:h100:1:latest" or "chart:h100:nav:prev:2024-01-06"
    parts = data.split(":")

    if parts[1] == "pick":
        try:
            await query.edit_message_text(
                "Which chart would you like to browse?",
                reply_markup=chart_type_keyboard(),
            )
        except BadRequest:
            pass
        return

    ct_code = parts[1]  # h100 or b200
    chart_type = "hot-100" if ct_code == "h100" else "billboard-200"

    # Handle date navigation: chart:h100:nav:prev:2024-01-06
    if parts[2] == "nav":
        date_str = parts[4]
        chart_date = date.fromisoformat(date_str)
        page = 1
    else:
        page = int(parts[2])
        date_str = parts[3] if len(parts) > 3 else "latest"
        chart_date = None if date_str == "latest" else date.fromisoformat(date_str)

    try:
        available_dates = await run_sync(chart_service.get_available_dates, chart_type)
        if not available_dates:
            await query.edit_message_text("No chart data available.")
            return

        if chart_date is None:
            chart_date = available_dates[0]

        entries = await run_sync(chart_service.get_weekly_chart, chart_date, chart_type)
        if not entries:
            await query.edit_message_text("No entries found for this chart date.")
            return

        total_pages = math.ceil(len(entries) / PER_PAGE)
        page = max(1, min(page, total_pages))
        page_entries = entries[(page - 1) * PER_PAGE : page * PER_PAGE]

        text = fmt_chart_page(page_entries, chart_type, chart_date, page, total_pages)
        keyboard = chart_nav_keyboard(chart_type, chart_date, page, total_pages, available_dates)

        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    except Exception:
        logger.exception("Error in chart_callback")
        await query.answer("Error loading chart data.", show_alert=True)


def get_handlers():
    return [
        CommandHandler("chart", chart_command),
        CallbackQueryHandler(chart_callback, pattern=r"^chart:"),
    ]
