"""Admin commands: /status and /update (admin-only)."""

import logging
import asyncio
import os

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from billboard_stats.services import data_status_service
from billboard_stats.bot.formatters import fmt_data_status
from billboard_stats.bot.keyboards import admin_update_confirm_keyboard

logger = logging.getLogger(__name__)

ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID")


async def run_sync(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _is_admin(update: Update) -> bool:
    """Accept numeric user ID or @username (with or without the @)."""
    if not ADMIN_ID:
        return False
    user = update.effective_user
    admin_val = ADMIN_ID.lstrip("@")
    try:
        return user.id == int(admin_val)
    except ValueError:
        return (user.username or "").lower() == admin_val.lower()


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show database status (public)."""
    try:
        summary = await run_sync(data_status_service.get_data_summary)
        text = fmt_data_status(summary)
        await update.message.reply_text(text, parse_mode="HTML")
    except Exception:
        logger.exception("Error in /status")
        await update.message.reply_text("Error retrieving database status.")


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show update confirmation prompt (admin only)."""
    if not _is_admin(update):
        await update.message.reply_text("This command is restricted to administrators.")
        return

    await update.message.reply_text(
        "⚠️ <b>Trigger chart update?</b>\n\n"
        "This will fetch new chart data and rebuild stats. "
        "It may take several minutes.",
        parse_mode="HTML",
        reply_markup=admin_update_confirm_keyboard(),
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle adm:* callbacks."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "adm:update:cancel":
        try:
            await query.edit_message_text("Update cancelled.")
        except BadRequest:
            pass
        return

    if data == "adm:update:confirm":
        if not _is_admin(update):
            await query.answer("Unauthorized.", show_alert=True)
            return

        try:
            await query.edit_message_text("🔄 Running chart update, please wait…")
        except BadRequest:
            pass

        try:
            from billboard_stats.etl.updater import run_update

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, run_update)

            repair = result.get("repair", {})
            update_res = result.get("update", {})
            msg = (
                "✅ <b>Update complete</b>\n\n"
                f"Repair — Hot 100: {repair.get('hot-100', 0)}, "
                f"B200: {repair.get('billboard-200', 0)}\n"
                f"Update — Hot 100: {update_res.get('hot100_loaded', 0)}, "
                f"B200: {update_res.get('b200_loaded', 0)} new charts loaded"
            )
        except Exception:
            logger.exception("Manual update failed")
            msg = "❌ <b>Update failed</b> — check server logs."

        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except BadRequest:
            pass


def get_handlers():
    return [
        CommandHandler("status", status_command),
        CommandHandler("update", update_command),
        CallbackQueryHandler(admin_callback, pattern=r"^adm:"),
    ]
