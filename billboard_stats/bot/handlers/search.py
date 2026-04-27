"""Search ConversationHandler with artist/song/album drill-down."""

import logging
import asyncio
import math
from typing import List

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.error import BadRequest

from billboard_stats.services import artist_service, song_service, album_service
from billboard_stats.bot.formatters import (
    fmt_artist_profile,
    fmt_artist_songs_page,
    fmt_artist_albums_page,
    fmt_song_detail,
    fmt_song_history_page,
    fmt_album_detail,
    fmt_album_history_page,
)
from billboard_stats.bot.keyboards import (
    search_type_keyboard,
    search_results_keyboard,
    artist_detail_keyboard,
    artist_songs_page_keyboard,
    artist_albums_page_keyboard,
    song_detail_keyboard,
    album_detail_keyboard,
    history_page_keyboard,
)

logger = logging.getLogger(__name__)

SEARCH_TYPE = 0
SEARCH_QUERY = 1
SEARCH_RESULTS = 2
DETAIL_VIEW = 3

SONGS_PER_PAGE = 30
ALBUMS_PER_PAGE = 30
HISTORY_PER_PAGE = 30


async def run_sync(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "What would you like to search for?",
        reply_markup=search_type_keyboard(),
    )
    return SEARCH_TYPE


async def search_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    entity_type = parts[2]  # art, sng, alb
    context.user_data["search_type"] = entity_type

    type_label = {"art": "artist", "sng": "song", "alb": "album"}[entity_type]
    try:
        await query.edit_message_text(f"Enter the {type_label} name to search for:")
    except BadRequest:
        pass
    return SEARCH_QUERY


async def search_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query_text = update.message.text.strip()
    entity_type = context.user_data.get("search_type", "art")

    await update.message.reply_text("Searching...")

    try:
        if entity_type == "art":
            results = await run_sync(artist_service.search_artists, query_text, 10)
        elif entity_type == "sng":
            results = await run_sync(song_service.search_songs, query_text, 10)
        else:
            results = await run_sync(album_service.search_albums, query_text, 10)
    except Exception:
        logger.exception("Search failed")
        await update.message.reply_text("Error during search. Please try again.")
        return SEARCH_QUERY

    if not results:
        await update.message.reply_text(
            "No results found. Try a different search term.",
            reply_markup=search_type_keyboard(),
        )
        return SEARCH_TYPE

    context.user_data["search_results"] = results
    await update.message.reply_text(
        f"Found {len(results)} result(s). Pick one:",
        reply_markup=search_results_keyboard(results, entity_type),
    )
    return SEARCH_RESULTS


async def search_result_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    idx = int(parts[2])
    results = context.user_data.get("search_results", [])
    entity_type = context.user_data.get("search_type", "art")

    if idx >= len(results):
        await query.edit_message_text("Invalid selection. Use /search to start again.")
        return ConversationHandler.END

    item = results[idx]

    if entity_type == "art":
        return await _show_artist(query, context, item.id)
    elif entity_type == "sng":
        return await _show_song(query, context, item.song.id)
    else:
        return await _show_album(query, context, item.album.id)


async def search_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle all srch:* callbacks for drill-down from outside the conversation."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    action = parts[1]

    if action == "art":
        artist_id = int(parts[2])
        return await _show_artist(query, context, artist_id)

    elif action == "sng":
        song_id = int(parts[2])
        return await _show_song(query, context, song_id)

    elif action == "alb":
        album_id = int(parts[2])
        return await _show_album(query, context, album_id)

    elif action == "sng_hist":
        song_id = int(parts[2])
        page = int(parts[3])
        return await _show_song_history(query, context, song_id, page)

    elif action == "alb_hist":
        album_id = int(parts[2])
        page = int(parts[3])
        return await _show_album_history(query, context, album_id, page)

    elif action == "art_songs":
        artist_id = int(parts[2])
        page = int(parts[3])
        return await _show_artist_songs(query, context, artist_id, page)

    elif action == "art_albums":
        artist_id = int(parts[2])
        page = int(parts[3])
        return await _show_artist_albums(query, context, artist_id, page)

    return DETAIL_VIEW


async def _show_artist(query, context, artist_id: int) -> int:
    try:
        profile = await run_sync(artist_service.get_artist_profile, artist_id)
        if not profile:
            await query.edit_message_text("Artist not found.")
            return DETAIL_VIEW

        context.user_data["current_artist_id"] = artist_id
        text = fmt_artist_profile(profile)
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=artist_detail_keyboard(artist_id),
        )
    except Exception:
        logger.exception("Error showing artist")
        await query.answer("Error loading artist data.", show_alert=True)
    return DETAIL_VIEW


async def _show_song(query, context, song_id: int) -> int:
    try:
        song_ws = await run_sync(song_service.get_song, song_id)
        if not song_ws:
            await query.edit_message_text("Song not found.")
            return DETAIL_VIEW

        context.user_data["current_song_id"] = song_id
        text = fmt_song_detail(song_ws)
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=song_detail_keyboard(song_id, song_ws.artists),
        )
    except Exception:
        logger.exception("Error showing song")
        await query.answer("Error loading song data.", show_alert=True)
    return DETAIL_VIEW


async def _show_album(query, context, album_id: int) -> int:
    try:
        album_ws = await run_sync(album_service.get_album, album_id)
        if not album_ws:
            await query.edit_message_text("Album not found.")
            return DETAIL_VIEW

        context.user_data["current_album_id"] = album_id
        text = fmt_album_detail(album_ws)
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=album_detail_keyboard(album_id, album_ws.artists),
        )
    except Exception:
        logger.exception("Error showing album")
        await query.answer("Error loading album data.", show_alert=True)
    return DETAIL_VIEW


async def _show_song_history(query, context, song_id: int, page: int) -> int:
    try:
        history = await run_sync(song_service.get_chart_run, song_id)
        if not history:
            await query.edit_message_text("No chart history found.")
            return DETAIL_VIEW

        # Get song title for header
        song_ws = await run_sync(song_service.get_song, song_id)
        title = song_ws.song.title if song_ws else f"Song #{song_id}"

        total_pages = math.ceil(len(history) / HISTORY_PER_PAGE)
        page = max(1, min(page, total_pages))
        page_entries = history[(page - 1) * HISTORY_PER_PAGE : page * HISTORY_PER_PAGE]

        text = fmt_song_history_page(page_entries, title, page, total_pages)
        keyboard = history_page_keyboard("sng", song_id, page, total_pages)

        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    except Exception:
        logger.exception("Error showing song history")
        await query.answer("Error loading chart history.", show_alert=True)
    return DETAIL_VIEW


async def _show_album_history(query, context, album_id: int, page: int) -> int:
    try:
        history = await run_sync(album_service.get_chart_run, album_id)
        if not history:
            await query.edit_message_text("No chart history found.")
            return DETAIL_VIEW

        album_ws = await run_sync(album_service.get_album, album_id)
        title = album_ws.album.title if album_ws else f"Album #{album_id}"

        total_pages = math.ceil(len(history) / HISTORY_PER_PAGE)
        page = max(1, min(page, total_pages))
        page_entries = history[(page - 1) * HISTORY_PER_PAGE : page * HISTORY_PER_PAGE]

        text = fmt_album_history_page(page_entries, title, page, total_pages)
        keyboard = history_page_keyboard("alb", album_id, page, total_pages)

        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    except Exception:
        logger.exception("Error showing album history")
        await query.answer("Error loading chart history.", show_alert=True)
    return DETAIL_VIEW


async def _show_artist_songs(query, context, artist_id: int, page: int) -> int:
    try:
        songs = await run_sync(artist_service.get_artist_songs, artist_id)
        if not songs:
            await query.edit_message_text("No Hot 100 songs found for this artist.")
            return DETAIL_VIEW

        profile = await run_sync(artist_service.get_artist_profile, artist_id)
        artist_name = profile.artist.name if profile else f"Artist #{artist_id}"

        total_pages = math.ceil(len(songs) / SONGS_PER_PAGE)
        page = max(1, min(page, total_pages))
        page_items = songs[(page - 1) * SONGS_PER_PAGE : page * SONGS_PER_PAGE]

        text = fmt_artist_songs_page(page_items, artist_name, page, total_pages)
        keyboard = artist_songs_page_keyboard(artist_id, page, total_pages)

        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    except Exception:
        logger.exception("Error showing artist songs")
        await query.answer("Error loading artist songs.", show_alert=True)
    return DETAIL_VIEW


async def _show_artist_albums(query, context, artist_id: int, page: int) -> int:
    try:
        albums = await run_sync(artist_service.get_artist_albums, artist_id)
        if not albums:
            await query.edit_message_text("No Billboard 200 albums found for this artist.")
            return DETAIL_VIEW

        profile = await run_sync(artist_service.get_artist_profile, artist_id)
        artist_name = profile.artist.name if profile else f"Artist #{artist_id}"

        total_pages = math.ceil(len(albums) / ALBUMS_PER_PAGE)
        page = max(1, min(page, total_pages))
        page_items = albums[(page - 1) * ALBUMS_PER_PAGE : page * ALBUMS_PER_PAGE]

        text = fmt_artist_albums_page(page_items, artist_name, page, total_pages)
        keyboard = artist_albums_page_keyboard(artist_id, page, total_pages)

        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    except Exception:
        logger.exception("Error showing artist albums")
        await query.answer("Error loading artist albums.", show_alert=True)
    return DETAIL_VIEW


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Search cancelled.")
    return ConversationHandler.END


async def expired_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer("Session expired. Use /search to start again.", show_alert=True)
    return ConversationHandler.END


def get_handlers():
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("search", search_command)],
        states={
            SEARCH_TYPE: [
                CallbackQueryHandler(search_type_callback, pattern=r"^srch:type:"),
            ],
            SEARCH_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_query_handler),
            ],
            SEARCH_RESULTS: [
                CallbackQueryHandler(search_result_callback, pattern=r"^srch:res:"),
                CallbackQueryHandler(search_inline_callback, pattern=r"^srch:(art|sng|alb|sng_hist|alb_hist|art_songs|art_albums):"),
            ],
            DETAIL_VIEW: [
                CallbackQueryHandler(search_inline_callback, pattern=r"^srch:(art|sng|alb|sng_hist|alb_hist|art_songs|art_albums):"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_search),
            CommandHandler("search", search_command),
        ],
        conversation_timeout=300,
        per_message=False,
        per_chat=True,
    )
    # Standalone handler for srch:* callbacks triggered from outside conversations
    # (e.g., from records leaderboard drill-down)
    standalone = CallbackQueryHandler(search_inline_callback, pattern=r"^srch:(art|sng|alb|sng_hist|alb_hist|art_songs|art_albums):")
    return [conv_handler, standalone]
