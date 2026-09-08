"""Before vs After Analysis: compare GSC performance around one change-log entry.

Before/after datasets are auto-picked as whichever uploaded periods sit
immediately before and after the selected change's date.

Note: this page reports correlation, not causation — wording is deliberately
phrased as "performance improved following this optimization," never as the
change having caused the result.
"""

import pandas as pd
import streamlit as st

from charts import plotly_charts
from data_processing import comparison, metrics
from database import change_log_repository, gsc_repository
from database.db_setup import initialize_database

st.set_page_config(page_title="Before vs After Analysis", layout="wide")
initialize_database()
st.title("Before vs After Analysis")

changes_df = change_log_repository.list_changes()
if changes_df.empty:
    st.info("No SEO changes recorded yet. Add one on the SEO Change Log page.")
    st.stop()

changes_df["option_label"] = changes_df.apply(
    lambda row: f"{row['change_date']} — {row['category']} — {row['page_url']}", axis=1
)
selected_label = st.selectbox("Select an SEO change", changes_df["option_label"])
selected_change = changes_df[changes_df["option_label"] == selected_label].iloc[0]

st.write(f"**Description:** {selected_change['description'] or '—'}")
st.write(f"**Target keyword:** {selected_change['target_keyword'] or '—'}")
st.write(f"**Notes:** {selected_change['notes'] or '—'}")

change_date = pd.to_datetime(selected_change["change_date"]).date()
before_meta, after_meta = gsc_repository.get_dataset_before_and_after(change_date)

if before_meta is None or after_meta is None:
    st.warning(
        "Not enough data to compare yet. Upload a GSC dataset covering a "
        "period before this change's date and one covering a period after it."
    )
    st.stop()

st.caption(
    f"Before: **{before_meta['label']}** ({before_meta['period_start'].date()} to {before_meta['period_end'].date()}) "
    f"vs After: **{after_meta['label']}** ({after_meta['period_start'].date()} to {after_meta['period_end'].date()})"
)

before_df = gsc_repository.get_dataset_rows(int(before_meta["id"]))
after_df = gsc_repository.get_dataset_rows(int(after_meta["id"]))

summary = comparison.build_before_after_summary(
    before_meta,
    after_meta,
    before_df,
    after_df,
    target_keyword=selected_change["target_keyword"],
)

st.subheader("Overall Performance")
if summary["before"]["is_approximate"] or summary["after"]["is_approximate"]:
    st.caption(
        "⚠️ One or both periods were uploaded as a CSV, which has no site-wide "
        "total separate from its query rows (Search Console omits some low-volume "
        "queries from that breakdown, so totals below may understate the true numbers)."
    )

# (label, before value, after value, lower numbers are better, display format)
metric_definitions = [
    ("Clicks", summary["before"]["clicks"], summary["after"]["clicks"], False, "{:,.0f}"),
    ("Impressions", summary["before"]["impressions"], summary["after"]["impressions"], False, "{:,.0f}"),
    ("CTR (%)", summary["before"]["ctr"] * 100, summary["after"]["ctr"] * 100, False, "{:.2f}"),
    ("Average Position", summary["before"]["position"], summary["after"]["position"], True, "{:.1f}"),
]

cols = st.columns(4)
for col, (name, before_val, after_val, lower_is_better, fmt) in zip(cols, metric_definitions):
    delta_text = metrics.format_before_after_delta(before_val, after_val, lower_is_better)
    col.metric(name, fmt.format(after_val), delta_text)

st.plotly_chart(
    plotly_charts.before_after_bar_chart(
        ["Clicks", "Impressions"],
        [summary["before"]["clicks"], summary["before"]["impressions"]],
        [summary["after"]["clicks"], summary["after"]["impressions"]],
        "Clicks & Impressions: Before vs After",
        "Count",
    ),
    width="stretch",
)

st.caption("For page-specific tracking (independent of before/after pairs), see the Page Performance page.")

if summary["keyword"]:
    keyword_summary = summary["keyword"]
    st.subheader(f"Target Keyword: {keyword_summary['query']}")

    before_pos = keyword_summary["before_position"]
    after_pos = keyword_summary["after_position"]
    if before_pos is not None and after_pos is not None:
        change = metrics.position_change(before_pos, after_pos)
        st.metric(
            "Position",
            f"{after_pos:.1f}",
            f"{change:+.1f}",
            help="Lower is better. A positive delta means the position improved.",
        )
    else:
        st.info("This target keyword was not found in one or both of the compared periods.")

st.divider()
if comparison.has_performance_improved(summary):
    st.success("Performance improved following this optimization.")
else:
    st.info("No clear performance improvement was observed following this optimization.")
