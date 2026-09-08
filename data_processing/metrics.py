"""Pure metric calculations shared across the dashboard.

Keeping these here (instead of duplicating math in each page) is what
guarantees Overview and Keyword Performance agree on what "average position"
or "% change" means.
"""

from datetime import date, timedelta

import pandas as pd


def days_since(reference_date: date) -> int:
    """Days between reference_date and today. Used to flag stale data on the
    Overview page. Negative values (a future-dated period) are left as-is —
    callers should clamp for display."""
    return (date.today() - reference_date).days


def total_clicks(df: pd.DataFrame) -> int:
    return int(df["clicks"].sum()) if not df.empty else 0


def total_impressions(df: pd.DataFrame) -> int:
    return int(df["impressions"].sum()) if not df.empty else 0


def average_ctr(df: pd.DataFrame) -> float:
    """Impressions-weighted CTR (clicks / impressions), matching how GSC
    reports an aggregate CTR rather than a plain mean of per-query CTR."""
    impressions = total_impressions(df)
    if impressions == 0:
        return 0.0
    return total_clicks(df) / impressions


def average_position(df: pd.DataFrame) -> float:
    """Impressions-weighted average position. A plain mean would let a
    handful of low-impression queries skew the number disproportionately."""
    impressions = total_impressions(df)
    if impressions == 0 or df.empty:
        return 0.0
    return float((df["position"] * df["impressions"]).sum() / impressions)


def percent_change(previous_value: float, current_value: float):
    """Returns None when previous_value is 0, since percent change is
    undefined there — callers should render 'N/A' rather than divide by zero."""
    if previous_value == 0:
        return None
    return (current_value - previous_value) / previous_value * 100


def position_change(previous_position: float, current_position: float) -> float:
    """Positive means the position improved (the number went down)."""
    return previous_position - current_position


def format_before_after_delta(before_value: float, after_value: float, lower_is_better: bool = False) -> str:
    """Delta string for st.metric: absolute change plus percent change when
    defined. Sign is flipped for lower_is_better metrics (e.g. position) so
    an actual improvement always displays as positive, matching Streamlit's
    default green-for-positive delta coloring."""
    absolute_change = after_value - before_value
    pct_change = percent_change(before_value, after_value)

    displayed_change = -absolute_change if lower_is_better else absolute_change
    displayed_pct = (-pct_change if lower_is_better else pct_change) if pct_change is not None else None

    delta_text = f"{displayed_change:+.2f}"
    if displayed_pct is not None:
        delta_text += f" ({displayed_pct:+.1f}%)"
    return delta_text


def previous_equivalent_period(start_date: date, end_date: date) -> tuple:
    """The immediately preceding period of the same length — e.g. Last 28
    Days -> the 28 days before that. Used for optional period comparison."""
    period_length_days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_length_days - 1)
    return previous_start, previous_end


def format_ctr_delta(previous_ctr: float, current_ctr: float) -> str:
    """CTR change shown as percentage-point change (the number that actually
    matters for CTR) with relative percent change alongside for context —
    these are different numbers and conflating them is a common mistake."""
    point_change = (current_ctr - previous_ctr) * 100
    pct_change = percent_change(previous_ctr, current_ctr)
    delta_text = f"{point_change:+.2f} pp"
    if pct_change is not None:
        delta_text += f" ({pct_change:+.1f}%)"
    return delta_text
