"""Parsing and validation for uploaded Google Search Console query exports.

GSC's UI export for the Performance report's "Queries" table typically uses
headers like "Top queries", "Clicks", "Impressions", "CTR", "Position", with
CTR as a percentage string (e.g. "4.32%"). This module normalizes that into a
consistent DataFrame the rest of the app can rely on.
"""

import pandas as pd

COLUMN_ALIASES = {
    "query": ["top queries", "query", "queries", "keyword"],
    "clicks": ["clicks"],
    "impressions": ["impressions"],
    "ctr": ["ctr"],
    "position": ["position", "average position", "avg. position"],
}


class GSCFileFormatError(ValueError):
    """Raised when an uploaded file doesn't look like a GSC query export."""


def parse_gsc_csv(uploaded_file) -> pd.DataFrame:
    """Read an uploaded GSC 'Queries' CSV export.

    Returns a DataFrame with normalized columns: query, clicks, impressions,
    ctr (fraction 0-1), position (float). Raises GSCFileFormatError with a
    clear message if the file can't be read or is missing expected columns.
    """
    try:
        raw_df = pd.read_csv(uploaded_file)
    except Exception as exc:
        raise GSCFileFormatError(f"Could not read file as CSV: {exc}") from exc

    columns_by_lower_name = {column.strip().lower(): column for column in raw_df.columns}

    resolved_columns = {}
    for field, aliases in COLUMN_ALIASES.items():
        match = next((columns_by_lower_name[alias] for alias in aliases if alias in columns_by_lower_name), None)
        if match is None:
            raise GSCFileFormatError(
                f"Missing expected column for '{field}'. Found columns: {list(raw_df.columns)}"
            )
        resolved_columns[field] = match

    clean_df = pd.DataFrame()
    clean_df["query"] = raw_df[resolved_columns["query"]].astype(str).str.strip()
    clean_df["clicks"] = _parse_number(raw_df[resolved_columns["clicks"]]).fillna(0).astype(int)
    clean_df["impressions"] = _parse_number(raw_df[resolved_columns["impressions"]]).fillna(0).astype(int)
    clean_df["ctr"] = raw_df[resolved_columns["ctr"]].apply(_parse_ctr)
    clean_df["position"] = _parse_number(raw_df[resolved_columns["position"]])

    # Drop rows where position couldn't be parsed at all; keep everything else.
    clean_df = clean_df.dropna(subset=["position"]).reset_index(drop=True)

    if clean_df.empty:
        raise GSCFileFormatError("No usable rows found after parsing the file.")

    return clean_df


def _parse_number(series: pd.Series) -> pd.Series:
    """Strip thousands separators before converting to numeric, since some
    locale exports format Clicks/Impressions like '1,234'."""
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(cleaned, errors="coerce")


def _parse_ctr(value) -> float:
    """Normalize a CTR cell to a 0-1 fraction, whether it arrives as '4.3%',
    '4.3', or '0.043'."""
    text = str(value).strip()
    had_percent_sign = text.endswith("%")
    if had_percent_sign:
        text = text[:-1]

    number = pd.to_numeric(text, errors="coerce")
    if pd.isna(number):
        return 0.0
    if had_percent_sign or number > 1:
        return float(number) / 100.0
    return float(number)
