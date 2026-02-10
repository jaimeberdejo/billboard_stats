"""Streamlit frontend for Billboard Music Statistics Platform.

Kworb.net-inspired dense, data-first UI.
Run with: streamlit run billboard_stats/app.py
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import altair as alt
import pandas as pd
import streamlit as st

from billboard_stats.services import (
    artist_service,
    song_service,
    album_service,
    chart_service,
    records_service,
    data_status_service,
)
from billboard_stats.etl.updater import update_charts, repair_gaps
from billboard_stats.db.connection import get_conn, put_conn

st.set_page_config(page_title="Billboard Stats", layout="wide")



# ---------------------------------------------------------------------------
# Chart helpers (kept from original)
# ---------------------------------------------------------------------------

def _assign_chart_runs(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("Date").reset_index(drop=True)
    gaps = df["Date"].diff() > pd.Timedelta(days=14)
    df["run"] = gaps.cumsum()
    return df


def _build_chart_run_chart(entries, chart_type: str) -> alt.Chart:
    df = pd.DataFrame([
        {
            "Date": e.chart_date,
            "Position": e.rank,
            "Last Week": e.last_pos,
            "Peak": e.peak_pos,
            "Weeks on Chart": e.weeks_on_chart,
        }
        for e in entries
    ])
    df = _assign_chart_runs(df)
    num_weeks = len(df)
    y_max = 200 if chart_type == "billboard-200" else 100
    stroke_width = 1.5 if num_weeks > 150 else 2
    tooltip = [
        alt.Tooltip("Date:T", title="Week"),
        alt.Tooltip("Position:Q", title="Position"),
        alt.Tooltip("Last Week:Q", title="Last Week"),
        alt.Tooltip("Peak:Q", title="Peak"),
        alt.Tooltip("Weeks on Chart:Q", title="Weeks on Chart"),
    ]
    show_points = num_weeks <= 80
    zoom = alt.selection_interval(bind="scales")
    chart = (
        alt.Chart(df)
        .mark_line(point=show_points, strokeWidth=stroke_width)
        .encode(
            x=alt.X("Date:T", title="Week"),
            y=alt.Y("Position:Q", title="Chart Position",
                     scale=alt.Scale(domain=[y_max, 1]),
                     axis=alt.Axis(tickCount=10, titlePadding=40, labelFlush=True)),
            detail="run:N",
            tooltip=tooltip,
        )
        .properties(height=420)
        .add_params(zoom)
    )
    return chart


def _build_chart_history_df(entries) -> pd.DataFrame:
    rows = []
    for e in entries:
        last = e.last_pos
        off_chart = last is not None and last == 0
        change = None
        if not off_chart and last is not None:
            change = last - e.rank
        if off_chart:
            change_label = "NEW" if e.is_new else "RE"
        else:
            change_label = change
        rows.append({
            "Week": e.chart_date,
            "Pos": e.rank,
            "LW": "—" if off_chart else (last if last is not None else "—"),
            "Chg": change_label,
            "Pk": e.peak_pos,
            "Wks": e.weeks_on_chart,
        })
    df = pd.DataFrame(rows)
    df = df.sort_values("Week", ascending=False).reset_index(drop=True)
    df["Chg"] = df["Chg"].apply(
        lambda v: v if isinstance(v, str)
        else f"+{v}" if v is not None and v > 0
        else str(v) if v is not None
        else "—"
    )
    return df


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------

def _nav(page: str, **kwargs):
    st.session_state["page"] = page
    # Clear drill-down state when leaving any page
    for stale_key in ("_dd_last_sel_idx", "records_drilldown_artist_id",
                       "records_drilldown_chart_date"):
        st.session_state.pop(stale_key, None)
    for k, v in kwargs.items():
        st.session_state[k] = v


def _back():
    prev = st.session_state.get("prev_page", "Latest Charts")
    st.session_state["page"] = prev


if "page" not in st.session_state:
    st.session_state["page"] = "Latest Charts"

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Billboard Stats")
    for label in ["Latest Charts", "Search", "Records", "Data Status"]:
        if st.button(label, key=f"nav_{label}"):
            _nav(label)
            st.rerun()

page = st.session_state["page"]


# ===================================================================
# Helper: format a change value for chart tables
# ===================================================================
def _fmt_lw(last_pos, is_new):
    if last_pos is None or last_pos == 0:
        return "NEW" if is_new else "RE" if last_pos == 0 else "—"
    return last_pos


def _fmt_chg(last_pos, rank, is_new):
    if last_pos is None or last_pos == 0:
        return "NEW" if is_new else "RE" if last_pos == 0 else "—"
    diff = last_pos - rank
    if diff > 0:
        return f"+{diff}"
    return str(diff) if diff != 0 else "="


# ===================================================================
# PAGE: Latest Charts
# ===================================================================
if page == "Latest Charts":
    chart_type = st.radio(
        "Chart", ["hot-100", "billboard-200"],
        format_func=lambda x: "Hot 100" if x == "hot-100" else "Billboard 200",
        horizontal=True, key="lc_chart_type",
    )

    available_dates = chart_service.get_available_dates(chart_type)
    if not available_dates:
        st.warning("No chart data available.")
    else:
        latest = available_dates[0]
        st.caption(f"Latest: {latest.strftime('%B %d, %Y')}")

        selected_date = st.selectbox(
            "Week", options=available_dates,
            format_func=lambda d: d.strftime("%B %d, %Y"),
            key="lc_date",
        )

        with st.spinner("Loading chart..."):
            entries = chart_service.get_weekly_chart(selected_date, chart_type)
        if entries:
            rows = []
            for e in entries:
                rows.append({
                    "Pos": e.rank,
                    "Title": e.title,
                    "Artist": e.artist_credit,
                    "LW": _fmt_lw(e.last_pos, e.is_new),
                    "Chg": _fmt_chg(e.last_pos, e.rank, e.is_new),
                    "Pk": e.peak_pos,
                    "Wks": e.weeks_on_chart,
                    "_song_id": e.song_id,
                    "_album_id": e.album_id,
                })
            df = pd.DataFrame(rows)
            display_cols = ["Pos", "Title", "Artist", "LW", "Chg", "Pk", "Wks"]

            event = st.dataframe(
                df[display_cols],
                hide_index=True, use_container_width=True,
                on_select="rerun", selection_mode="single-row",
                key="lc_table",
            )
            if event.selection.rows:
                idx = event.selection.rows[0]
                st.session_state["prev_page"] = "Latest Charts"
                if chart_type == "hot-100" and df.iloc[idx]["_song_id"]:
                    _nav("Song Detail", song_id=int(df.iloc[idx]["_song_id"]))
                elif chart_type == "billboard-200" and df.iloc[idx]["_album_id"]:
                    _nav("Album Detail", album_id=int(df.iloc[idx]["_album_id"]))
                st.rerun()
        else:
            st.info("No entries for this date.")


# ===================================================================
# PAGE: Search
# ===================================================================
elif page == "Search":
    st.header("Search")
    query = st.text_input("Search artists, songs, or albums", key="search_q")

    search_type = st.radio(
        "Type", ["Artists", "Songs", "Albums"],
        horizontal=True, key="search_type",
    )

    if query and len(query) >= 2:
        if search_type == "Artists":
            with st.spinner("Searching..."):
                artists = artist_service.search_artists(query, limit=50)
            if artists:
                rows = [{"Name": a.name, "_id": a.id} for a in artists]
                df = pd.DataFrame(rows)
                event = st.dataframe(
                    df[["Name"]], hide_index=True, use_container_width=True,
                    on_select="rerun", selection_mode="single-row",
                    key="search_artists_table",
                )
                if event.selection.rows:
                    idx = event.selection.rows[0]
                    st.session_state["prev_page"] = "Search"
                    _nav("Artist Detail", artist_id=int(df.iloc[idx]["_id"]))
                    st.rerun()
            else:
                st.info("No artists found.")

        elif search_type == "Songs":
            with st.spinner("Searching..."):
                songs = song_service.search_songs(query, limit=50)
            if songs:
                rows = [{
                    "Title": s.song.title,
                    "Artist": s.song.artist_credit,
                    "Pk": s.stats.peak_position if s.stats else None,
                    "Wks": s.stats.total_weeks if s.stats else None,
                    "Wks@Pk": s.stats.weeks_at_peak if s.stats else None,
                    "_id": s.song.id,
                } for s in songs]
                df = pd.DataFrame(rows)
                event = st.dataframe(
                    df[["Title", "Artist", "Pk", "Wks", "Wks@Pk"]],
                    hide_index=True, use_container_width=True,
                    on_select="rerun", selection_mode="single-row",
                    key="search_songs_table",
                )
                if event.selection.rows:
                    idx = event.selection.rows[0]
                    st.session_state["prev_page"] = "Search"
                    _nav("Song Detail", song_id=int(df.iloc[idx]["_id"]))
                    st.rerun()
            else:
                st.info("No songs found.")

        elif search_type == "Albums":
            with st.spinner("Searching..."):
                albums = album_service.search_albums(query, limit=50)
            if albums:
                rows = [{
                    "Title": a.album.title,
                    "Artist": a.album.artist_credit,
                    "Pk": a.stats.peak_position if a.stats else None,
                    "Wks": a.stats.total_weeks if a.stats else None,
                    "Wks@Pk": a.stats.weeks_at_peak if a.stats else None,
                    "_id": a.album.id,
                } for a in albums]
                df = pd.DataFrame(rows)
                event = st.dataframe(
                    df[["Title", "Artist", "Pk", "Wks", "Wks@Pk"]],
                    hide_index=True, use_container_width=True,
                    on_select="rerun", selection_mode="single-row",
                    key="search_albums_table",
                )
                if event.selection.rows:
                    idx = event.selection.rows[0]
                    st.session_state["prev_page"] = "Search"
                    _nav("Album Detail", album_id=int(df.iloc[idx]["_id"]))
                    st.rerun()
            else:
                st.info("No albums found.")
    elif query:
        st.caption("Type at least 2 characters to search.")


# ===================================================================
# PAGE: Artist Detail
# ===================================================================
elif page == "Artist Detail":
    if st.button("< Back"):
        _back()
        st.rerun()

    artist_id = st.session_state.get("artist_id")
    if not artist_id:
        st.error("No artist selected.")
    else:
        with st.spinner("Loading artist..."):
            profile = artist_service.get_artist_profile(artist_id)
        if not profile:
            st.error("Artist not found.")
        else:
            st.header(profile.artist.name)
            s = profile.stats
            if s:
                first = s.first_chart_date.strftime("%b %d, %Y") if s.first_chart_date else "—"
                latest = s.latest_chart_date.strftime("%b %d, %Y") if s.latest_chart_date else "—"
                best_h = f"#{s.best_hot100_peak}" if s.best_hot100_peak else "—"
                best_b = f"#{s.best_b200_peak}" if s.best_b200_peak else "—"

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Songs", s.total_hot100_songs)
                c2.metric("Albums", s.total_b200_albums)
                c3.metric("#1 Songs", s.hot100_number_ones)
                c4.metric("#1 Albums", s.b200_number_ones)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Hot 100 Weeks", f"{s.total_hot100_weeks:,}")
                c2.metric("B200 Weeks", f"{s.total_b200_weeks:,}")
                c3.metric("Best Hot 100 Peak", best_h)
                c4.metric("Best B200 Peak", best_b)

                c1, c2, c3 = st.columns(3)
                c1.metric("Max Simultaneous", s.max_simultaneous_hot100)
                c2.metric("First Charted", first)
                c3.metric("Latest", latest)

            # --- Songs table ---
            st.markdown("---")
            st.subheader("Songs")
            with st.spinner("Loading songs..."):
                songs = artist_service.get_artist_songs(artist_id)
            if songs:
                rows = [{
                    "Title": sw.song.title,
                    "Pk": sw.stats.peak_position if sw.stats else None,
                    "Wks": sw.stats.total_weeks if sw.stats else None,
                    "Wks@Pk": sw.stats.weeks_at_peak if sw.stats else None,
                    "Debut": str(sw.stats.debut_date) if sw.stats and sw.stats.debut_date else "—",
                    "_id": sw.song.id,
                } for sw in songs]
                df = pd.DataFrame(rows)
                event = st.dataframe(
                    df[["Title", "Pk", "Wks", "Wks@Pk", "Debut"]],
                    hide_index=True, use_container_width=True,
                    on_select="rerun", selection_mode="single-row",
                    key="artist_songs_table",
                )
                if event.selection.rows:
                    idx = event.selection.rows[0]
                    st.session_state["prev_page"] = "Artist Detail"
                    _nav("Song Detail", song_id=int(df.iloc[idx]["_id"]))
                    st.rerun()
            else:
                st.info("No songs found.")

            # --- Albums table ---
            st.markdown("---")
            st.subheader("Albums")
            with st.spinner("Loading albums..."):
                albums = artist_service.get_artist_albums(artist_id)
            if albums:
                rows = [{
                    "Title": aw.album.title,
                    "Pk": aw.stats.peak_position if aw.stats else None,
                    "Wks": aw.stats.total_weeks if aw.stats else None,
                    "Wks@Pk": aw.stats.weeks_at_peak if aw.stats else None,
                    "Debut": str(aw.stats.debut_date) if aw.stats and aw.stats.debut_date else "—",
                    "_id": aw.album.id,
                } for aw in albums]
                df = pd.DataFrame(rows)
                event = st.dataframe(
                    df[["Title", "Pk", "Wks", "Wks@Pk", "Debut"]],
                    hide_index=True, use_container_width=True,
                    on_select="rerun", selection_mode="single-row",
                    key="artist_albums_table",
                )
                if event.selection.rows:
                    idx = event.selection.rows[0]
                    st.session_state["prev_page"] = "Artist Detail"
                    _nav("Album Detail", album_id=int(df.iloc[idx]["_id"]))
                    st.rerun()
            else:
                st.info("No albums found.")


# ===================================================================
# PAGE: Song Detail
# ===================================================================
elif page == "Song Detail":
    if st.button("< Back"):
        _back()
        st.rerun()

    song_id = st.session_state.get("song_id")
    if not song_id:
        st.error("No song selected.")
    else:
        with st.spinner("Loading song..."):
            sws = song_service.get_song(song_id)
        if not sws:
            st.error("Song not found.")
        else:
            st.header(f'"{sws.song.title}" — {sws.song.artist_credit}')
            s = sws.stats
            if s:
                peak = f"#{s.peak_position}" if s.peak_position else "—"
                debut_pos = f"#{s.debut_position}" if s.debut_position else "—"
                debut_dt = s.debut_date.strftime("%b %d, %Y") if s.debut_date else "—"
                last_dt = s.last_date.strftime("%b %d, %Y") if s.last_date else "—"

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Peak", peak)
                c2.metric("Weeks on Chart", s.total_weeks)
                c3.metric("Weeks at #1", s.weeks_at_number_one)
                c4.metric("Weeks at Peak", s.weeks_at_peak)

                c1, c2, c3 = st.columns(3)
                c1.metric("Debut Position", debut_pos)
                c2.metric("Debut", debut_dt)
                c3.metric("Last Charted", last_dt)

            # Chart history table (always visible, primary data view)
            with st.spinner("Loading chart history..."):
                chart_run = song_service.get_chart_run(song_id)
            if chart_run:
                st.markdown("---")
                st.subheader("Chart History")
                history_df = _build_chart_history_df(chart_run)
                st.dataframe(history_df, hide_index=True, use_container_width=True,
                             height=600)

                # Chart visualization behind toggle
                if st.checkbox("Show chart visualization", key="song_show_chart"):
                    chart = _build_chart_run_chart(chart_run, "hot-100")
                    st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No chart run data available.")

            # Artist links
            if sws.artists:
                st.markdown("---")
                st.subheader("Artists")
                cols = st.columns(min(len(sws.artists), 6))
                for i, artist in enumerate(sws.artists):
                    with cols[i % len(cols)]:
                        if st.button(artist.name, key=f"song_artist_{artist.id}"):
                            st.session_state["prev_page"] = "Song Detail"
                            _nav("Artist Detail", artist_id=artist.id)
                            st.rerun()


# ===================================================================
# PAGE: Album Detail
# ===================================================================
elif page == "Album Detail":
    if st.button("< Back"):
        _back()
        st.rerun()

    album_id = st.session_state.get("album_id")
    if not album_id:
        st.error("No album selected.")
    else:
        with st.spinner("Loading album..."):
            aws = album_service.get_album(album_id)
        if not aws:
            st.error("Album not found.")
        else:
            st.header(f'"{aws.album.title}" — {aws.album.artist_credit}')
            s = aws.stats
            if s:
                peak = f"#{s.peak_position}" if s.peak_position else "—"
                debut_pos = f"#{s.debut_position}" if s.debut_position else "—"
                debut_dt = s.debut_date.strftime("%b %d, %Y") if s.debut_date else "—"
                last_dt = s.last_date.strftime("%b %d, %Y") if s.last_date else "—"

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Peak", peak)
                c2.metric("Weeks on Chart", s.total_weeks)
                c3.metric("Weeks at #1", s.weeks_at_number_one)
                c4.metric("Weeks at Peak", s.weeks_at_peak)

                c1, c2, c3 = st.columns(3)
                c1.metric("Debut Position", debut_pos)
                c2.metric("Debut", debut_dt)
                c3.metric("Last Charted", last_dt)

            with st.spinner("Loading chart history..."):
                chart_run = album_service.get_chart_run(album_id)
            if chart_run:
                st.markdown("---")
                st.subheader("Chart History")
                history_df = _build_chart_history_df(chart_run)
                st.dataframe(history_df, hide_index=True, use_container_width=True,
                             height=600)

                if st.checkbox("Show chart visualization", key="album_show_chart"):
                    chart = _build_chart_run_chart(chart_run, "billboard-200")
                    st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No chart run data available.")

            # Artist links
            if aws.artists:
                st.markdown("---")
                st.subheader("Artists")
                cols = st.columns(min(len(aws.artists), 6))
                for i, artist in enumerate(aws.artists):
                    with cols[i % len(cols)]:
                        if st.button(artist.name, key=f"album_artist_{artist.id}"):
                            st.session_state["prev_page"] = "Album Detail"
                            _nav("Artist Detail", artist_id=artist.id)
                            st.rerun()


# ===================================================================
# PAGE: Records
# ===================================================================
elif page == "Records":
    st.header("Records")

    # Drill-down mapping: record_type -> (func, value_label, needs_chart_date)
    DRILLDOWN_MAP = {
        "Most #1 Songs (by Artist)": (records_service.drilldown_number_one_songs, "Wks #1", False),
        "Most #1 Albums (by Artist)": (records_service.drilldown_number_one_albums, "Wks #1", False),
        "Most Entries by Artist": (records_service.drilldown_artist_entries, "Total Wks", False),
        "Most Simultaneous Entries": (records_service.drilldown_simultaneous_entries, "Position", True),
    }

    col1, col2 = st.columns([2, 1])
    with col1:
        record_type = st.selectbox("Record Type", [
            "Custom Query",
            "Most Weeks at #1",
            "Longest Chart Runs",
            "Most #1 Songs (by Artist)",
            "Most #1 Albums (by Artist)",
            "Most Entries by Artist",
            "Most Simultaneous Entries",
            "Biggest Debuts",
            "Fastest to #1",
        ], key="rec_type")
    with col2:
        rec_chart = st.radio(
            "Chart", ["hot-100", "billboard-200"],
            format_func=lambda x: "Hot 100" if x == "hot-100" else "Billboard 200",
            horizontal=True, key="rec_chart",
        )

    # Clear drill-down state when record type or chart changes
    _dd_key = f"{record_type}|{rec_chart}"
    if st.session_state.get("_dd_context") != _dd_key:
        st.session_state["_dd_context"] = _dd_key
        st.session_state.pop("records_drilldown_artist_id", None)
        st.session_state.pop("records_drilldown_chart_date", None)
        st.session_state.pop("_dd_last_sel_idx", None)

    results = None
    val_label = "Value"

    if record_type == "Custom Query":
        max_pos = 100 if rec_chart == "hot-100" else 200

        RANK_BY_OPTIONS = {
            "Weeks at Position X": "weeks_at_position",
            "Weeks in Top N": "weeks_in_top_n",
            "Total Weeks on Chart": "total_weeks",
            "Weeks at #1": "weeks_at_number_one",
        }
        rank_label = st.selectbox("Rank by", list(RANK_BY_OPTIONS.keys()), key="cq_rank_by")
        rank_by = RANK_BY_OPTIONS[rank_label]

        rank_by_param = 1
        if rank_by == "weeks_at_position":
            rank_by_param = st.number_input("Position", min_value=1, max_value=max_pos, value=1, key="cq_pos")
            val_label = f"Wks at #{rank_by_param}"
        elif rank_by == "weeks_in_top_n":
            rank_by_param = st.number_input("N", min_value=1, max_value=max_pos, value=10, key="cq_topn")
            val_label = f"Wks in Top {rank_by_param}"
        elif rank_by == "total_weeks":
            val_label = "Total Wks"
        else:
            val_label = "Wks #1"

        with st.expander("Filters (optional)"):
            artist_filter = st.text_input("Artists (comma-separated)", key="cq_artist", placeholder="e.g. Drake, Taylor Swift")

            peak_range = st.slider(
                "Peak position range (best to worst)",
                min_value=1, max_value=max_pos, value=(1, max_pos),
                key="cq_peak_range",
            )
            peak_min = peak_range[0] if peak_range != (1, max_pos) else None
            peak_max = peak_range[1] if peak_range != (1, max_pos) else None

            weeks_min = st.number_input("Min total weeks on chart", min_value=1, value=None, key="cq_weeks_min", placeholder="any")

            debut_range = st.slider(
                "Debut position range (best to worst)",
                min_value=1, max_value=max_pos, value=(1, max_pos),
                key="cq_debut_range",
            )
            debut_pos_min = debut_range[0] if debut_range != (1, max_pos) else None
            debut_pos_max = debut_range[1] if debut_range != (1, max_pos) else None

        with st.spinner("Running query..."):
            results = records_service.custom_query(
                rank_by=rank_by,
                rank_by_param=rank_by_param,
                chart=rec_chart,
                limit=10000,
                peak_min=peak_min,
                peak_max=peak_max,
                weeks_min=weeks_min,
                debut_pos_min=debut_pos_min,
                debut_pos_max=debut_pos_max,
                artist_names=[n.strip() for n in artist_filter.split(",") if n.strip()] or None,
            )
    else:
        RECORD_FUNCS = {
            "Most Weeks at #1": records_service.most_weeks_at_number_one,
            "Longest Chart Runs": records_service.longest_chart_runs,
            "Most #1 Songs (by Artist)": records_service.most_number_one_songs_by_artist,
            "Most #1 Albums (by Artist)": records_service.most_number_one_albums_by_artist,
            "Most Entries by Artist": records_service.most_entries_by_artist,
            "Most Simultaneous Entries": records_service.most_simultaneous_entries,
            "Biggest Debuts": records_service.biggest_debuts,
            "Fastest to #1": records_service.fastest_to_number_one,
        }

        func = RECORD_FUNCS[record_type]
        with st.spinner("Loading records..."):
            results = func(chart=rec_chart, limit=10000)

        value_labels = {
            "Most Weeks at #1": "Wks #1",
            "Longest Chart Runs": "Total Wks",
            "Most #1 Songs (by Artist)": "#1 Songs",
            "Most #1 Albums (by Artist)": "#1 Albums",
            "Most Entries by Artist": "Entries",
            "Most Simultaneous Entries": "Simult.",
            "Biggest Debuts": "Debut Pos",
            "Fastest to #1": "Wks to #1",
        }
        val_label = value_labels[record_type]

    if not results:
        if record_type == "Most Simultaneous Entries" and rec_chart == "billboard-200":
            st.info("This record is only tracked for the Hot 100.")
        elif record_type == "Most #1 Songs (by Artist)" and rec_chart == "billboard-200":
            st.info("This record is only available for the Hot 100.")
        elif record_type == "Most #1 Albums (by Artist)" and rec_chart == "hot-100":
            st.info("This record is only available for the Billboard 200.")
        else:
            st.info("No records found.")
    else:
        has_dates = any(r.chart_date is not None for r in results)
        rows = []
        for r in results:
            row = {
                "#": r.rank,
                "Title / Artist": r.title,
                "Artist": r.artist_credit,
                val_label: r.value,
                "_song_id": r.song_id,
                "_album_id": r.album_id,
                "_artist_id": r.artist_id,
                "_chart_date": r.chart_date,
            }
            if has_dates:
                row["Week"] = r.chart_date.strftime("%b %d, %Y") if r.chart_date else "—"
            rows.append(row)
        df = pd.DataFrame(rows)
        display_cols = ["#", "Title / Artist", "Artist", val_label]
        if has_dates:
            display_cols.append("Week")

        has_drilldown = record_type in DRILLDOWN_MAP

        event = st.dataframe(
            df[display_cols],
            hide_index=True, use_container_width=True,
            on_select="rerun", selection_mode="single-row",
            key="records_table",
        )
        if event.selection.rows:
            idx = event.selection.rows[0]
            row = df.iloc[idx]

            # Artist-level records with drill-down: expand inline sub-table
            if has_drilldown and row["_artist_id"] is not None and not pd.isna(row["_artist_id"]):
                clicked_id = int(row["_artist_id"])
                # Only process if this is a genuinely new selection
                if st.session_state.get("_dd_last_sel_idx") != idx:
                    st.session_state["_dd_last_sel_idx"] = idx
                    st.session_state["records_drilldown_artist_id"] = clicked_id
                    if has_dates and row["_chart_date"] is not None:
                        st.session_state["records_drilldown_chart_date"] = row["_chart_date"]
                    else:
                        st.session_state.pop("records_drilldown_chart_date", None)
            else:
                # Song/album rows or artist records without drill-down: navigate
                st.session_state["prev_page"] = "Records"
                if row["_song_id"] is not None and not pd.isna(row["_song_id"]):
                    _nav("Song Detail", song_id=int(row["_song_id"]))
                elif row["_album_id"] is not None and not pd.isna(row["_album_id"]):
                    _nav("Album Detail", album_id=int(row["_album_id"]))
                elif row["_artist_id"] is not None and not pd.isna(row["_artist_id"]):
                    _nav("Artist Detail", artist_id=int(row["_artist_id"]))
                st.rerun()
        else:
            # Selection cleared (user deselected) — collapse drill-down
            if st.session_state.get("_dd_last_sel_idx") is not None:
                st.session_state.pop("_dd_last_sel_idx", None)
                st.session_state.pop("records_drilldown_artist_id", None)
                st.session_state.pop("records_drilldown_chart_date", None)

        # --- Inline drill-down sub-table ---
        dd_artist_id = st.session_state.get("records_drilldown_artist_id")
        if has_drilldown and dd_artist_id is not None:
            dd_func, dd_val_label, needs_date = DRILLDOWN_MAP[record_type]

            # Find artist name from main results
            dd_name = None
            for r in results:
                if r.artist_id == dd_artist_id:
                    dd_name = r.title
                    break
            dd_name = dd_name or "Artist"

            st.markdown("---")
            col_hdr, col_close = st.columns([4, 1])
            with col_hdr:
                st.subheader(dd_name)
            with col_close:
                if st.button("Close", key="dd_close"):
                    st.session_state.pop("records_drilldown_artist_id", None)
                    st.session_state.pop("records_drilldown_chart_date", None)
                    st.rerun()

            # Call drill-down function
            kwargs = {"artist_id": dd_artist_id, "chart": rec_chart}
            if needs_date:
                kwargs["chart_date"] = st.session_state.get("records_drilldown_chart_date")
            dd_results = dd_func(**kwargs)

            if not dd_results:
                st.info("No items found.")
            else:
                dd_rows = []
                for r in dd_results:
                    dd_rows.append({
                        "#": r.rank,
                        "Title": r.title,
                        "Artist": r.artist_credit,
                        dd_val_label: r.value,
                        "_song_id": r.song_id,
                        "_album_id": r.album_id,
                    })
                dd_df = pd.DataFrame(dd_rows)
                dd_event = st.dataframe(
                    dd_df[["#", "Title", "Artist", dd_val_label]],
                    hide_index=True, use_container_width=True,
                    on_select="rerun", selection_mode="single-row",
                    key="dd_table",
                )
                if dd_event.selection.rows:
                    dd_idx = dd_event.selection.rows[0]
                    dd_row = dd_df.iloc[dd_idx]
                    st.session_state["prev_page"] = "Records"
                    if dd_row["_song_id"] is not None and not pd.isna(dd_row["_song_id"]):
                        _nav("Song Detail", song_id=int(dd_row["_song_id"]))
                    elif dd_row["_album_id"] is not None and not pd.isna(dd_row["_album_id"]):
                        _nav("Album Detail", album_id=int(dd_row["_album_id"]))
                    st.rerun()


# ===================================================================
# PAGE: Data Status
# ===================================================================
elif page == "Data Status":
    st.header("Data Status")

    with st.spinner("Loading data status..."):
        summary = data_status_service.get_data_summary()
    latest = summary.get("latest_dates", {})

    hot100_latest = latest.get("hot-100", "—")
    b200_latest = latest.get("billboard-200", "—")
    st.caption(f"Last Updated: {hot100_latest} (Hot 100) / {b200_latest} (Billboard 200)")

    # Single stats table
    counts = summary.get("counts", {})
    stats_rows = [{"Metric": table, "Count": f"{cnt:,}"} for table, cnt in counts.items()]
    stats_df = pd.DataFrame(stats_rows)
    st.dataframe(stats_df, hide_index=True, use_container_width=True)

    st.markdown("---")
    if st.button("Update Now", type="primary"):
        conn = get_conn()
        try:
            with st.spinner("Repairing data gaps..."):
                repair_result = repair_gaps(conn)
            with st.spinner("Fetching new chart data..."):
                update_result = update_charts(conn)
            st.success(
                f"Update complete. "
                f"Hot 100: {update_result['hot100_loaded']} new weeks. "
                f"B200: {update_result['b200_loaded']} new weeks. "
                f"Repairs: {repair_result}"
            )
            st.rerun()
        except Exception as e:
            st.error(f"Update failed: {e}")
        finally:
            put_conn(conn)
