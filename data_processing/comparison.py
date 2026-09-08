"""Logic for comparing two periods of GSC data: current-vs-previous for the
Keyword Performance page, and before-vs-after for the change-log analysis.
"""

import pandas as pd

from data_processing import metrics


def build_period_summary(df: pd.DataFrame) -> dict:
    """Aggregate totals for a single period, computed from query-level rows.

    Only a fallback for periods with no stored site-wide total (see
    build_period_summary_from_dataset) — Search Console's query-level
    breakdown omits some low-volume/anonymized queries, so this can
    understate the true total.
    """
    return {
        "clicks": metrics.total_clicks(df),
        "impressions": metrics.total_impressions(df),
        "ctr": metrics.average_ctr(df),
        "position": metrics.average_position(df),
    }


def build_period_summary_from_dataset(dataset_row, query_df: pd.DataFrame) -> dict:
    """Aggregate totals for a period, for KPI-level display.

    Prefers the dataset's stored site-wide totals (from a dimension-less
    Search Console API call, fetch_overall_performance) over summing
    query-level rows, since the query-level breakdown omits some low-volume/
    anonymized queries and would undercount. Falls back to summing query_df
    only when no site-wide total was captured — i.e. a manually uploaded
    CSV export, which has no separate total to draw from — and flags that
    result as approximate so the UI can say so.
    """
    total_clicks = dataset_row.get("total_clicks")
    if pd.notna(total_clicks):
        return {
            "clicks": int(total_clicks),
            "impressions": int(dataset_row["total_impressions"]),
            "ctr": float(dataset_row["overall_ctr"]),
            "position": float(dataset_row["overall_position"]),
            "is_approximate": False,
        }

    summary = build_period_summary(query_df)
    summary["is_approximate"] = True
    return summary


def merge_current_and_previous(current_df: pd.DataFrame, previous_df: pd.DataFrame) -> pd.DataFrame:
    """Left-join current-period queries with the previous period's position.

    Queries with no previous-period match (new queries) get a missing
    previous_position/position_change rather than being dropped or crashing.
    """
    merged = current_df.copy()

    if previous_df is None or previous_df.empty:
        merged["previous_position"] = pd.NA
        merged["position_change"] = pd.NA
        return merged

    previous_positions = previous_df[["query", "position"]].rename(columns={"position": "previous_position"})
    merged = merged.merge(previous_positions, on="query", how="left")
    merged["position_change"] = merged.apply(
        lambda row: metrics.position_change(row["previous_position"], row["position"])
        if pd.notna(row["previous_position"])
        else pd.NA,
        axis=1,
    )
    return merged


def normalize_page_url(url: str) -> str:
    """Loose normalization so 'https://x.com/page' and 'https://x.com/page/'
    (or different casing) still match the same GSC page row. Used wherever a
    freeform-typed page URL (e.g. a change log entry) needs to match GSC's
    canonical page strings."""
    return url.strip().rstrip("/").lower()


def build_before_after_summary(
    before_meta,
    after_meta,
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
    target_keyword: str = None,
) -> dict:
    """Aggregate before/after totals (site-wide, via build_period_summary_from_dataset),
    plus a target-keyword position comparison when that data is available.

    Page-specific comparison lives on the separate Page Performance page now
    (it doesn't need a before/after pair), not here.
    """
    result = {
        "before": build_period_summary_from_dataset(before_meta, before_df),
        "after": build_period_summary_from_dataset(after_meta, after_df),
        "keyword": None,
    }

    if target_keyword:
        before_row = before_df[before_df["query"].str.lower() == target_keyword.strip().lower()]
        after_row = after_df[after_df["query"].str.lower() == target_keyword.strip().lower()]
        result["keyword"] = {
            "query": target_keyword,
            "before_position": float(before_row["position"].iloc[0]) if not before_row.empty else None,
            "after_position": float(after_row["position"].iloc[0]) if not after_row.empty else None,
        }

    return result


def has_performance_improved(summary: dict) -> bool:
    """Simple heuristic used only to choose which summary message to display
    — clicks went up or average position got numerically lower. This is a
    correlation check, never a claim that the SEO change caused the result."""
    before, after = summary["before"], summary["after"]
    return after["clicks"] > before["clicks"] or after["position"] < before["position"]
