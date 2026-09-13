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
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_FILE", str(tmp_path / "library.json"))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
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


def embedded_data(body):
    """Pull the LIBRARY_DATA / TIKTOK JSON blob out of the rendered page."""
    marker = "const LIBRARY_DATA = " if "const LIBRARY_DATA = " in body else "const TIKTOK = "
    start = body.index(marker) + len(marker)
    end = body.index(";\n", start)
    return json.loads(body[start:end].replace("<\\/", "</"))


def test_home_lists_seeded_countries(server):
    status, body = get(server, "/")
    assert status == 200
    data = embedded_data(body)
    countries = {t["country"] for t in data["tiktoks"]}
    assert countries == {"Japan", "Portugal", "Mexico"}


def test_country_and_city_pages_render(server):
    status, body = get(server, "/country/Japan")
    assert status == 200
    assert "<h1>Japan</h1>" in body

    status, body = get(server, "/city/Kyoto")
    assert status == 200
    assert "<h1>Kyoto</h1>" in body
    assert 'href="/country/Japan"' in body


def test_city_with_space_in_name(server):
    status, body = get(server, "/city/Mexico%20City")
    assert status == 200
    assert "<h1>Mexico City</h1>" in body


def test_detail_page_shows_places(server):
    status, body = get(server, "/tiktok/kyoto-7301122334455667788")
    assert status == 200
    tiktok = embedded_data(body)
    assert tiktok["video_summary"]["main_topic"] == "Favorite Photo Locations in Kyoto"
    assert [p["name"] for p in tiktok["places"]][:2] == ["Kifune Shrine", "Kurama Temple"]


def test_unknown_tiktok_is_404(server):
    status, _ = get(server, "/tiktok/does-not-exist")
    assert status == 404


def test_unknown_path_is_404(server):
    status, _ = get(server, "/nope")
    assert status == 404


def test_save_then_browse(server):
    extraction = {
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
    status, saved = post_json(
        server,
        "/save",
        {"url": "https://www.tiktok.com/@x/video/111222333", "result": extraction},
    )
    assert status == 200
    assert saved == {"ok": True, "id": "seville-111222333", "city": "Seville", "country": "Spain"}

    status, body = get(server, "/country/Spain")
    assert status == 200
    cities = {t["city"] for t in embedded_data(body)["tiktoks"] if t["country"] == "Spain"}
    assert cities == {"Seville"}

    status, body = get(server, "/tiktok/seville-111222333")
    assert status == 200
    assert embedded_data(body)["status"] == "needs_review"


def test_save_requires_url_and_result(server):
    status, resp = post_json(server, "/save", {"url": ""})
    assert status == 400
    assert "error" in resp


def test_seed_file_is_not_modified_by_saves(server):
    seed_before = open(os.path.join(ROOT, "data", "seed-library.json"), encoding="utf-8").read()
    post_json(
        server,
        "/save",
        {
            "url": "https://www.tiktok.com/@x/video/999",
            "result": {"video_summary": {"destination_city": "Oslo", "destination_country": "Norway"}},
        },
    )
    seed_after = open(os.path.join(ROOT, "data", "seed-library.json"), encoding="utf-8").read()
    assert seed_before == seed_after
