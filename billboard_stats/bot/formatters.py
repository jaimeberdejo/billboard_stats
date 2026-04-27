"""HTML text formatting functions for the Telegram bot."""

import html
from typing import List, Optional

from billboard_stats.models.schemas import (
    ArtistProfile,
    SongWithStats,
    AlbumWithStats,
    ChartEntry,
    ChartRunEntry,
    RecordEntry,
)

CHART_LABELS = {
    "hot-100": "Hot 100",
    "billboard-200": "Billboard 200",
}

RECORD_LABELS = {
    "wk1": "Most Weeks at #1",
    "lcr": "Longest Chart Runs",
    "n1s": "Most #1 Songs (Artist)",
    "n1a": "Most #1 Albums (Artist)",
    "mea": "Most Entries (Artist)",
    "mse": "Most Simultaneous Entries",
    "bdeb": "Biggest Debuts",
    "ftn1": "Fastest to #1",
}

VAL_LABELS = {
    "wk1": "wks at #1",
    "lcr": "total wks",
    "n1s": "#1 songs",
    "n1a": "#1 albums",
    "mea": "entries",
    "mse": "songs",
    "bdeb": "debut pos",
    "ftn1": "wks to #1",
}

CUSTOM_QUERY_LABELS = {
    "wk1": ("weeks_at_number_one", 0, "wks at #1"),
    "pos": ("weeks_at_position", None, "wks at pos"),
    "topn": ("weeks_in_top_n", None, "wks in top-N"),
    "tot": ("total_weeks", 0, "total wks"),
}


def _e(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text)) if text is not None else ""


def fmt_chart_page(
    entries: List[ChartEntry],
    chart_type: str,
    chart_date,
    page: int,
    total_pages: int,
) -> str:
    chart_label = CHART_LABELS.get(chart_type, chart_type)
    date_str = chart_date.strftime("%B %d, %Y") if chart_date else "Unknown"
    lines = [
        f"<b>{_e(chart_label)} — {_e(date_str)}</b>",
        f"<i>Page {page}/{total_pages}</i>",
        "",
    ]
    for entry in entries:
        badge = "🆕 " if entry.is_new else ""
        peak = f" ▲{entry.peak_pos}" if entry.peak_pos else ""
        wks = f" {entry.weeks_on_chart}wk" if entry.weeks_on_chart else ""
        lines.append(
            f"{badge}<b>#{entry.rank}</b> {_e(entry.title)}\n"
            f"    <i>{_e(entry.artist_credit)}</i>{peak}{wks}"
        )
    return "\n".join(lines)


def fmt_song_detail(song_with_stats: SongWithStats) -> str:
    song = song_with_stats.song
    stats = song_with_stats.stats
    artists = song_with_stats.artists

    artist_str = ", ".join(_e(a.name) for a in artists) if artists else _e(song.artist_credit)
    lines = [
        f"<b>{_e(song.title)}</b>",
        f"<i>{artist_str}</i>",
        "",
    ]
    if stats:
        debut = stats.debut_date.strftime("%b %d, %Y") if stats.debut_date else "—"
        last = stats.last_date.strftime("%b %d, %Y") if stats.last_date else "—"
        lines += [
            f"📅 Debut: <b>{_e(debut)}</b> at #{stats.debut_position or '—'}",
            f"📊 Total weeks: <b>{stats.total_weeks}</b>",
            f"🏆 Peak: <b>#{stats.peak_position or '—'}</b> ({stats.weeks_at_peak} wks)",
            f"1️⃣ Weeks at #1: <b>{stats.weeks_at_number_one}</b>",
            f"📆 Last seen: <b>{_e(last)}</b>",
        ]
    return "\n".join(lines)


def fmt_song_history_page(
    entries: List[ChartRunEntry],
    song_title: str,
    page: int,
    total_pages: int,
) -> str:
    lines = [
        f"<b>Chart History: {_e(song_title)}</b>",
        f"<i>Page {page}/{total_pages}</i>",
        "",
    ]
    for entry in entries:
        date_str = entry.chart_date.strftime("%b %d, %Y")
        badge = "🆕 " if entry.is_new else ""
        peak = f" (peak #{entry.peak_pos})" if entry.peak_pos else ""
        lines.append(f"{badge}{_e(date_str)} — <b>#{entry.rank}</b>{peak}")
    return "\n".join(lines)


def fmt_album_detail(album_with_stats: AlbumWithStats) -> str:
    album = album_with_stats.album
    stats = album_with_stats.stats
    artists = album_with_stats.artists

    artist_str = ", ".join(_e(a.name) for a in artists) if artists else _e(album.artist_credit)
    lines = [
        f"<b>{_e(album.title)}</b>",
        f"<i>{artist_str}</i>",
        "",
    ]
    if stats:
        debut = stats.debut_date.strftime("%b %d, %Y") if stats.debut_date else "—"
        last = stats.last_date.strftime("%b %d, %Y") if stats.last_date else "—"
        lines += [
            f"📅 Debut: <b>{_e(debut)}</b> at #{stats.debut_position or '—'}",
            f"📊 Total weeks: <b>{stats.total_weeks}</b>",
            f"🏆 Peak: <b>#{stats.peak_position or '—'}</b> ({stats.weeks_at_peak} wks)",
            f"1️⃣ Weeks at #1: <b>{stats.weeks_at_number_one}</b>",
            f"📆 Last seen: <b>{_e(last)}</b>",
        ]
    return "\n".join(lines)


def fmt_album_history_page(
    entries: List[ChartRunEntry],
    album_title: str,
    page: int,
    total_pages: int,
) -> str:
    lines = [
        f"<b>Chart History: {_e(album_title)}</b>",
        f"<i>Page {page}/{total_pages}</i>",
        "",
    ]
    for entry in entries:
        date_str = entry.chart_date.strftime("%b %d, %Y")
        badge = "🆕 " if entry.is_new else ""
        peak = f" (peak #{entry.peak_pos})" if entry.peak_pos else ""
        lines.append(f"{badge}{_e(date_str)} — <b>#{entry.rank}</b>{peak}")
    return "\n".join(lines)


def fmt_artist_profile(profile: ArtistProfile) -> str:
    artist = profile.artist
    stats = profile.stats
    lines = [f"<b>{_e(artist.name)}</b>", ""]
    if stats:
        first = stats.first_chart_date.strftime("%b %d, %Y") if stats.first_chart_date else "—"
        latest = stats.latest_chart_date.strftime("%b %d, %Y") if stats.latest_chart_date else "—"
        lines += [
            "<b>Hot 100</b>",
            f"  Songs: <b>{stats.total_hot100_songs}</b>",
            f"  Total weeks: <b>{stats.total_hot100_weeks}</b>",
            f"  #1 songs: <b>{stats.hot100_number_ones}</b>",
            f"  Best peak: <b>#{stats.best_hot100_peak or '—'}</b>",
            f"  Max simultaneous: <b>{stats.max_simultaneous_hot100}</b>",
            "",
            "<b>Billboard 200</b>",
            f"  Albums: <b>{stats.total_b200_albums}</b>",
            f"  Total weeks: <b>{stats.total_b200_weeks}</b>",
            f"  #1 albums: <b>{stats.b200_number_ones}</b>",
            f"  Best peak: <b>#{stats.best_b200_peak or '—'}</b>",
            "",
            f"📅 First charted: <b>{_e(first)}</b>",
            f"📆 Last seen: <b>{_e(latest)}</b>",
        ]
    return "\n".join(lines)


def fmt_artist_songs_page(
    songs: List[SongWithStats],
    artist_name: str,
    page: int,
    total_pages: int,
) -> str:
    lines = [
        f"<b>Hot 100 Songs: {_e(artist_name)}</b>",
        f"<i>Page {page}/{total_pages}</i>",
        "",
    ]
    for i, sws in enumerate(songs):
        s = sws.song
        st = sws.stats
        peak = f" ▲#{st.peak_position}" if st and st.peak_position else ""
        wks = f" {st.total_weeks}wk" if st else ""
        lines.append(f"<b>{i + 1}.</b> {_e(s.title)}{peak}{wks}")
    return "\n".join(lines)


def fmt_artist_albums_page(
    albums: List[AlbumWithStats],
    artist_name: str,
    page: int,
    total_pages: int,
) -> str:
    lines = [
        f"<b>Billboard 200 Albums: {_e(artist_name)}</b>",
        f"<i>Page {page}/{total_pages}</i>",
        "",
    ]
    for i, aws in enumerate(albums):
        a = aws.album
        st = aws.stats
        peak = f" ▲#{st.peak_position}" if st and st.peak_position else ""
        wks = f" {st.total_weeks}wk" if st else ""
        lines.append(f"<b>{i + 1}.</b> {_e(a.title)}{peak}{wks}")
    return "\n".join(lines)


def fmt_records_page(
    results: List[RecordEntry],
    record_name: str,
    chart_label: str,
    val_label: str,
    page: int,
    total_pages: int,
) -> str:
    lines = [
        f"<b>{_e(record_name)}</b>",
        f"<i>{_e(chart_label)} · Page {page}/{total_pages}</i>",
        "",
    ]
    for entry in results:
        lines.append(
            f"<b>#{entry.rank}</b> {_e(entry.title)}\n"
            f"    <i>{_e(entry.artist_credit)}</i> — {entry.value} {_e(val_label)}"
        )
    return "\n".join(lines)


def fmt_data_status(summary: dict) -> str:
    counts = summary.get("counts", {})
    dates = summary.get("latest_dates", {})

    h100_date = dates.get("hot-100", "—")
    b200_date = dates.get("billboard-200", "—")
    if hasattr(h100_date, "strftime"):
        h100_date = h100_date.strftime("%b %d, %Y")
    if hasattr(b200_date, "strftime"):
        b200_date = b200_date.strftime("%b %d, %Y")

    lines = [
        "<b>Database Status</b>",
        "",
        f"🎵 Songs: <b>{counts.get('songs', 0):,}</b>",
        f"💿 Albums: <b>{counts.get('albums', 0):,}</b>",
        f"👤 Artists: <b>{counts.get('artists', 0):,}</b>",
        f"📊 Hot 100 entries: <b>{counts.get('hot100_entries', 0):,}</b>",
        f"📊 B200 entries: <b>{counts.get('b200_entries', 0):,}</b>",
        "",
        f"📅 Latest Hot 100: <b>{_e(str(h100_date))}</b>",
        f"📅 Latest Billboard 200: <b>{_e(str(b200_date))}</b>",
    ]
    return "\n".join(lines)


def split_message(text: str, max_len: int = 4096) -> List[str]:
    """Split a long message on newlines to stay within Telegram's limit."""
    if len(text) <= max_len:
        return [text]
    parts = []
    current = []
    current_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > max_len and current:
            parts.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len
    if current:
        parts.append("\n".join(current))
    return parts
