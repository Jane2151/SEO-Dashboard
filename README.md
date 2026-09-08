# SEO Performance Dashboard

A Streamlit dashboard for tracking whether SEO changes are followed by
improvements in Google Search Console (GSC) performance. It syncs GSC data
automatically via the Search Console API and never claims causation — only
"performance changed after this SEO change," not "this change caused it."

The dashboard is locked to a single GSC property, set in
`utils/constants.py` (`TARGET_SITE_URL`).

## Setup

```
pip install -r requirements.txt
```

### Connect Google Search Console

1. In [Google Cloud Console](https://console.cloud.google.com/), create an
   OAuth Client ID of type **Desktop app** and enable the Search Console API
   for that project.
2. Download the client secret JSON and save it as
   `credentials/client_secret.json` (this path is gitignored — never commit
   it).
3. Run the app and click **Connect to Google Search Console** on the main
   page. This opens a one-time browser consent flow; the resulting token is
   cached to `credentials/token.json` (also gitignored) and refreshed
   automatically afterward.

## Run

```
streamlit run app.py
```

On the main page, click **Sync GSC Data**. The first sync backfills the
last 90 days; every sync after that re-fetches the most recent few days too,
since Google can revise recently-collected data for a few days after it's
first reported.

## Pages

- **SEO Overview** — KPI cards (Clicks, Impressions, CTR, Average Position)
  for a selected date range (Last 7/28 Days, Last 3 Months, or a custom
  range), trend charts with SEO Change Log entries marked on them, an
  optional previous-period comparison, and Top Pages / Devices / Countries
  breakdowns.
- **Keyword Performance** — a manually-curated list of target keywords
  (distinct from GSC's own reported queries) with per-keyword stats and
  trend, plus a searchable/sortable table of every actual search query GSC
  reports.
- **SEO Change Log** — record, edit, and delete SEO changes (title/meta
  updates, content changes, technical SEO, etc.). Entries with a target
  keyword are automatically added to the Keyword Performance watchlist, and
  every entry appears as a marker on the Overview trend charts.

`legacy_pages/` holds two earlier, now-unused pages (Before/After Analysis,
Page Performance) kept for reference — they aren't part of the active
Streamlit navigation.

## Data model

GSC data is stored at daily granularity (`gsc_daily_overall`,
`gsc_daily_query`, `gsc_daily_page`, `gsc_daily_device`,
`gsc_daily_country`), so any date range is computed by aggregating stored
days rather than re-fetching per range. Aggregation always uses SUM(clicks),
SUM(impressions), SUM(clicks)/SUM(impressions) for CTR, and
impressions-weighted average position — never a plain average of daily
values. `sync_state.latest_complete_date` tracks the newest date Google
itself considers finalized (via `dataState="final"`); preset date ranges
anchor to that, not to the newest date merely stored locally, so a
still-revisable day never silently inflates a KPI card.

The SQLite file itself (`data/seo_dashboard.db`) is gitignored — each
environment builds its own from a fresh sync.

## Project structure

- `app.py` — GSC connection and the Sync GSC Data button (the app's landing
  page)
- `pages/` — the three active dashboard pages
- `legacy_pages/` — retired pages kept for reference, not in the nav
- `database/` — SQLite schema and CRUD/aggregation functions
- `data_processing/` — GSC API client, sync logic, and metric calculations
- `charts/` — reusable Plotly chart builders
- `utils/` — shared constants and the date-range picker
