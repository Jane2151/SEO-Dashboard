"""Keyword Performance: target keywords we're chasing, plus every actual
search query GSC reports, both computed live from the daily-synced data.

Target keywords (target_keywords table) are a manually-curated watchlist —
distinct from gsc_daily_query, which is whatever people actually searched.
"""

import streamlit as st

from data_processing import metrics
from database import gsc_daily_repository, target_keyword_repository
from database.db_setup import initialize_database
from utils.date_ranges import select_range

st.set_page_config(page_title="Keyword Performance", layout="wide")
initialize_database()
st.title("Keyword Performance")

latest_synced_date = gsc_daily_repository.get_latest_synced_date()
if latest_synced_date is None:
    st.info("No synced data yet. Go to the main page and click 'Sync GSC Data' to get started.")
    st.stop()

earliest_synced_date = gsc_daily_repository.get_earliest_synced_date()
latest_complete_date = gsc_daily_repository.get_latest_complete_date()
range_start, range_end = select_range(latest_synced_date, earliest_synced_date, key_prefix="keyword_perf", latest_complete_date=latest_complete_date)

if range_start > range_end:
    st.error("Start date must be before end date.")
    st.stop()

st.caption(f"Showing **{range_start} to {range_end}**.")

st.subheader("Target Keywords")
st.caption("Keywords we intentionally want to rank for — chosen by hand, not pulled from GSC.")

with st.expander("Manage target keywords"):
    with st.form("add_target_keyword_form", clear_on_submit=True):
        new_keyword = st.text_input("Add a target keyword")
        add_submitted = st.form_submit_button("Add")
    if add_submitted:
        if new_keyword.strip():
            target_keyword_repository.add_target_keyword(new_keyword)
            st.rerun()
        else:
            st.error("Enter a keyword first.")

    target_keywords_df = target_keyword_repository.list_target_keywords()
    if not target_keywords_df.empty:
        remove_id = st.selectbox(
            "Remove a target keyword",
            options=[None, *target_keywords_df["id"].tolist()],
            format_func=lambda x: "Select a keyword..." if x is None else target_keywords_df.loc[target_keywords_df["id"] == x, "keyword"].iloc[0],
        )
        if remove_id is not None and st.button("Remove selected keyword"):
            target_keyword_repository.delete_target_keyword(remove_id)
            st.rerun()

target_keywords_df = target_keyword_repository.list_target_keywords()

if target_keywords_df.empty:
    st.info("No target keywords yet. Add one above to start tracking it.")
else:
    # Color each card by trend so improving/declining keywords are easy to
    # spot at a glance instead of blending into a wall of identical boxes.
    # Streamlit exposes a container's `key` as a `st-key-<key>` CSS class, so
    # baking the trend into the key lets one [class*=...] rule per trend
    # color every card of that trend, even though each key is unique.
    # Backgrounds use a low-opacity rgba tint (not a solid light color) so
    # they wash over the theme's own background instead of assuming light
    # mode — a solid light pastel would swallow light-on-dark text in dark
    # mode. Text color is left untouched so it always matches the theme.
    TREND_STYLES = {
        "improving": ("rgba(46, 125, 50, 0.25)", "#4caf50"),
        "declining": ("rgba(198, 40, 40, 0.25)", "#ef5350"),
        "stable": ("rgba(117, 117, 117, 0.25)", "#9e9e9e"),
        "not_enough_history": ("rgba(249, 168, 37, 0.25)", "#ffca28"),
        "no_data": ("rgba(117, 117, 117, 0.15)", "#757575"),
    }
    style_rules = "\n".join(
        f'[class*="st-key-tk_card_{trend}"] {{ background-color: {bg}; border-left: 5px solid {border}; '
        f"border-radius: 0.5rem; padding: 0.75rem 1rem; }}"
        for trend, (bg, border) in TREND_STYLES.items()
    )
    st.markdown(f"<style>{style_rules}</style>", unsafe_allow_html=True)

    previous_start, previous_end = metrics.previous_equivalent_period(range_start, range_end)
    card_cols = st.columns(min(len(target_keywords_df), 3))

    for position, keyword_row in enumerate(target_keywords_df.itertuples(index=False)):
        stats = gsc_daily_repository.get_query_stats(keyword_row.keyword, range_start, range_end)
        previous_stats = gsc_daily_repository.get_query_stats(keyword_row.keyword, previous_start, previous_end)

        if stats["impressions"] == 0:
            trend_label = "No data"
        elif previous_stats["impressions"] == 0:
            trend_label = "Not enough history"
        else:
            change = metrics.position_change(previous_stats["position"], stats["position"])
            if change > 0:
                trend_label = "Improving"
            elif change < 0:
                trend_label = "Declining"
            else:
                trend_label = "Stable"

        card_key = f"tk_card_{trend_label.lower().replace(' ', '_')}_{position}"
        with card_cols[position % len(card_cols)].container(border=True, key=card_key):
            # Keyword name only, no metrics or caption — the card's color
            # already signals the trend on its own.
            st.markdown(f"**{keyword_row.keyword}**")

st.divider()
st.subheader("Current User Search Queries")
st.caption("What people actually searched for on Google when the site appeared — from the GSC query dimension.")

query_breakdown = gsc_daily_repository.get_query_breakdown(range_start, range_end, limit=5000)

if query_breakdown.empty:
    st.info("No query-level data for this range.")
else:
    search_col, sort_col = st.columns([2, 1])
    search_term = search_col.text_input("Search queries")
    sort_option = sort_col.selectbox("Sort by", ["Impressions", "Clicks", "CTR", "Position (best first)"])

    filtered_df = query_breakdown
    if search_term:
        filtered_df = filtered_df[filtered_df["query"].str.contains(search_term, case=False, na=False)]

    if sort_option == "Impressions":
        filtered_df = filtered_df.sort_values("impressions", ascending=False)
    elif sort_option == "Clicks":
        filtered_df = filtered_df.sort_values("clicks", ascending=False)
    elif sort_option == "CTR":
        filtered_df = filtered_df.sort_values("ctr", ascending=False)
    else:
        filtered_df = filtered_df.sort_values("position", ascending=True)

    display_df = filtered_df.rename(
        columns={"query": "Search Query", "clicks": "Clicks", "impressions": "Impressions", "ctr": "CTR", "position": "Avg Position"}
    ).copy()
    display_df["CTR"] = (display_df["CTR"] * 100).round(2)
    display_df["Avg Position"] = display_df["Avg Position"].round(1)

    # Sized to fit every row so the table itself never needs an internal
    # scrollbar — 35px/row plus the header, matching st.dataframe's own
    # row/header sizing, rather than the default fixed-height scroll box.
    table_height = 38 + 35 * len(display_df) + 3

    # Rows whose query text is exactly one of the target keywords get the
    # same yellow used for the "not enough history" card, so a watched
    # keyword's real query row is easy to spot in the full table below.
    target_keyword_texts = {kw.strip().lower() for kw in target_keywords_df["keyword"]} if not target_keywords_df.empty else set()

    def _highlight_target_keyword_rows(row):
        is_target = row["Search Query"].strip().lower() in target_keyword_texts
        style = "background-color: rgba(249, 168, 37, 0.35)" if is_target else ""
        return [style] * len(row)

    # Styler bypasses st.dataframe's own numeric formatting, so without an
    # explicit format Avg Position renders as a raw float (e.g. "12.000000")
    # instead of the "12.0" the plain DataFrame showed before.
    styled_display_df = display_df.style.apply(_highlight_target_keyword_rows, axis=1).format({"Avg Position": "{:.1f}"})

    st.dataframe(
        styled_display_df,
        width="stretch",
        hide_index=True,
        height=table_height,
        column_config={"CTR": st.column_config.NumberColumn("CTR", format="%.2f%%")},
    )
