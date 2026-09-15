"""SEO Overview: current performance + trends, from the daily-synced data.

Built around "SEO performance from this date to this date," not "which saved
dataset should I open" — any date range is computed live from gsc_daily_*
via SUM/SUM CTR and impression-weighted position (data_processing.metrics).
Period comparison exists, but is opt-in, not the default view.
"""

import streamlit as st

from charts import plotly_charts
from data_processing import metrics
from database import change_log_repository, gsc_daily_repository, target_keyword_repository
from database.db_setup import initialize_database
from utils.chart_style import inject_chart_transition_css
from utils.date_ranges import select_range
from utils.text_style import styled_caption

st.set_page_config(page_title="SEO Overview", layout="wide")
initialize_database()
inject_chart_transition_css()
st.title("SEO Overview")

latest_synced_date = gsc_daily_repository.get_latest_synced_date()
if latest_synced_date is None:
    st.info("No synced data yet. Go to the main page and click 'Sync GSC Data' to get started.")
    st.stop()

earliest_synced_date = gsc_daily_repository.get_earliest_synced_date()
latest_complete_date = gsc_daily_repository.get_latest_complete_date()

range_start, range_end = select_range(latest_synced_date, earliest_synced_date, key_prefix="overview", latest_complete_date=latest_complete_date)

if range_start > range_end:
    st.error("Start date must be before end date.")
    st.stop()

styled_caption(f"Showing {range_start} to {range_end} — synced data available from {earliest_synced_date} to {latest_synced_date}.")

days_stale = metrics.days_since(latest_synced_date)
if days_stale > 3:
    st.warning(f"Last synced data is from {latest_synced_date} ({days_stale} days ago). Sync again on the main page for fresher numbers.")

current_daily = gsc_daily_repository.get_daily_overall_range(range_start, range_end)

if current_daily.empty:
    st.info("No data for this date range yet.")
    st.stop()

current_summary = {
    "clicks": metrics.total_clicks(current_daily),
    "impressions": metrics.total_impressions(current_daily),
    "ctr": metrics.average_ctr(current_daily),
    "position": metrics.average_position(current_daily),
}

compare_enabled = st.checkbox("Compare with previous period")

previous_summary = None
if compare_enabled:
    previous_start, previous_end = metrics.previous_equivalent_period(range_start, range_end)
    previous_daily = gsc_daily_repository.get_daily_overall_range(previous_start, previous_end)
    if previous_daily.empty:
        st.info(f"No data available for the previous period ({previous_start} to {previous_end}) to compare against.")
    else:
        previous_summary = {
            "clicks": metrics.total_clicks(previous_daily),
            "impressions": metrics.total_impressions(previous_daily),
            "ctr": metrics.average_ctr(previous_daily),
            "position": metrics.average_position(previous_daily),
        }
        st.caption(f"Comparing against **{previous_start} to {previous_end}**.")

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Total Clicks",
    f"{current_summary['clicks']:,}",
    metrics.format_before_after_delta(previous_summary["clicks"], current_summary["clicks"]) if previous_summary else None,
)
col2.metric(
    "Total Impressions",
    f"{current_summary['impressions']:,}",
    metrics.format_before_after_delta(previous_summary["impressions"], current_summary["impressions"]) if previous_summary else None,
)
col3.metric(
    "Average CTR",
    f"{current_summary['ctr'] * 100:.2f}%",
    metrics.format_ctr_delta(previous_summary["ctr"], current_summary["ctr"]) if previous_summary else None,
)
col4.metric(
    "Average Position",
    f"{current_summary['position']:.1f}",
    metrics.format_before_after_delta(previous_summary["position"], current_summary["position"], lower_is_better=True) if previous_summary else None,
    help="Lower is better. A positive delta here means position improved.",
)

st.subheader("Trends")
st.caption(
    "Markers show SEO changes recorded in the Change Log — hover one for details. "
    "This is a visual reference only: it does not mean the change caused what happened afterward."
)

changes_in_range = change_log_repository.get_changes_in_range(range_start, range_end)
grouped_changes = []
if not changes_in_range.empty:
    for change_date, group in changes_in_range.groupby("change_date"):
        entries = [{"category": row.category, "description": row.description} for row in group.itertuples(index=False)]
        grouped_changes.append((change_date, entries))

# Gridlines are drawn with an explicit color (needed to make the two
# y-axes' gridlines share the same rows — see clicks_impressions_dual_axis_chart),
# so they can't rely on Streamlit's own theme CSS to stay visible. Reading
# the active theme here picks a matching tint instead of a fixed color.
is_dark_theme = st.context.theme.type == "dark"

shared_x_range = [current_daily["date"].min(), current_daily["date"].max()]

clicks_impressions_tab, position_tab = st.tabs(["Clicks & Impressions", "Average Position"])

with clicks_impressions_tab:
    if "show_clicks_cb" not in st.session_state:
        st.session_state.show_clicks_cb = True
        st.session_state.show_impressions_cb = False
    if "compare_mode_toggle" not in st.session_state:
        st.session_state.compare_mode_toggle = False

    # Session state for a keyed widget already reflects its new value by
    # the time the script reruns (before that widget's own line executes),
    # so this read of compare_mode_toggle picks up a just-flipped toggle in
    # the same rerun that draws the checkboxes below — forcing both to
    # appear checked immediately rather than one rerun later.
    compare_mode = st.session_state.compare_mode_toggle
    if compare_mode:
        st.session_state.show_clicks_cb = True
        st.session_state.show_impressions_cb = True
    elif st.session_state.show_clicks_cb and st.session_state.show_impressions_cb:
        # Both are only ever True together as a leftover from Compare mode
        # (the checkboxes' own on_change callbacks never allow that
        # otherwise) — collapse back to a single selection now that Compare
        # is off, so the checked box always matches the chart being shown.
        st.session_state.show_impressions_cb = False

    def _uncheck_impressions():
        if st.session_state.show_clicks_cb:
            st.session_state.show_impressions_cb = False

    def _uncheck_clicks():
        if st.session_state.show_impressions_cb:
            st.session_state.show_clicks_cb = False

    checkbox_col1, checkbox_col2, toggle_col = st.columns([1, 1, 1])
    show_clicks = checkbox_col1.checkbox(
        "Clicks", key="show_clicks_cb", on_change=_uncheck_impressions, disabled=compare_mode
    )
    show_impressions = checkbox_col2.checkbox(
        "Impressions", key="show_impressions_cb", on_change=_uncheck_clicks, disabled=compare_mode
    )
    toggle_col.toggle("Compare", key="compare_mode_toggle")

    if compare_mode:
        st.plotly_chart(
            plotly_charts.clicks_impressions_dual_axis_chart(
                current_daily["date"],
                current_daily["clicks"],
                current_daily["impressions"],
                changes=grouped_changes,
                x_range=shared_x_range,
                dark_mode=is_dark_theme,
            ),
            width="stretch",
        )
    elif show_clicks:
        st.plotly_chart(
            plotly_charts.trend_line_chart_with_change_markers(
                current_daily["date"],
                current_daily["clicks"],
                "Clicks Over Time",
                "Clicks",
                grouped_changes,
                x_range=shared_x_range,
                dark_mode=is_dark_theme,
                line_color=plotly_charts.CLICKS_COLOR,
            ),
            width="stretch",
        )
    elif show_impressions:
        st.plotly_chart(
            plotly_charts.trend_line_chart_with_change_markers(
                current_daily["date"],
                current_daily["impressions"],
                "Impressions Over Time",
                "Impressions",
                grouped_changes,
                x_range=shared_x_range,
                dark_mode=is_dark_theme,
                line_color=plotly_charts.CLICKS_COLOR,
            ),
            width="stretch",
        )
    else:
        st.info("Select Clicks or Impressions to display a chart.")

with position_tab:
    target_keywords_df = target_keyword_repository.list_target_keywords()
    keyword_series = []
    for row in target_keywords_df.itertuples(index=False):
        keyword_daily = gsc_daily_repository.get_query_daily_position(row.keyword, range_start, range_end)
        if not keyword_daily.empty:
            keyword_series.append({"label": row.keyword, "x": keyword_daily["date"], "y": keyword_daily["position"]})

    # The chart's categorical palette reserves one slot for the sitewide
    # line, leaving 7 for keyword lines — past that, more lines would stop
    # being visually distinguishable rather than just crowding the legend.
    max_keyword_lines = 7
    if len(keyword_series) > max_keyword_lines:
        st.caption(
            f"Showing {max_keyword_lines} of {len(keyword_series)} target keywords on the chart below — "
            "too many to stay readable as separate lines."
        )
        keyword_series = keyword_series[:max_keyword_lines]

    if keyword_series:
        # The chart drops its own in-figure title when keyword lines are
        # shown (it would fight the legend for the same space above the
        # plot) — this heading replaces it.
        st.markdown("**Average Position Over Time**")

    st.plotly_chart(
        plotly_charts.trend_line_chart_with_change_markers(
            current_daily["date"],
            current_daily["position"],
            "Average Position Over Time",
            "Position",
            grouped_changes,
            invert_y=True,
            dark_mode=is_dark_theme,
            keyword_series=keyword_series,
        ),
        width="stretch",
    )
    st.caption("Axis is inverted so an upward line always means better rankings.")
    if keyword_series:
        st.caption("Each colored line is one target keyword's own position — compare it against the change markers to see whether a specific action moved that keyword.")

st.subheader("Breakdowns")

page_tab, device_tab, country_tab = st.tabs(["Top Pages", "Devices", "Countries"])

with page_tab:
    page_breakdown = gsc_daily_repository.get_page_breakdown(range_start, range_end)
    if page_breakdown.empty:
        st.info("No page-level data for this range.")
    else:
        st.dataframe(page_breakdown, width="stretch", hide_index=True)

with device_tab:
    device_breakdown = gsc_daily_repository.get_device_breakdown(range_start, range_end)
    if device_breakdown.empty:
        st.info("No device-level data for this range.")
    else:
        st.dataframe(device_breakdown, width="stretch", hide_index=True)

with country_tab:
    country_breakdown = gsc_daily_repository.get_country_breakdown(range_start, range_end)
    if country_breakdown.empty:
        st.info("No country-level data for this range.")
    else:
        st.dataframe(country_breakdown, width="stretch", hide_index=True)
