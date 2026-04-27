"""Records leaderboards and custom query builder handler."""

import logging
import asyncio
import math

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from billboard_stats.services import records_service
from billboard_stats.bot.formatters import fmt_records_page, RECORD_LABELS, VAL_LABELS, CHART_LABELS
from billboard_stats.bot.keyboards import (
    records_menu_keyboard,
    records_chart_keyboard,
    records_page_keyboard,
    cq_chart_keyboard,
    cq_rankby_keyboard,
    cq_param_keyboard,
    cq_results_page_keyboard,
)

logger = logging.getLogger(__name__)

PER_PAGE = 25

# Record types that only apply to one chart
HOT100_ONLY = {"n1s", "mse"}
B200_ONLY = {"n1a"}
# For drill-down items from leaderboard rows
ITEM_CB_PREFIX = "rec:item"


async def run_sync(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _chart_str(ct: str) -> str:
    return "hot-100" if ct == "h100" else "billboard-200"


async def records_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Billboard Records & Leaderboards</b>\n\nChoose a category:",
        parse_mode="HTML",
        reply_markup=records_menu_keyboard(),
    )


async def records_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split(":")

    try:
        if data == "rec:menu":
            await _show_menu(query)
        elif parts[1] == "chart" and len(parts) == 3:
            # rec:chart:wk1 — show chart picker (or auto-pick if chart-exclusive)
            await _handle_record_type(query, parts[2])
        elif parts[1] == "chart" and len(parts) == 4:
            # rec:chart:wk1:h100 — chart chosen, show page 1
            await _show_record_page(query, parts[3], parts[2], 1)
        elif parts[1] == "pg":
            # rec:pg:h100:wk1:2
            await _show_record_page(query, parts[2], parts[3], int(parts[4]))
        elif parts[1] == "cq":
            await _handle_custom_query(query, parts)
        else:
            await query.edit_message_text("Unknown action.")
    except Exception:
        logger.exception("Error in records_callback for data=%s", data)
        await query.answer("Error loading data.", show_alert=True)


async def _show_menu(query) -> None:
    try:
        await query.edit_message_text(
            "<b>Billboard Records &amp; Leaderboards</b>\n\nChoose a category:",
            parse_mode="HTML",
            reply_markup=records_menu_keyboard(),
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise


async def _handle_record_type(query, rtype: str) -> None:
    """Show chart picker or skip it for chart-exclusive types."""
    if rtype in HOT100_ONLY:
        await _show_record_page(query, "h100", rtype, 1)
    elif rtype in B200_ONLY:
        await _show_record_page(query, "b200", rtype, 1)
    else:
        try:
            await query.edit_message_text(
                f"<b>{RECORD_LABELS.get(rtype, rtype)}</b>\n\nSelect chart:",
                parse_mode="HTML",
                reply_markup=records_chart_keyboard(rtype),
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise


async def _fetch_records(rtype: str, chart_str: str, limit: int):
    """Call the appropriate service function."""
    if rtype == "wk1":
        return await run_sync(records_service.most_weeks_at_number_one, chart_str, limit)
    elif rtype == "lcr":
        return await run_sync(records_service.longest_chart_runs, chart_str, limit)
    elif rtype == "n1s":
        return await run_sync(records_service.most_number_one_songs_by_artist, chart_str, limit)
    elif rtype == "n1a":
        return await run_sync(records_service.most_number_one_albums_by_artist, chart_str, limit)
    elif rtype == "mea":
        return await run_sync(records_service.most_entries_by_artist, chart_str, limit)
    elif rtype == "mse":
        return await run_sync(records_service.most_simultaneous_entries, chart_str, limit)
    elif rtype == "bdeb":
        return await run_sync(records_service.biggest_debuts, chart_str, limit)
    elif rtype == "ftn1":
        return await run_sync(records_service.fastest_to_number_one, chart_str, limit)
    return []


async def _show_record_page(query, ct: str, rtype: str, page: int) -> None:
    chart_str = _chart_str(ct)
    all_results = await _fetch_records(rtype, chart_str, 200)

    if not all_results:
        await query.edit_message_text(
            "No records found for this category.",
            reply_markup=records_menu_keyboard(),
        )
        return

    total_pages = math.ceil(len(all_results) / PER_PAGE)
    page = max(1, min(page, total_pages))
    page_items = all_results[(page - 1) * PER_PAGE : page * PER_PAGE]

    chart_label = CHART_LABELS.get(chart_str, chart_str)
    val_label = VAL_LABELS.get(rtype, "value")
    record_name = RECORD_LABELS.get(rtype, rtype)

    text = fmt_records_page(page_items, record_name, chart_label, val_label, page, total_pages)
    keyboard = records_page_keyboard(ct, rtype, page, total_pages)

    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise


# ---------------------------------------------------------------------------
# Custom Query Builder
# ---------------------------------------------------------------------------

RANKBY_DISPLAY = {
    "wk1": ("weeks_at_number_one", 0, "Wks at #1"),
    "tot": ("total_weeks", 0, "Total Wks"),
    "pos": ("weeks_at_position", None, "Wks at Pos"),
    "topn": ("weeks_in_top_n", None, "Wks in Top-N"),
}


async def _handle_custom_query(query, parts: list) -> None:
    """Route custom query steps."""
    step = parts[2]

    if step == "start":
        try:
            await query.edit_message_text(
                "<b>Custom Query</b>\n\nSelect chart:",
                parse_mode="HTML",
                reply_markup=cq_chart_keyboard(),
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise

    elif step == "rankby":
        # rec:cq:rankby:h100
        ct = parts[3]
        try:
            await query.edit_message_text(
                "<b>Custom Query</b>\n\nRank by:",
                parse_mode="HTML",
                reply_markup=cq_rankby_keyboard(ct),
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise

    elif step == "param":
        # rec:cq:param:h100:pos
        ct = parts[3]
        rankby = parts[4]
        if rankby in ("wk1", "tot"):
            # No numeric param needed — go straight to run
            await _run_custom_query(query, ct, rankby, "0", 1)
        else:
            try:
                await query.edit_message_text(
                    f"<b>Custom Query</b>\n\nChoose parameter value:",
                    parse_mode="HTML",
                    reply_markup=cq_param_keyboard(ct, rankby),
                )
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    raise

    elif step == "run":
        # rec:cq:run:h100:pos:1
        ct = parts[3]
        rankby = parts[4]
        val = parts[5]
        await _run_custom_query(query, ct, rankby, val, 1)

    elif step == "pg":
        # rec:cq:pg:h100:pos:1:2
        ct = parts[3]
        rankby = parts[4]
        val = parts[5]
        page = int(parts[6])
        await _run_custom_query(query, ct, rankby, val, page)


async def _run_custom_query(query, ct: str, rankby: str, val: str, page: int) -> None:
    chart_str = _chart_str(ct)
    rank_by_map, _, val_label = RANKBY_DISPLAY.get(rankby, ("total_weeks", 0, "value"))
    rank_by_param = int(val)

    all_results = await run_sync(
        records_service.custom_query,
        rank_by_map,
        rank_by_param,
        chart_str,
        200,
    )

    if not all_results:
        try:
            await query.edit_message_text(
                "No results found for this query.",
                reply_markup=records_menu_keyboard(),
            )
        except BadRequest:
            pass
        return

    total_pages = math.ceil(len(all_results) / PER_PAGE)
    page = max(1, min(page, total_pages))
    page_items = all_results[(page - 1) * PER_PAGE : page * PER_PAGE]

    chart_label = CHART_LABELS.get(chart_str, chart_str)
    param_str = f" {val}" if rankby not in ("wk1", "tot") else ""
    record_name = f"Custom: {val_label}{param_str}"

    text = fmt_records_page(page_items, record_name, chart_label, val_label, page, total_pages)
    keyboard = cq_results_page_keyboard(ct, rankby, val, page, total_pages)

    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise


def get_handlers():
    return [
        CommandHandler("records", records_command),
        CallbackQueryHandler(records_callback, pattern=r"^rec:"),
    ]
