"""
Database layer for TikTok Travel Saver.
Handles all Supabase interactions.
"""
import os
import re
from urllib.parse import urlparse
from dotenv import load_dotenv
from supabase import create_client, Client

# Load .env
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ---------------------------------------------------------------------------
# Supabase client initialization
# ---------------------------------------------------------------------------
_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not _SUPABASE_URL or not _SUPABASE_KEY:
    print("⚠️  SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set in .env — DB features will fail.")
    _supabase: Client | None = None
else:
    _supabase: Client = create_client(_SUPABASE_URL, _SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def db_fetch_all() -> dict:
    """Return {tiktoks: [...]} from Supabase, shaped for the HTML templates."""
    if _supabase is None:
        return {"tiktoks": []}
    rows = (
        _supabase.table("tiktoks")
        .select("id,url,author,city,country,status,cover_path,data,transcript,screen_text,created_at,reviewed_at")
        .order("created_at", desc=True)
        .execute()
        .data
    )
    # Merge top-level columns back into the shape the HTML templates expect
    tiktoks = []
    for row in rows:
        entry = row.get("data") or {}
        entry["id"] = row["id"]
        entry["url"] = row["url"]
        entry["author"] = row.get("author", "")
        entry["city"] = row["city"]
        entry["country"] = row["country"]
        entry["status"] = row["status"]
        entry["cover_path"] = row.get("cover_path", "")
        entry["transcript"] = row.get("transcript", "")
        entry["screen_text"] = row.get("screen_text", "")
        entry["created_at"] = row.get("created_at", "")
        tiktoks.append(entry)
    return {"tiktoks": tiktoks}


def db_find_by_id(tiktok_id: str) -> dict | None:
    """Fetch a single TikTok row by id and return it merged, or None."""
    if _supabase is None:
        return None
    rows = (
        _supabase.table("tiktoks")
        .select("*")
        .eq("id", tiktok_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return None
    row = rows[0]
    entry = row.get("data") or {}
    entry["id"] = row["id"]
    entry["url"] = row["url"]
    entry["author"] = row.get("author", "")
    entry["city"] = row["city"]
    entry["country"] = row["country"]
    entry["status"] = row["status"]
    entry["cover_path"] = row.get("cover_path", "")
    entry["transcript"] = row.get("transcript", "")
    entry["screen_text"] = row.get("screen_text", "")
    entry["created_at"] = row.get("created_at", "")
    return entry


def db_save_tiktok(tiktok_url: str, extraction: dict, transcript: str, screen_text: str) -> dict:
    """Insert (or upsert) a TikTok extraction into Supabase. Returns the saved row."""
    if _supabase is None:
        raise RuntimeError("Supabase client not initialised — check .env")
    vs = extraction.get("video_summary") or {}
    city = vs.get("destination_city") or "Unknown"
    country = vs.get("destination_country") or "Unknown"
    # Build a stable id from url (strip query params, use last path segment)
    parsed = urlparse(tiktok_url)
    video_id = parsed.path.rstrip("/").rsplit("/", 1)[-1] or "unknown"
    slug_city = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")
    tiktok_id = f"{slug_city}-{video_id}"
    row = {
        "id": tiktok_id,
        "url": tiktok_url,
        "city": city,
        "country": country,
        "status": "needs_review",
        "data": extraction,
        "transcript": transcript or "",
        "screen_text": screen_text or "",
    }
    _supabase.table("tiktoks").upsert(row).execute()
    return {**extraction, **row}
