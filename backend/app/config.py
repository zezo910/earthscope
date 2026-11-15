"""Every path the backend uses, in one place. Override any of them with an environment variable."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

RAW_DIR = Path(os.environ.get("EARTHSCOPE_RAW", REPO_ROOT / "data" / "raw"))
PROCESSED_DIR = Path(os.environ.get("EARTHSCOPE_PROCESSED", REPO_ROOT / "data" / "processed"))
DB_PATH = Path(os.environ.get("EARTHSCOPE_DB", PROCESSED_DIR / "earthscope.db"))

SCHEMA_SQL = BACKEND_DIR / "db" / "schema.sql"
CASES_JSON = BACKEND_DIR / "db" / "cases.json"

# The EarthScope website (the Base44 design). FastAPI serves it at http://127.0.0.1:8000
FRONTEND_DIR = REPO_ROOT / "frontend"
# Live Base44 app: the site's data functions and player profiles still run there
BASE44_URL = os.environ.get("EARTHSCOPE_BASE44_URL", "https://earth-scope-detective.base44.app").rstrip("/")
# Static copy of the case-game data (offline demo mode for case-game/)
STATIC_EXPORT_DIR = Path(os.environ.get("EARTHSCOPE_STATIC_EXPORT", REPO_ROOT / "case-game" / "public" / "static"))
