from pathlib import Path

# Project root is the parent of this utils/ folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# OAuth client secret (downloaded from Google Cloud Console) — only ever
# needed locally, for the one-time interactive "Connect" flow, which opens a
# real browser and so can't run on a hosted deployment. The resulting user
# token is cached in the shared database (oauth_token_repository), not here,
# since a hosted deployment has no persistent local disk.
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
CLIENT_SECRET_PATH = CREDENTIALS_DIR / "client_secret.json"

# This dashboard tracks a single Search Console property. Fetching is locked
# to this site so data from any other verified property in the account never
# gets mixed into the same dataset history.
TARGET_SITE_URL = "sc-domain:kampar-free-range-duck.com"

# Staleness thresholds for the Overview page, measured in days between the
# current period's end date and today. Search Console itself has a ~2-3 day
# processing delay, so "a few days old" is normal; these flag when a period
# hasn't been refreshed in a while.
STALE_WARNING_DAYS = 7
STALE_ERROR_DAYS = 30

CHANGE_CATEGORIES = [
    "Title optimization",
    "Meta description",
    "Content update",
    "Heading optimization",
    "Structured data",
    "Internal linking",
    "Image optimization",
    "Technical SEO",
    "Other",
]
