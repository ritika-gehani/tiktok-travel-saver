"""End-to-end HTTP tests for the web UI, run against the local JSON store."""
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def library_file(tmp_path, monkeypatch):
    path = tmp_path / "library.json"
    monkeypatch.setenv("LIBRARY_FILE", str(path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    return path


@pytest.fixture()
def server(library_file):
    import web_viewer

    httpd = HTTPServer(("127.0.0.1", 0), web_viewer.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def get(base, path):
    try:
        with urllib.request.urlopen(base + path) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def get_json(base, path):
    status, body = get(base, path)
    return status, json.loads(body)


def post_json(base, path, payload):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def embedded(body, name):
    """Pull a `const NAME = {...};` JSON blob out of a rendered page."""
    marker = f"const {name} = "
    start = body.index(marker) + len(marker)
    end = body.index(";\n", start)
    return json.loads(body[start:end].replace("<\\/", "</"))


SEVILLE = {
    "video_summary": {
        "main_topic": "Tapas Crawl in Seville",
        "destination_city": "Seville",
        "destination_country": "Spain",
        "usefulness_for_itinerary": "high",
        "overall_vibe": ["food"],
        "summary": "Three tapas bars.",
    },
    "places": [{"name": "El Rinconcillo", "place_type": "bar", "confidence": "high"}],
    "non_place_notes": [],
    "needs_user_review": [],
}


# --- Home -------------------------------------------------------------------

def test_home_lists_one_trip_per_seeded_city(server):
    status, body = get(server, "/")
    assert status == 200
    data = embedded(body, "LIBRARY_DATA")
    cities = {(t["city"], t["country"]) for t in data["trips"]}
    assert cities == {
        ("Tokyo", "Japan"), ("Kyoto", "Japan"),
        ("Lisbon", "Portugal"), ("Porto", "Portugal"),
        ("Mexico City", "Mexico"),
    }
    trip_ids = {t["id"] for t in data["trips"]}
    assert all(t["trip_id"] in trip_ids for t in data["tiktoks"])
    assert data["trips"][0]["flag"]  # country flag derived from ISO code


# --- Destination typeahead ----------------------------------------------------

def test_country_typeahead_filters_as_you_type(server):
    status, data = get_json(server, "/api/destinations?q=jap")
    assert status == 200
    assert [c["name"] for c in data["countries"]] == ["Japan"]
    assert data["countries"][0]["code"] == "JP"

    status, data = get_json(server, "/api/destinations?q=zzzz")
    assert status == 200
    assert data["countries"] == []


def test_city_typeahead_is_scoped_to_country(server):
    status, data = get_json(server, "/api/destinations?country=Japan&q=ky")
    assert status == 200
    assert data["country"] == "Japan"
    assert data["cities"][0] == "Kyoto"
    assert all(c.lower().startswith("ky") for c in data["cities"])

    # Same prefix, different country: Kyoto must not leak through.
    status, data = get_json(server, "/api/destinations?country=Portugal&q=ky")
    assert status == 200
    assert "Kyoto" not in data["cities"]

    status, data = get_json(server, "/api/destinations?country=Japan&q=kyotoo")
    assert status == 200
    assert data["cities"] == []


def test_city_typeahead_accepts_common_english_spellings(server):
    status, data = get_json(server, "/api/destinations?country=Spain&q=seville")
    assert status == 200
    assert data["cities"] == ["Sevilla"]

    status, resp = post_json(server, "/trips", {"country": "Spain", "city": "Seville"})
    assert status == 201
    assert resp["trip"]["city"] == "Sevilla"


def test_city_typeahead_unknown_country_is_404(server):
    status, data = get_json(server, "/api/destinations?country=Narnia&q=a")
    assert status == 404
    assert data["cities"] == []


# --- Create trip --------------------------------------------------------------

def test_create_trip_canonicalises_country_and_city(server):
    status, resp = post_json(
        server, "/trips",
        {"country": "japan", "city": "osaka", "start_date": "2026-06-01", "planning_mode": "itinerary"},
    )
    assert status == 201
    trip = resp["trip"]
    assert (trip["id"], trip["country"], trip["city"]) == ("osaka-japan", "Japan", "Osaka")
    assert trip["planning_mode"] == "itinerary"
    assert trip["start_date"] == "2026-06-01"

    status, body = get(server, "/trip/osaka-japan")
    assert status == 200
    assert embedded(body, "TRIP")["city"] == "Osaka"
    assert embedded(body, "TIKTOKS") == []


def test_create_trip_rejects_unknown_country_and_city(server):
    status, resp = post_json(server, "/trips", {"country": "Narnia", "city": "Cair Paravel"})
    assert status == 400
    assert resp["error"] == "unknown_country"

    status, resp = post_json(server, "/trips", {"country": "Japan", "city": "Kyotoo"})
    assert status == 400
    assert resp["error"] == "unknown_city"
    assert "Kyotoo" in resp["message"] and "Japan" in resp["message"]


def test_create_trip_rejects_bad_date_range(server):
    status, _ = post_json(
        server, "/trips",
        {"country": "Japan", "city": "Osaka", "start_date": "2026-06-10", "end_date": "2026-06-01"},
    )
    assert status == 400


def test_second_trip_to_same_city_gets_distinct_id(server):
    status, resp = post_json(server, "/trips", {"country": "Japan", "city": "Kyoto"})
    assert status == 201
    assert resp["trip"]["id"] == "kyoto-japan-2"


# --- Trip page ----------------------------------------------------------------

def test_trip_page_lists_only_its_tiktoks(server):
    status, body = get(server, "/trip/tokyo-japan")
    assert status == 200
    trip = embedded(body, "TRIP")
    tiktoks = embedded(body, "TIKTOKS")
    assert trip["city"] == "Tokyo"
    assert [t["video_summary"]["main_topic"] for t in tiktoks] == ["5 Ramen Shops Worth the Queue in Tokyo"]
    assert all(t["trip_id"] == "tokyo-japan" for t in tiktoks)


def test_unknown_trip_is_404(server):
    status, _ = get(server, "/trip/atlantis-nowhere")
    assert status == 404


def test_add_page_carries_trip_context(server):
    status, body = get(server, "/add?trip=tokyo-japan")
    assert status == 200
    assert embedded(body, "TRIP")["id"] == "tokyo-japan"

    status, body = get(server, "/add")
    assert status == 200
    assert embedded(body, "TRIP") is None

    status, _ = get(server, "/add?trip=nope")
    assert status == 404


# --- TikTok detail ------------------------------------------------------------

def test_detail_page_shows_places_and_links_back_to_trip(server):
    status, body = get(server, "/tiktok/kyoto-7301122334455667788")
    assert status == 200
    tiktok = embedded(body, "TIKTOK")
    assert tiktok["video_summary"]["main_topic"] == "Favorite Photo Locations in Kyoto"
    assert [p["name"] for p in tiktok["places"]][:2] == ["Kifune Shrine", "Kurama Temple"]
    assert 'href="/trip/kyoto-japan"' in body


def test_unknown_tiktok_is_404(server):
    status, _ = get(server, "/tiktok/does-not-exist")
    assert status == 404


# --- Labels -------------------------------------------------------------------

def test_pages_embed_the_controlled_label_vocabulary(server):
    for path in ("/trip/tokyo-japan", "/tiktok/kyoto-7301122334455667788", "/add?trip=tokyo-japan"):
        status, body = get(server, path)
        assert status == 200, path
        labels = embedded(body, "LABELS")
        assert {t["key"] for t in labels["place_types"]} >= {"food", "sight", "other"}
        assert all(set(item) == {"key", "label", "help"} for group in labels.values() for item in group)


def test_how_it_works_page(server):
    status, body = get(server, "/how-it-works")
    assert status == 200
    assert "What the labels mean" in body
    assert embedded(body, "LABELS")["confidence"][0]["key"] == "high"


def test_how_it_works_labels_anchor_clears_the_sticky_topbar(server):
    # Regression: /how-it-works#labels must scroll the heading below the sticky
    # top bar, so anchor targets need a scroll offset at least as tall as it.
    status, body = get(server, "/how-it-works")
    assert status == 200
    assert 'id="labels"' in body
    assert "position: sticky; top: 0" in body
    assert "scroll-padding-top" in body or "scroll-margin-top" in body


def test_unknown_path_is_404(server):
    status, _ = get(server, "/nope")
    assert status == 404


# --- Save ---------------------------------------------------------------------

def test_save_into_trip(server):
    status, resp = post_json(server, "/trips", {"country": "Spain", "city": "Seville"})
    assert status == 201
    trip_id = resp["trip"]["id"]

    status, saved = post_json(
        server, "/save",
        {"url": "https://www.tiktok.com/@x/video/111222333", "result": SEVILLE, "trip_id": trip_id},
    )
    assert status == 200
    assert saved == {"ok": True, "id": "sevilla-111222333", "trip_id": trip_id, "city": "Sevilla", "country": "Spain"}

    status, body = get(server, f"/trip/{trip_id}")
    assert [t["id"] for t in embedded(body, "TIKTOKS")] == ["sevilla-111222333"]

    status, body = get(server, "/tiktok/sevilla-111222333")
    assert status == 200
    assert embedded(body, "TIKTOK")["status"] == "needs_review"


def test_save_snaps_free_text_labels_to_the_controlled_set(server, library_file):
    result = json.loads(json.dumps(SEVILLE))
    result["video_summary"]["overall_vibe"] = ["street food", "late night", "made-up-label"]
    result["places"][0].update({"place_type": "tapas restaurant", "confidence": "certain", "best_for": ["dinner"]})
    status, saved = post_json(
        server, "/save",
        {"url": "https://www.tiktok.com/@x/video/999", "result": result, "trip_id": "tokyo-japan"},
    )
    assert status == 200

    stored = next(t for t in json.loads(library_file.read_text())["tiktoks"] if t["id"] == saved["id"])
    assert stored["data"]["video_summary"]["overall_vibe"] == ["food", "nightlife"]
    assert stored["data"]["places"][0]["place_type"] == "food"
    assert stored["data"]["places"][0]["confidence"] == "high"
    assert stored["data"]["places"][0]["best_for"] == ["food"]


def test_save_without_trip_files_under_extracted_city(server):
    status, saved = post_json(
        server, "/save", {"url": "https://www.tiktok.com/@x/video/444", "result": SEVILLE},
    )
    assert status == 200
    assert saved["trip_id"] == "sevilla-spain"  # extraction's "Seville" canonicalised
    status, body = get(server, "/")
    assert any(t["id"] == "sevilla-spain" for t in embedded(body, "LIBRARY_DATA")["trips"])


def test_save_rejects_unknown_trip(server):
    status, resp = post_json(
        server, "/save",
        {"url": "https://www.tiktok.com/@x/video/555", "result": SEVILLE, "trip_id": "nope"},
    )
    assert status == 404
    assert "error" in resp


def test_save_requires_url_and_result(server):
    status, resp = post_json(server, "/save", {"url": ""})
    assert status == 400
    assert "error" in resp


def test_seed_file_is_not_modified_by_saves(server):
    seed_path = os.path.join(ROOT, "data", "seed-library.json")
    with open(seed_path, encoding="utf-8") as f:
        seed_before = f.read()
    post_json(
        server, "/save",
        {
            "url": "https://www.tiktok.com/@x/video/999",
            "result": {"video_summary": {"destination_city": "Oslo", "destination_country": "Norway"}},
        },
    )
    with open(seed_path, encoding="utf-8") as f:
        assert f.read() == seed_before


# --- Review -------------------------------------------------------------------

def test_approving_a_tiktok_clears_needs_review(server, library_file):
    tiktok_id = "tokyo-7288001122334455667"
    status, body = get(server, f"/tiktok/{tiktok_id}")
    assert embedded(body, "TIKTOK")["status"] == "needs_review"

    status, resp = post_json(server, "/review", {"id": tiktok_id, "status": "reviewed"})
    assert status == 200
    assert resp["status"] == "reviewed" and resp["reviewed_at"]

    status, body = get(server, f"/tiktok/{tiktok_id}")
    assert embedded(body, "TIKTOK")["status"] == "reviewed"
    stored = next(t for t in json.loads(library_file.read_text())["tiktoks"] if t["id"] == tiktok_id)
    assert stored["status"] == "reviewed" and stored["reviewed_at"]


def test_review_can_be_undone(server):
    tiktok_id = "tokyo-7288001122334455667"
    post_json(server, "/review", {"id": tiktok_id, "status": "reviewed"})
    status, resp = post_json(server, "/review", {"id": tiktok_id, "status": "needs_review"})
    assert status == 200
    assert resp["status"] == "needs_review" and resp["reviewed_at"] == ""


def test_review_rejects_unknown_tiktok_and_status(server):
    status, _ = post_json(server, "/review", {"id": "nope-123", "status": "reviewed"})
    assert status == 404
    status, _ = post_json(server, "/review", {"id": "tokyo-7288001122334455667", "status": "approved"})
    assert status == 400


# --- Migration ----------------------------------------------------------------

def test_legacy_list_library_is_migrated_into_city_trips(library_file):
    legacy_rows = [
        {
            "id": "tokyo-1", "url": "https://www.tiktok.com/@a/video/1", "author": "@a",
            "city": "Tokyo", "country": "Japan", "status": "needs_review", "cover_path": None,
            "data": {"video_summary": {"main_topic": "Tokyo eats"}, "places": []},
            "transcript": "", "screen_text": "", "created_at": "2026-01-01T00:00:00+00:00", "reviewed_at": None,
        },
        {
            "id": "kyoto-2", "url": "https://www.tiktok.com/@a/video/2", "author": "@a",
            "city": "Kyoto", "country": "Japan", "status": "needs_review", "cover_path": None,
            "data": {"video_summary": {"main_topic": "Kyoto walks"}, "places": []},
            "transcript": "", "screen_text": "", "created_at": "2026-01-02T00:00:00+00:00", "reviewed_at": None,
        },
    ]
    library_file.write_text(json.dumps(legacy_rows), encoding="utf-8")

    from db import db_fetch_all

    data = db_fetch_all()
    assert {t["id"] for t in data["trips"]} == {"tokyo-japan", "kyoto-japan"}
    assert {t["id"]: t["trip_id"] for t in data["tiktoks"]} == {"tokyo-1": "tokyo-japan", "kyoto-2": "kyoto-japan"}

    on_disk = json.loads(library_file.read_text(encoding="utf-8"))
    assert set(on_disk) == {"trips", "tiktoks"}
    assert len(on_disk["trips"]) == 2
