"""Page Performance: page-level tracking, independent of before/after pairs.

Pick any page with saved Search Console page-level data (dimensions=["page"])
and see its current metrics plus its full history across every fetched
period, with SEO change log entries for that page marked on the trend chart.
Unlike Before/After Analysis, this never depends on having a before-and-after
dataset pair — it just shows whatever history exists for the selected page.
"""

import streamlit as st

from charts import plotly_charts
from data_processing.comparison import normalize_page_url
from database import change_log_repository, gsc_repository
from database.db_setup import initialize_database

st.set_page_config(page_title="Page Performance", layout="wide")
initialize_database()
st.title("Page Performance")

known_pages = gsc_repository.list_known_pages()

if not known_pages:
    st.info(
        "No page-level data yet. Fetch a period through the Search Console API "
        "on the main page — CSV uploads don't include page-level data."
    )
    st.stop()

selected_page = st.selectbox("Page URL", known_pages)

history = gsc_repository.get_page_history(selected_page)

if history.empty:
    st.info("No saved data for this page yet.")
    st.stop()

current = history.iloc[-1]
st.caption(f"Current period: **{current['label']}** ({current['period_start']} to {current['period_end']})")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Clicks", f"{int(current['clicks']):,}")
col2.metric("Impressions", f"{int(current['impressions']):,}")
col3.metric("CTR", f"{current['ctr'] * 100:.2f}%")
col4.metric("Average Position", f"{current['position']:.1f}", help="Lower is better.")

st.subheader("Historical Trend")

if len(history) < 2:
    st.info("Only one period of data exists for this page so far. Fetch more periods to see a trend.")
else:
    # SEO change log entries logged against this specific page, for markers.
    all_changes = change_log_repository.list_changes()
    normalized_target = normalize_page_url(selected_page)
    matching_changes = all_changes[all_changes["page_url"].apply(normalize_page_url) == normalized_target]
    markers = list(zip(matching_changes["change_date"], matching_changes["category"])) if not matching_changes.empty else []

    impressions_tab, clicks_tab, position_tab = st.tabs(["Impressions", "Clicks", "Average Position"])

    with impressions_tab:
        fig = plotly_charts.trend_line_chart_with_markers(
            history["period_end"], history["impressions"], "Impressions Over Time", "Impressions", markers=markers
        )
        st.plotly_chart(fig, width="stretch")

    with clicks_tab:
        fig = plotly_charts.trend_line_chart_with_markers(
            history["period_end"], history["clicks"], "Clicks Over Time", "Clicks", markers=markers
        )
        st.plotly_chart(fig, width="stretch")

    with position_tab:
        fig = plotly_charts.trend_line_chart_with_markers(
            history["period_end"], history["position"], "Average Position Over Time", "Position",
            markers=markers, invert_y=True,
        )
        st.plotly_chart(fig, width="stretch")
        st.caption("Axis is inverted so an upward line always means better rankings.")

    if markers:
        entry_word = "entry" if len(markers) == 1 else "entries"
        st.caption(f"Dashed lines mark {len(markers)} SEO change log {entry_word} logged against this page.")
