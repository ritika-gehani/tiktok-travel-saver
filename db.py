"""
Database layer for TikTok Travel Saver.

Two backends, chosen automatically:
  - Supabase, when SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set.
  - A local JSON file otherwise (LIBRARY_FILE, default data/library.json),
    seeded from data/seed-library.json on first use so the app works offline
    with no credentials.

Data model:
  - A *trip* is one city (country + city + optional dates + planning mode).
  - Every saved TikTok belongs to exactly one trip via trip_id.
"""
import json
import os
import re
import shutil
from datetime import datetime, timezone
from urllib.parse import urlparse

from dotenv import load_dotenv

from destinations import canonical_city, canonical_country, country_code, flag
from labels import normalize_extraction

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SEED_FILE = os.path.join(PROJECT_DIR, "data", "seed-library.json")
DEFAULT_LIBRARY_FILE = os.path.join(PROJECT_DIR, "data", "library.json")

PLANNING_MODES = ("collect", "itinerary")

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
    "id,url,author,trip_id,city,country,status,cover_path,data,transcript,screen_text,created_at,reviewed_at"
)
TRIP_COLUMNS = "id,country,city,start_date,end_date,planning_mode,created_at"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "unknown"


def _merge_row(row: dict) -> dict:
    """Flatten a stored TikTok row into the shape the HTML templates expect."""
    entry = normalize_extraction(dict(row.get("data") or {}))
    entry["id"] = row["id"]
    entry["url"] = row["url"]
    entry["author"] = row.get("author") or ""
    entry["trip_id"] = row.get("trip_id") or ""
    entry["city"] = row["city"]
    entry["country"] = row["country"]
    entry["status"] = row["status"]
    entry["cover_path"] = row.get("cover_path") or ""
    entry["transcript"] = row.get("transcript") or ""
    entry["screen_text"] = row.get("screen_text") or ""
    entry["created_at"] = row.get("created_at") or ""
    return entry


def _merge_trip(trip: dict) -> dict:
    code = country_code(trip["country"])
    return {
        "id": trip["id"],
        "country": trip["country"],
        "city": trip["city"],
        "country_code": code,
        "flag": flag(code),
        "start_date": trip.get("start_date") or "",
        "end_date": trip.get("end_date") or "",
        "planning_mode": trip.get("planning_mode") or "collect",
        "created_at": trip.get("created_at") or "",
    }


def _build_row(tiktok_url: str, extraction: dict, transcript: str, screen_text: str, trip: dict) -> dict:
    parsed = urlparse(tiktok_url)
    video_id = parsed.path.rstrip("/").rsplit("/", 1)[-1] or "unknown"
    return {
        "id": f"{_slug(trip['city'])}-{video_id}",
        "url": tiktok_url,
        "trip_id": trip["id"],
        "city": trip["city"],
        "country": trip["country"],
        "status": "needs_review",
        "data": normalize_extraction(extraction),
        "transcript": transcript or "",
        "screen_text": screen_text or "",
    }


def _build_trip(country: str, city: str, start_date: str, end_date: str, planning_mode: str,
                existing_ids: set[str]) -> dict:
    base = f"{_slug(city)}-{_slug(country)}"
    trip_id, n = base, 2
    while trip_id in existing_ids:
        trip_id, n = f"{base}-{n}", n + 1
    return {
        "id": trip_id,
        "country": country,
        "city": city,
        "start_date": start_date or None,
        "end_date": end_date or None,
        "planning_mode": planning_mode if planning_mode in PLANNING_MODES else "collect",
        "created_at": _now(),
    }


def _find_trip_for(trips: list[dict], country: str, city: str) -> dict | None:
    for t in trips:
        if t["city"].lower() == (city or "").lower() and t["country"].lower() == (country or "").lower():
            return t
    return None


def _assign_orphans(trips: list[dict], tiktoks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Give every TikTok without a trip_id a trip (one per city), creating trips as needed.
    Returns (new_trips, changed_tiktoks)."""
    new_trips, changed = [], []
    for row in tiktoks:
        if row.get("trip_id"):
            continue
        trip = _find_trip_for(trips, row["country"], row["city"])
        if trip is None:
            trip = _build_trip(row["country"], row["city"], "", "", "collect", {t["id"] for t in trips})
            trip["created_at"] = row.get("created_at") or trip["created_at"]
            trips.append(trip)
            new_trips.append(trip)
        row["trip_id"] = trip["id"]
        changed.append(row)
    return new_trips, changed


# ---------------------------------------------------------------------------
# Local JSON backend
# ---------------------------------------------------------------------------

def library_file() -> str:
    return os.environ.get("LIBRARY_FILE", DEFAULT_LIBRARY_FILE)


def _local_read() -> dict:
    """Return {"trips": [...], "tiktoks": [...]}, migrating older list-only files in place."""
    path = library_file()
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if os.path.exists(SEED_FILE):
            shutil.copyfile(SEED_FILE, path)
        else:
            _local_write({"trips": [], "tiktoks": []})
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    store = {"trips": [], "tiktoks": raw} if isinstance(raw, list) else raw
    store.setdefault("trips", [])
    store.setdefault("tiktoks", [])
    new_trips, changed = _assign_orphans(store["trips"], store["tiktoks"])
    if isinstance(raw, list) or new_trips or changed:
        _local_write(store)
    return store


def _local_write(store: dict) -> None:
    path = library_file()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _supabase_read() -> dict:
    trips = _supabase.table("trips").select(TRIP_COLUMNS).order("created_at", desc=True).execute().data
    tiktoks = _supabase.table("tiktoks").select(ROW_COLUMNS).order("created_at", desc=True).execute().data
    new_trips, changed = _assign_orphans(trips, tiktoks)
    if new_trips:
        _supabase.table("trips").upsert(new_trips).execute()
    for row in changed:
        _supabase.table("tiktoks").update({"trip_id": row["trip_id"]}).eq("id", row["id"]).execute()
    return {"trips": trips, "tiktoks": tiktoks}


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def db_fetch_all() -> dict:
    """Return {trips: [...], tiktoks: [...]} newest first, shaped for the HTML templates."""
    store = _local_read() if _supabase is None else _supabase_read()
    trips = sorted(store["trips"], key=lambda t: t.get("created_at") or "", reverse=True)
    tiktoks = sorted(store["tiktoks"], key=lambda r: r.get("created_at") or "", reverse=True)
    return {"trips": [_merge_trip(t) for t in trips], "tiktoks": [_merge_row(r) for r in tiktoks]}


def db_find_trip(trip_id: str) -> dict | None:
    if _supabase is None:
        trips = [t for t in _local_read()["trips"] if t["id"] == trip_id]
    else:
        trips = _supabase.table("trips").select(TRIP_COLUMNS).eq("id", trip_id).limit(1).execute().data
    return _merge_trip(trips[0]) if trips else None


def db_create_trip(country: str, city: str, start_date: str = "", end_date: str = "",
                   planning_mode: str = "collect") -> dict:
    """Create a city trip. Country/city are stored as given — validate them first."""
    if _supabase is None:
        store = _local_read()
        trip = _build_trip(country, city, start_date, end_date, planning_mode, {t["id"] for t in store["trips"]})
        store["trips"].append(trip)
        _local_write(store)
    else:
        existing = {t["id"] for t in _supabase.table("trips").select("id").execute().data}
        trip = _build_trip(country, city, start_date, end_date, planning_mode, existing)
        _supabase.table("trips").insert(trip).execute()
    return _merge_trip(trip)


def db_find_by_id(tiktok_id: str) -> dict | None:
    """Fetch a single TikTok row by id and return it merged, or None."""
    if _supabase is None:
        rows = [r for r in _local_read()["tiktoks"] if r["id"] == tiktok_id]
    else:
        rows = _supabase.table("tiktoks").select("*").eq("id", tiktok_id).limit(1).execute().data
    return _merge_row(rows[0]) if rows else None


def db_save_tiktok(tiktok_url: str, extraction: dict, transcript: str, screen_text: str,
                   trip_id: str = "") -> dict:
    """Insert (or upsert) a TikTok extraction into a trip.

    With trip_id, the TikTok is filed under that trip. Without one, it is filed
    under the trip matching the extraction's destination city (created if needed).
    Returns the saved row merged with the extraction.
    """
    trip = db_find_trip(trip_id) if trip_id else None
    if trip is None:
        if trip_id:
            raise LookupError(f"No trip with id {trip_id!r}")
        vs = extraction.get("video_summary") or {}
        city = vs.get("destination_city") or "Unknown"
        country = vs.get("destination_country") or "Unknown"
        country = canonical_country(country) or country
        city = canonical_city(country, city) or city
        trip = _find_trip_for(db_fetch_all()["trips"], country, city) or db_create_trip(country, city)

    row = _build_row(tiktok_url, extraction, transcript, screen_text, trip)
    if _supabase is None:
        row["created_at"] = _now()
        store = _local_read()
        store["tiktoks"] = [r for r in store["tiktoks"] if r["id"] != row["id"]] + [row]
        _local_write(store)
    else:
        _supabase.table("tiktoks").upsert(row).execute()
    return {**extraction, **row}
