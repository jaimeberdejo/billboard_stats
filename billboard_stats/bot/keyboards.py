"""InlineKeyboardMarkup builder functions for the Telegram bot."""

from typing import List, Optional
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from billboard_stats.models.schemas import Artist, SongWithStats, AlbumWithStats


def chart_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Hot 100", callback_data="chart:h100:1:latest"),
            InlineKeyboardButton("Billboard 200", callback_data="chart:b200:1:latest"),
        ]
    ])


def _date_str(d) -> str:
    return d.strftime("%Y-%m-%d") if d else "latest"


def chart_nav_keyboard(
    chart_type: str,
    chart_date,
    page: int,
    total_pages: int,
    available_dates: List[date],
) -> InlineKeyboardMarkup:
    ct = "h100" if chart_type == "hot-100" else "b200"
    date_s = _date_str(chart_date)

    # Find adjacent dates
    try:
        idx = [_date_str(d) for d in available_dates].index(date_s)
    except ValueError:
        idx = 0

    prev_date = _date_str(available_dates[idx + 1]) if idx + 1 < len(available_dates) else None
    next_date = _date_str(available_dates[idx - 1]) if idx > 0 else None

    rows = []

    # Page navigation
    page_row = []
    if page > 1:
        page_row.append(InlineKeyboardButton("◀ Prev", callback_data=f"chart:{ct}:{page-1}:{date_s}"))
    if page < total_pages:
        page_row.append(InlineKeyboardButton("Next ▶", callback_data=f"chart:{ct}:{page+1}:{date_s}"))
    if page_row:
        rows.append(page_row)

    # Date navigation
    date_row = []
    if prev_date:
        date_row.append(InlineKeyboardButton("⬅ Older", callback_data=f"chart:{ct}:nav:prev:{prev_date}"))
    if next_date:
        date_row.append(InlineKeyboardButton("Newer ➡", callback_data=f"chart:{ct}:nav:next:{next_date}"))
    if date_row:
        rows.append(date_row)

    rows.append([InlineKeyboardButton("🔄 Change Chart", callback_data="chart:pick")])
    return InlineKeyboardMarkup(rows)


def search_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎤 Artists", callback_data="srch:type:art"),
            InlineKeyboardButton("🎵 Songs", callback_data="srch:type:sng"),
            InlineKeyboardButton("💿 Albums", callback_data="srch:type:alb"),
        ]
    ])


def search_results_keyboard(results: list, entity_type: str) -> InlineKeyboardMarkup:
    rows = []
    for i, item in enumerate(results[:10]):
        if entity_type == "art":
            label = item.name if hasattr(item, "name") else str(item)
        else:
            label = item.song.title if hasattr(item, "song") else (
                item.album.title if hasattr(item, "album") else str(item)
            )
        # Truncate label to keep callback data short
        label = label[:40]
        rows.append([InlineKeyboardButton(
            f"{i+1}. {label}",
            callback_data=f"srch:res:{i}"
        )])
    return InlineKeyboardMarkup(rows)


def artist_detail_keyboard(artist_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Hot 100 Songs", callback_data=f"srch:art_songs:{artist_id}:1"),
            InlineKeyboardButton("💿 B200 Albums", callback_data=f"srch:art_albums:{artist_id}:1"),
        ]
    ])


def song_detail_keyboard(song_id: int, artists: List) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📈 Chart History", callback_data=f"srch:sng_hist:{song_id}:1")],
    ]
    for artist in artists[:3]:
        rows.append([InlineKeyboardButton(
            f"👤 {artist.name[:35]}",
            callback_data=f"srch:art:{artist.id}"
        )])
    return InlineKeyboardMarkup(rows)


def album_detail_keyboard(album_id: int, artists: List) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📈 Chart History", callback_data=f"srch:alb_hist:{album_id}:1")],
    ]
    for artist in artists[:3]:
        rows.append([InlineKeyboardButton(
            f"👤 {artist.name[:35]}",
            callback_data=f"srch:art:{artist.id}"
        )])
    return InlineKeyboardMarkup(rows)


def history_page_keyboard(
    entity_type: str,
    entity_id: int,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    prefix = "srch:sng_hist" if entity_type == "sng" else "srch:alb_hist"
    rows = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"{prefix}:{entity_id}:{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"{prefix}:{entity_id}:{page+1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(rows)


def artist_songs_page_keyboard(
    artist_id: int,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"srch:art_songs:{artist_id}:{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"srch:art_songs:{artist_id}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("👤 Back to Artist", callback_data=f"srch:art:{artist_id}")])
    return InlineKeyboardMarkup(rows)


def artist_albums_page_keyboard(
    artist_id: int,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"srch:art_albums:{artist_id}:{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"srch:art_albums:{artist_id}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("👤 Back to Artist", callback_data=f"srch:art:{artist_id}")])
    return InlineKeyboardMarkup(rows)


def records_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Weeks at #1", callback_data="rec:chart:wk1"),
            InlineKeyboardButton("Longest Runs", callback_data="rec:chart:lcr"),
        ],
        [
            InlineKeyboardButton("Most #1 Songs", callback_data="rec:chart:n1s"),
            InlineKeyboardButton("Most #1 Albums", callback_data="rec:chart:n1a"),
        ],
        [
            InlineKeyboardButton("Most Entries", callback_data="rec:chart:mea"),
            InlineKeyboardButton("Simultaneous", callback_data="rec:chart:mse"),
        ],
        [
            InlineKeyboardButton("Biggest Debuts", callback_data="rec:chart:bdeb"),
            InlineKeyboardButton("Fastest to #1", callback_data="rec:chart:ftn1"),
        ],
        [InlineKeyboardButton("🔧 Custom Query", callback_data="rec:cq:start")],
    ])


def records_chart_keyboard(rtype: str) -> InlineKeyboardMarkup:
    """Chart picker for a record type that applies to both charts."""
    # n1s (Hot 100 only), n1a (B200 only), mse (Hot 100 only) skip the picker
    rows = [
        [
            InlineKeyboardButton("Hot 100", callback_data=f"rec:chart:{rtype}:h100"),
            InlineKeyboardButton("Billboard 200", callback_data=f"rec:chart:{rtype}:b200"),
        ],
        [InlineKeyboardButton("« Back", callback_data="rec:menu")],
    ]
    return InlineKeyboardMarkup(rows)


def records_page_keyboard(
    chart: str,
    rtype: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"rec:pg:{chart}:{rtype}:{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"rec:pg:{chart}:{rtype}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("« Records Menu", callback_data="rec:menu")])
    return InlineKeyboardMarkup(rows)


def cq_chart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Hot 100", callback_data="rec:cq:rankby:h100"),
            InlineKeyboardButton("Billboard 200", callback_data="rec:cq:rankby:b200"),
        ],
        [InlineKeyboardButton("« Back", callback_data="rec:menu")],
    ])


def cq_rankby_keyboard(chart: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Wks at #1", callback_data=f"rec:cq:param:{chart}:wk1"),
            InlineKeyboardButton("Total Wks", callback_data=f"rec:cq:param:{chart}:tot"),
        ],
        [
            InlineKeyboardButton("Wks at Pos X", callback_data=f"rec:cq:param:{chart}:pos"),
            InlineKeyboardButton("Wks in Top-N", callback_data=f"rec:cq:param:{chart}:topn"),
        ],
        [InlineKeyboardButton("« Back", callback_data="rec:cq:start")],
    ])


def cq_param_keyboard(chart: str, rankby: str) -> InlineKeyboardMarkup:
    if rankby == "pos":
        values = [1, 2, 3, 5, 10, 20, 40]
    else:  # topn
        values = [5, 10, 20, 40, 50, 75, 100]

    # Build rows of 4
    rows = []
    row = []
    for v in values:
        row.append(InlineKeyboardButton(str(v), callback_data=f"rec:cq:run:{chart}:{rankby}:{v}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("« Back", callback_data=f"rec:cq:rankby:{chart}")])
    return InlineKeyboardMarkup(rows)


def cq_run_keyboard(chart: str, rankby: str, val: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶ Run Query", callback_data=f"rec:cq:run:{chart}:{rankby}:{val}")],
        [InlineKeyboardButton("« Back", callback_data=f"rec:cq:param:{chart}:{rankby}")],
    ])


def cq_results_page_keyboard(
    chart: str,
    rankby: str,
    val: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"rec:cq:pg:{chart}:{rankby}:{val}:{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"rec:cq:pg:{chart}:{rankby}:{val}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("« Records Menu", callback_data="rec:menu")])
    return InlineKeyboardMarkup(rows)


def admin_update_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm Update", callback_data="adm:update:confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="adm:update:cancel"),
        ]
    ])
