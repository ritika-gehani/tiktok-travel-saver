"""
Database layer for TikTok Travel Saver.

Two backends, chosen automatically:
  - Supabase, when SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set.
  - A local JSON file otherwise (LIBRARY_FILE, default data/library.json),
    seeded from data/seed-library.json on first use so the app works offline
    with no credentials.
"""
import json
import os
import re
import shutil
from datetime import datetime, timezone
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SEED_FILE = os.path.join(PROJECT_DIR, "data", "seed-library.json")
DEFAULT_LIBRARY_FILE = os.path.join(PROJECT_DIR, "data", "library.json")

load_dotenv(os.path.join(PROJECT_DIR, ".env"))

# ---------------------------------------------------------------------------
# Supabase client initialization
# ---------------------------------------------------------------------------
_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if _SUPABASE_URL and _SUPABASE_KEY:
    from supabase import create_client

    _supabase = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    BACKEND = "supabase"
else:
    _supabase = None
    BACKEND = "local"

ROW_COLUMNS = (
    "id,url,author,city,country,status,cover_path,data,transcript,screen_text,created_at,reviewed_at"
)


def _merge_row(row: dict) -> dict:
    """Flatten a stored row into the shape the HTML templates expect."""
    entry = dict(row.get("data") or {})
    entry["id"] = row["id"]
    entry["url"] = row["url"]
    entry["author"] = row.get("author") or ""
    entry["city"] = row["city"]
    entry["country"] = row["country"]
    entry["status"] = row["status"]
    entry["cover_path"] = row.get("cover_path") or ""
    entry["transcript"] = row.get("transcript") or ""
    entry["screen_text"] = row.get("screen_text") or ""
    entry["created_at"] = row.get("created_at") or ""
    return entry


def _build_row(tiktok_url: str, extraction: dict, transcript: str, screen_text: str) -> dict:
    vs = extraction.get("video_summary") or {}
    city = vs.get("destination_city") or "Unknown"
    country = vs.get("destination_country") or "Unknown"
    # Build a stable id from url (strip query params, use last path segment)
    parsed = urlparse(tiktok_url)
    video_id = parsed.path.rstrip("/").rsplit("/", 1)[-1] or "unknown"
    slug_city = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")
    return {
        "id": f"{slug_city}-{video_id}",
        "url": tiktok_url,
        "city": city,
        "country": country,
        "status": "needs_review",
        "data": extraction,
        "transcript": transcript or "",
        "screen_text": screen_text or "",
    }


# ---------------------------------------------------------------------------
# Local JSON backend
# ---------------------------------------------------------------------------

def library_file() -> str:
    return os.environ.get("LIBRARY_FILE", DEFAULT_LIBRARY_FILE)


def _local_read() -> list[dict]:
    path = library_file()
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if os.path.exists(SEED_FILE):
            shutil.copyfile(SEED_FILE, path)
        else:
            _local_write([])
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _local_write(rows: list[dict]) -> None:
    path = library_file()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def db_fetch_all() -> dict:
    """Return {tiktoks: [...]} newest first, shaped for the HTML templates."""
    if _supabase is None:
        rows = sorted(_local_read(), key=lambda r: r.get("created_at") or "", reverse=True)
    else:
        rows = (
            _supabase.table("tiktoks")
            .select(ROW_COLUMNS)
            .order("created_at", desc=True)
            .execute()
            .data
        )
    return {"tiktoks": [_merge_row(r) for r in rows]}


def db_find_by_id(tiktok_id: str) -> dict | None:
    """Fetch a single TikTok row by id and return it merged, or None."""
    if _supabase is None:
        rows = [r for r in _local_read() if r["id"] == tiktok_id]
    else:
        rows = (
            _supabase.table("tiktoks")
            .select("*")
            .eq("id", tiktok_id)
            .limit(1)
            .execute()
            .data
        )
    return _merge_row(rows[0]) if rows else None


def db_save_tiktok(tiktok_url: str, extraction: dict, transcript: str, screen_text: str) -> dict:
    """Insert (or upsert) a TikTok extraction. Returns the saved row merged with the extraction."""
    row = _build_row(tiktok_url, extraction, transcript, screen_text)
    if _supabase is None:
        row["created_at"] = datetime.now(timezone.utc).isoformat()
        rows = [r for r in _local_read() if r["id"] != row["id"]]
        rows.append(row)
        _local_write(rows)
    else:
        _supabase.table("tiktoks").upsert(row).execute()
    return {**extraction, **row}
