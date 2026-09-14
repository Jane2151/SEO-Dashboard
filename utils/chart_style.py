"""Shared fade/slide-in animation for Plotly charts, so switching between
views (e.g. Clicks / Impressions / Compare on the Overview page) reads as a
smooth transition instead of an abrupt pop.
"""

import streamlit as st

_CSS = """
<style>
@keyframes seoChartFadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
div[data-testid="stPlotlyChart"] {
    animation: seoChartFadeIn 0.45s ease-out;
}
</style>
"""


def inject_chart_transition_css() -> None:
    st.html(_CSS)
