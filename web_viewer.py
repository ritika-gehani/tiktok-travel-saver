#!/usr/bin/env python3
"""
TikTok Travel Saver — Web Viewer

A simple local web app to run the pipeline and watch progress in real-time.
Usage: python3 web_viewer.py
Then open http://localhost:5050 in your browser.
"""

import os
import sys
import json
import re
import time
import subprocess
import urllib.request
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote, unquote
import html as html_lib

import base64
import cv2
from google import genai
from google.genai import types
from playwright.sync_api import sync_playwright

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(PROJECT_DIR, "prompt-extract-places.txt")
TEMP_VIDEO = os.path.join(PROJECT_DIR, "temp-video.mp4")
TEMP_AUDIO = os.path.join(PROJECT_DIR, "temp-audio.mp3")

# ---------------------------------------------------------------------------
# Shared state for streaming progress to browser
# ---------------------------------------------------------------------------

pipeline_state = {
    "running": False,
    "logs": [],
    "current_step": 0,
    "total_steps": 8,
    "result": None,
    "error": None,
    "transcript": "",
    "screen_text": "",
}


# ---------------------------------------------------------------------------
# Phase 1: Hardcoded sample data for the new Home / City / Detail pages.
# This is fake data baked into the file so we can see the new layout before
# wiring up real persistence. The pipeline (run_pipeline) is unchanged — its
# results still flow through pipeline_state and are shown only on /add.
# ---------------------------------------------------------------------------

FAKE_DATA = {
    "tiktoks": [
        {
            "id": "kyoto-photo-spots",
            "city": "Kyoto",
            "country": "Japan",
            "status": "needs_review",
            "author": "@traveljapan",
            "transcript": "",
            "screen_text": "Kifune Shrine\n180 Kuramakibunecho, Sakyo Ward, Kyoto, 601-1112, Japan\n\u8cb4\u8239\u795e\u793e\n\nKurama Temple\n\u978d\u99ac\u5bfa\n\nShiragiko Inari\n\u767d\u72d0\u7a32\u8377\n6, Sagakamenoocho, Ukyo, Kyoto, Kyoto, Japan 616-8386",
            "video_summary": {
                "main_topic": "Favorite Photo Locations in Kyoto",
                "destination_city": "Kyoto",
                "destination_country": "Japan",
                "overall_vibe": ["photography", "sightseeing", "travel inspiration", "casual exploring"],
                "usefulness_for_itinerary": "high",
                "summary": "This video showcases the creator's favorite photo locations in Kyoto, Japan, providing specific addresses for each spot."
            },
            "places": [
                {
                    "name": "Kifune Shrine",
                    "place_type": "shrine",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Kifune Shrine, Kyoto, Japan",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named in English and Japanese, with a full address provided.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography", "sightseeing", "nature"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["180 Kuramakibunecho, Sakyo Ward, Kyoto, 601-1112, Japan", "\u8cb4\u8239\u795e\u793e", "Kifune Shrine"]
                },
                {
                    "name": "Kurama Temple",
                    "place_type": "temple",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Kurama Temple, Kyoto, Japan",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named in Japanese and English.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography", "sightseeing", "history"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["\u978d\u99ac\u5bfa", "Kurama Temple"]
                },
                {
                    "name": "Shiragiko Inari",
                    "place_type": "shrine",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Shiragiko Inari, Kyoto, Japan",
                    "should_create_map_pin": True,
                    "confidence": "medium",
                    "why_confidence": "Explicitly named, and an address in the same ward is provided.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography", "sightseeing"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["\u767d\u72d0\u7a32\u8377", "6, Sagakamenoocho, Ukyo, Kyoto, Kyoto, Japan 616-8386"]
                },
                {
                    "name": "Kibune River",
                    "place_type": "attraction",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Kibune River, Kyoto, Japan",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named, often a scenic spot for photography near Kifune Shrine.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography", "nature", "scenery"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["\u8cb4\u8239\u5ddd"]
                },
                {
                    "name": "Kurama Temple, West Gate",
                    "place_type": "landmark",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": "Kurama Temple",
                    "map_search_query": "Kurama Temple West Gate, Kyoto, Japan",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named in Japanese and English, specified as part of Kurama Temple.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography", "sightseeing"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["\u978d\u99ac\u5bfa\u897f\u9580", "Kurama Temple, West Gate"]
                },
                {
                    "name": "Shogaku-ji Temple",
                    "place_type": "temple",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Shogaku-ji Temple, Sagatenryujitateishicho, Ukyo, Kyoto, Kyoto, Japan",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named with a full address string.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography", "sightseeing", "history"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["Shogaku-ji Temple, Sagatenryujitateishicho, Ukyo, Kyoto, Kyoto, Japan"]
                },
                {
                    "name": None,
                    "place_type": "unknown",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "1, Saganonomiyacho, Ukyo, Kyoto, Kyoto, Japan 616-8393",
                    "should_create_map_pin": True,
                    "confidence": "low",
                    "why_confidence": "Specific address provided as a photo location, but no explicit name given.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["1, Saganonomiyacho, Ukyo, Kyoto, Kyoto, Japan 616-8393"]
                },
                {
                    "name": None,
                    "place_type": "unknown",
                    "city": "Uji",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "95-9, Oguracho Kasugamori, Uji, Kyoto, Japan 611-0042",
                    "should_create_map_pin": True,
                    "confidence": "low",
                    "why_confidence": "Specific address provided as a photo location, but no explicit name given.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["95-9, Oguracho Kasugamori, Uji, Kyoto, Japan 611-0042"]
                },
                {
                    "name": None,
                    "place_type": "unknown",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "1, Giommachiminamigawa, Higashiyama, Kyoto, Kyoto, Japan 605-0074",
                    "should_create_map_pin": True,
                    "confidence": "low",
                    "why_confidence": "Specific address provided as a photo location, but no explicit name given.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["1, Giommachiminamigawa, Higashiyama, Kyoto, Kyoto, Japan 605-0074"]
                },
                {
                    "name": None,
                    "place_type": "unknown",
                    "city": "Miyazu",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "30, Monju, Miyazu, Kyoto, Japan 626-0001",
                    "should_create_map_pin": True,
                    "confidence": "low",
                    "why_confidence": "Specific address provided as a photo location, but no explicit name given.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["One of the creator's favorite photo locations"],
                    "best_for": ["photography"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["30, Monju, Miyazu, Kyoto, Japan 626-0001"]
                }
            ],
            "non_place_notes": [
                {"type": "vibe", "text": "Mentions 'childbirth/safe delivery,' a common prayer theme at Japanese shrines.", "related_place": None},
                {"type": "activity", "text": "Mentions 'omamori' (amulets), suggesting these are noteworthy at the photo locations.", "related_place": None}
            ],
            "needs_user_review": [
                {"issue": "Specific place name for address '1, Saganonomiyacho, Ukyo, Kyoto, Kyoto, Japan 616-8393'", "reason": "The video provides an address as a 'fav photo location' but does not explicitly name the place."},
                {"issue": "Specific place name for address '95-9, Oguracho Kasugamori, Uji, Kyoto, Japan 611-0042'", "reason": "The video provides an address as a 'fav photo location' but does not explicitly name the place."},
                {"issue": "Specific place name for address '1, Giommachiminamigawa, Higashiyama, Kyoto, Kyoto, Japan 605-0074'", "reason": "The video provides an address as a 'fav photo location' but does not explicitly name the place."},
                {"issue": "Specific place name for address '30, Monju, Miyazu, Kyoto, Japan 626-0001'", "reason": "The video provides an address as a 'fav photo location' but does not explicitly name the place."}
            ]
        },
        {
            "id": "kyoto-food-tour",
            "city": "Kyoto",
            "country": "Japan",
            "status": "needs_review",
            "author": "@foodieinkyoto",
            "transcript": "Today we're trying the best matcha and street food in Kyoto. First stop, Nishiki Market for fresh tofu donuts.",
            "screen_text": "Nishiki Market\n\u9326\u5e02\u5834\n\nIppodo Tea\n\u4e00\u4fdd\u5802\u8336\u8217\n\nMalebranche Kitayama",
            "video_summary": {
                "main_topic": "Best Food Stops in Kyoto",
                "destination_city": "Kyoto",
                "destination_country": "Japan",
                "overall_vibe": ["food", "casual exploring", "local culture"],
                "usefulness_for_itinerary": "high",
                "summary": "A quick tour of three favorite food stops in Kyoto: a market, a tea house, and a matcha pastry shop."
            },
            "places": [
                {
                    "name": "Nishiki Market",
                    "place_type": "market",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Nishiki Market, Kyoto, Japan",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named in transcript and on-screen text.",
                    "source_evidence": {"caption": False, "transcript": True, "ocr": True},
                    "creator_notes": ["Best place for fresh tofu donuts"],
                    "best_for": ["food", "snacks", "local culture"],
                    "warnings_or_requirements": ["Gets crowded after 11am"],
                    "mentioned_foods_or_items": ["tofu donuts", "pickles", "yuba"],
                    "raw_mentions": ["Nishiki Market", "\u9326\u5e02\u5834"]
                },
                {
                    "name": "Ippodo Tea",
                    "place_type": "shop",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Ippodo Tea Kyoto",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named.",
                    "source_evidence": {"caption": False, "transcript": True, "ocr": True},
                    "creator_notes": ["Beautiful old tea house, sit-down tasting room upstairs"],
                    "best_for": ["tea", "souvenirs"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": ["matcha", "gyokuro"],
                    "raw_mentions": ["Ippodo Tea", "\u4e00\u4fdd\u5802\u8336\u8217"]
                },
                {
                    "name": "Malebranche Kitayama",
                    "place_type": "shop",
                    "city": "Kyoto",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Malebranche Kitayama, Kyoto",
                    "should_create_map_pin": True,
                    "confidence": "medium",
                    "why_confidence": "Explicitly named on-screen, but creator did not give detailed notes.",
                    "source_evidence": {"caption": False, "transcript": False, "ocr": True},
                    "creator_notes": ["Famous for cha-no-ka matcha cookies"],
                    "best_for": ["dessert", "souvenirs"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": ["matcha cookies", "cha-no-ka"],
                    "raw_mentions": ["Malebranche Kitayama"]
                }
            ],
            "non_place_notes": [
                {"type": "tip", "text": "Go early to beat the lunch rush at Nishiki Market.", "related_place": "Nishiki Market"}
            ],
            "needs_user_review": [
                {"issue": "Confirm Malebranche Kitayama branch", "reason": "Creator showed the Kitayama branch but Malebranche has multiple locations in Kyoto."}
            ]
        },
        {
            "id": "osaka-street-food",
            "city": "Osaka",
            "country": "Japan",
            "status": "needs_review",
            "author": "@osakaeats",
            "transcript": "Welcome to Dotonbori, the heart of Osaka street food. We're hitting Kukuru for takoyaki and then Ichiran for late-night ramen.",
            "screen_text": "Dotonbori\n\u9053\u9813\u5800\n\nKukuru\n\nIchiran Ramen",
            "video_summary": {
                "main_topic": "Osaka Street Food Crawl",
                "destination_city": "Osaka",
                "destination_country": "Japan",
                "overall_vibe": ["food", "nightlife", "casual exploring"],
                "usefulness_for_itinerary": "high",
                "summary": "A short crawl through Osaka's Dotonbori district covering takoyaki and late-night ramen."
            },
            "places": [
                {
                    "name": "Dotonbori",
                    "place_type": "neighborhood",
                    "city": "Osaka",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Dotonbori, Osaka, Japan",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named in transcript and on-screen text.",
                    "source_evidence": {"caption": False, "transcript": True, "ocr": True},
                    "creator_notes": ["Heart of Osaka street food"],
                    "best_for": ["food", "nightlife", "atmosphere"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": ["takoyaki", "okonomiyaki"],
                    "raw_mentions": ["Dotonbori", "\u9053\u9813\u5800"]
                },
                {
                    "name": "Kukuru",
                    "place_type": "restaurant",
                    "city": "Osaka",
                    "country": "Japan",
                    "parent_place": "Dotonbori",
                    "map_search_query": "Kukuru takoyaki Dotonbori, Osaka",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named.",
                    "source_evidence": {"caption": False, "transcript": True, "ocr": True},
                    "creator_notes": ["Famous for takoyaki with extra-creamy filling"],
                    "best_for": ["snacks", "food"],
                    "warnings_or_requirements": ["Long line during dinner"],
                    "mentioned_foods_or_items": ["takoyaki"],
                    "raw_mentions": ["Kukuru"]
                },
                {
                    "name": "Ichiran Ramen",
                    "place_type": "restaurant",
                    "city": "Osaka",
                    "country": "Japan",
                    "parent_place": None,
                    "map_search_query": "Ichiran Ramen Dotonbori, Osaka",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named for late-night ramen.",
                    "source_evidence": {"caption": False, "transcript": True, "ocr": True},
                    "creator_notes": ["Open late, solo-style ramen booths"],
                    "best_for": ["food", "late night"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": ["tonkotsu ramen"],
                    "raw_mentions": ["Ichiran Ramen"]
                }
            ],
            "non_place_notes": [],
            "needs_user_review": []
        },
        {
            "id": "rome-must-see",
            "city": "Rome",
            "country": "Italy",
            "status": "needs_review",
            "author": "@romewithme",
            "transcript": "Three places you cannot skip in Rome. Number one, the Colosseum. Number two, Trastevere for dinner. Number three, an early morning walk around the Pantheon.",
            "screen_text": "Colosseum\nTrastevere\nPantheon",
            "video_summary": {
                "main_topic": "3 Must-See Spots in Rome",
                "destination_city": "Rome",
                "destination_country": "Italy",
                "overall_vibe": ["sightseeing", "history", "food"],
                "usefulness_for_itinerary": "high",
                "summary": "Quick top-3 list of essentials in Rome: an iconic landmark, a neighborhood for dinner, and a sunrise walk."
            },
            "places": [
                {
                    "name": "Colosseum",
                    "place_type": "landmark",
                    "city": "Rome",
                    "country": "Italy",
                    "parent_place": None,
                    "map_search_query": "Colosseum, Rome, Italy",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named.",
                    "source_evidence": {"caption": False, "transcript": True, "ocr": True},
                    "creator_notes": ["Book skip-the-line tickets in advance"],
                    "best_for": ["sightseeing", "history", "photography"],
                    "warnings_or_requirements": ["Buy tickets ahead of time"],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["Colosseum"]
                },
                {
                    "name": "Trastevere",
                    "place_type": "neighborhood",
                    "city": "Rome",
                    "country": "Italy",
                    "parent_place": None,
                    "map_search_query": "Trastevere, Rome, Italy",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named as a dinner destination.",
                    "source_evidence": {"caption": False, "transcript": True, "ocr": True},
                    "creator_notes": ["Best neighborhood for dinner; cobblestone streets and trattorias"],
                    "best_for": ["food", "nightlife", "atmosphere"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": ["cacio e pepe", "carbonara"],
                    "raw_mentions": ["Trastevere"]
                },
                {
                    "name": "Pantheon",
                    "place_type": "landmark",
                    "city": "Rome",
                    "country": "Italy",
                    "parent_place": None,
                    "map_search_query": "Pantheon, Rome, Italy",
                    "should_create_map_pin": True,
                    "confidence": "high",
                    "why_confidence": "Explicitly named.",
                    "source_evidence": {"caption": False, "transcript": True, "ocr": True},
                    "creator_notes": ["Go early in the morning to avoid crowds"],
                    "best_for": ["sightseeing", "history", "photography"],
                    "warnings_or_requirements": [],
                    "mentioned_foods_or_items": [],
                    "raw_mentions": ["Pantheon"]
                }
            ],
            "non_place_notes": [],
            "needs_user_review": [
                {"issue": "Specific Trastevere restaurant", "reason": "Creator recommends Trastevere for dinner but does not name a specific restaurant."}
            ]
        }
    ]
}


def reset_state():
    pipeline_state["running"] = False
    pipeline_state["logs"] = []
    pipeline_state["current_step"] = 0
    pipeline_state["result"] = None
    pipeline_state["error"] = None
    pipeline_state["transcript"] = ""
    pipeline_state["screen_text"] = ""


def log(msg, step=None):
    if step is not None:
        pipeline_state["current_step"] = step
    pipeline_state["logs"].append(msg)


# ---------------------------------------------------------------------------
# Pipeline functions (same logic as process_tiktok.py, with log() calls)
# ---------------------------------------------------------------------------

def load_env():
    env_path = os.path.join(PROJECT_DIR, ".env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()


def gemini_call(client, prompt, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text
        except Exception as e:
            if attempt < max_retries:
                log(f"⚠️ Gemini call failed (attempt {attempt}/{max_retries}): {e}")
                log("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                raise


def cleanup_temp_files():
    for filepath in [TEMP_VIDEO, TEMP_AUDIO]:
        if os.path.exists(filepath):
            os.remove(filepath)


def resolve_short_url(url):
    """Follow redirects to expand short TikTok links (e.g. tiktok.com/t/...)."""
    if "/t/" not in url:
        return url
    log("Short link detected — resolving redirect...")
    req = urllib.request.Request(url, method="HEAD", headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            resolved = resp.url
        log(f"Resolved to: {resolved}")
        return resolved
    except Exception as e:
        log(f"⚠️ Could not resolve short link: {e}")
        return url


def run_pipeline(tiktok_url):
    reset_state()
    pipeline_state["running"] = True
    tiktok_url = resolve_short_url(tiktok_url)
    carousel = "/photo/" in tiktok_url

    try:
        load_env()
        google_key = os.environ.get("GOOGLE_API_KEY")
        assemblyai_key = os.environ.get("ASSEMBLYAI_API_KEY")

        if not google_key:
            raise Exception("GOOGLE_API_KEY not found in .env file.")
        if not carousel and not assemblyai_key:
            raise Exception("ASSEMBLYAI_API_KEY not found in .env file.")

        gemini_client = genai.Client(
            api_key=google_key,
            http_options=types.HttpOptions(api_version='v1')
        )

        if carousel:
            # =============================================================
            # Photo carousel pipeline
            # =============================================================
            log("Detected photo carousel — using image-only pipeline", step=1)
            log("Fetching carousel data with headless browser (Playwright)...")
            log("Loading TikTok page (this takes ~10 seconds)...")

            caption, author, image_urls = "", "", []
            scrape_ok = False
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled"]
                    )
                    context = browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        )
                    )
                    pw_page = context.new_page()
                    pw_page.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                    )
                    pw_page.goto(tiktok_url, wait_until="networkidle", timeout=30000)

                    body_text = pw_page.inner_text("body")
                    all_imgs = pw_page.eval_on_selector_all("img", "els => els.map(e => e.src)")
                    browser.close()

                # Parse author (appears as "username_\n· 1-N" in body text)
                author_match = re.search(r'^([^\s]+)\s*\n\s*·\s*1-\d+', body_text, re.MULTILINE)
                if author_match:
                    author = author_match.group(1).rstrip("_")

                # Caption = deduplicated hashtags from visible text
                hashtags = re.findall(r'#\w+', body_text)
                caption = " ".join(dict.fromkeys(hashtags))

                # Images = photomode img src URLs, deduplicated
                seen = set()
                for src in all_imgs:
                    if "photomode-image" in src and src not in seen:
                        seen.add(src)
                        image_urls.append(src)

                scrape_ok = bool(image_urls)
                if not scrape_ok:
                    log("⚠️ No carousel images found in rendered page.")
            except Exception as e:
                log(f"⚠️ Playwright scraping failed: {e}")

            if not scrape_ok:
                log("Falling back to caption-only mode (no images available)...")
                caption, author = caption or "", author or ""

            log(f"Caption: {caption[:100]}{'...' if len(caption) > 100 else ''}")
            log(f"Author: {author}")
            log(f"Images found: {len(image_urls)}")

            # Step 2: Download images
            _img_headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            log(f"Downloading {len(image_urls)} carousel images...", step=2)
            images = []
            for i, img_url in enumerate(image_urls):
                try:
                    req = urllib.request.Request(img_url, headers=_img_headers)
                    with urllib.request.urlopen(req) as resp:
                        img_bytes = resp.read()
                    images.append({"index": i + 1, "jpeg_bytes": img_bytes})
                    log(f"Image {i + 1}/{len(image_urls)}: {len(img_bytes) / 1024:.0f} KB")
                except Exception as e:
                    log(f"⚠️ Failed to download image {i + 1}: {e}")
            log(f"Downloaded {len(images)}/{len(image_urls)} images")

            # Step 3: Skip audio
            log("Skipping audio transcription (photo carousel has no audio)", step=3)
            transcript = ""
            pipeline_state["transcript"] = transcript

            # Step 4-5: Send images to Gemini Vision
            log("Reading on-screen text from carousel images with Gemini Vision...", step=4)
            if not images:
                log("No images to analyze.")
                screen_text = ""
            else:
                contents = []
                for img in images:
                    raw_bytes = img["jpeg_bytes"]
                    if raw_bytes[:4] == b'RIFF':
                        mime = "image/webp"
                    elif raw_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                        mime = "image/png"
                    else:
                        mime = "image/jpeg"
                    contents.append(types.Part.from_bytes(data=raw_bytes, mime_type=mime))

                contents.append(types.Part.from_text(text="""These are images from a TikTok photo carousel (slideshow) about travel.

Please read ALL on-screen text visible in these images. This includes:
- Place names, restaurant names, shop names
- Descriptions, subtitles, captions overlaid on the images
- Prices, menu items, tips
- Any other readable text, including stylized or decorative text

Ignore TikTok UI elements (like/share buttons, usernames, follower counts).
Ignore text from map screenshots, Google Maps, navigation apps, or any map-like interface.

Return the text organized as bullet points, grouped by what appears to be the same place or topic. Remove duplicates. Include the slide number if helpful.

Return only the extracted text, nothing else."""))

                log(f"Sending {len(images)} images to Gemini Vision...")
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=contents
                )
                screen_text = response.text
                log(f"Extracted {len(screen_text)} chars of on-screen text")
            pipeline_state["screen_text"] = screen_text

        else:
            # =============================================================
            # Normal video pipeline
            # =============================================================

            # Step 1: Caption
            log("Fetching caption from TikTok...", step=1)
            oembed_url = f"https://www.tiktok.com/oembed?url={tiktok_url}"
            with urllib.request.urlopen(oembed_url) as response:
                oembed_data = json.loads(response.read())
            caption = oembed_data.get("title", "")
            author = oembed_data.get("author_name", "")
            log(f"Caption: {caption[:100]}{'...' if len(caption) > 100 else ''}")
            log(f"Author: {author}")

            # Step 2: Download
            log("Downloading TikTok video...", step=2)
            result = subprocess.run(
                ["yt-dlp", "-o", TEMP_VIDEO, "--force-overwrites", tiktok_url],
                capture_output=True, text=True, cwd=PROJECT_DIR
            )
            if result.returncode != 0:
                raise Exception(f"Video download failed: {result.stderr[:200]}")
            video_size = os.path.getsize(TEMP_VIDEO) / (1024 * 1024)
            log(f"Video downloaded ({video_size:.1f} MB)")

            log("Extracting audio...")
            result = subprocess.run(
                ["yt-dlp", "-x", "--audio-format", "mp3",
                 "-o", TEMP_AUDIO, "--force-overwrites", tiktok_url],
                capture_output=True, text=True, cwd=PROJECT_DIR
            )
            if result.returncode != 0:
                raise Exception(f"Audio extraction failed: {result.stderr[:200]}")
            audio_size = os.path.getsize(TEMP_AUDIO) / (1024 * 1024)
            log(f"Audio extracted ({audio_size:.1f} MB)")

            # Step 3: Transcribe
            log("Transcribing audio with AssemblyAI...", step=3)
            base_url = "https://api.assemblyai.com"

            def api_request(method, path, data=None, binary=None):
                headers = {"Authorization": assemblyai_key}
                if data is not None:
                    body = json.dumps(data).encode()
                    headers["Content-Type"] = "application/json"
                elif binary is not None:
                    body = binary
                    headers["Content-Type"] = "application/octet-stream"
                else:
                    body = None
                req = urllib.request.Request(base_url + path, data=body, headers=headers, method=method)
                with urllib.request.urlopen(req) as r:
                    return json.loads(r.read())

            log("Uploading audio...")
            with open(TEMP_AUDIO, "rb") as f:
                audio_data = f.read()
            upload_result = api_request("POST", "/v2/upload", binary=audio_data)
            upload_url = upload_result["upload_url"]
            log("Uploaded. Requesting transcription...")

            transcript_result = api_request("POST", "/v2/transcript", data={
                "audio_url": upload_url,
                "speech_models": ["universal-2"]
            })
            transcript_id = transcript_result["id"]

            log("Waiting for transcription (15-30 seconds)...")
            while True:
                poll = api_request("GET", f"/v2/transcript/{transcript_id}")
                status = poll["status"]
                if status == "completed":
                    break
                elif status == "error":
                    raise Exception(f"Transcription failed: {poll.get('error')}")
                time.sleep(3)

            transcript = poll.get("text") or ""
            if not transcript.strip():
                log("⚠️ No spoken transcript detected. Continuing with caption + OCR only.")
                transcript = ""
            else:
                log(f"Transcription complete ({len(transcript.split())} words)")
            pipeline_state["transcript"] = transcript

            # Step 4: Extract frames
            log("Extracting video frames...", step=4)
            video = cv2.VideoCapture(TEMP_VIDEO)
            fps = video.get(cv2.CAP_PROP_FPS)
            total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps
            sample_interval = 3
            log(f"Video: {duration:.1f}s, {fps:.0f} fps — sampling 1 frame every {sample_interval}s")

            frames = []
            frame_count = 0
            frames_to_skip = int(fps * sample_interval)
            while True:
                success, frame = video.read()
                if not success:
                    break
                if frame_count % frames_to_skip == 0:
                    timestamp = round(frame_count / fps, 2)
                    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    frames.append({
                        "timestamp": timestamp,
                        "jpeg_bytes": jpeg.tobytes()
                    })
                frame_count += 1
            video.release()
            log(f"Extracted {len(frames)} frames")

            # Step 5: Read on-screen text with Gemini Vision
            log("Reading on-screen text with Gemini Vision...", step=5)
            if not frames:
                log("No frames to analyze.")
                screen_text = ""
            else:
                contents = []
                for f in frames:
                    contents.append(types.Part.from_bytes(data=f["jpeg_bytes"], mime_type="image/jpeg"))
                contents.append(types.Part.from_text(text="""These are frames from a TikTok travel video, sampled every few seconds.

Please read ALL on-screen text visible in these frames. This includes:
- Place names, restaurant names, shop names
- Descriptions, subtitles, captions overlaid on the video
- Prices, menu items, tips
- Any other readable text, including stylized or decorative text

Ignore TikTok UI elements (like/share buttons, usernames, follower counts).
Ignore text from map screenshots, Google Maps, navigation apps, or any map-like interface (hotel names, street labels, transit info visible on maps are NOT real recommendations from the creator).

Return the text organized as bullet points, grouped by what appears to be the same place or topic. Remove duplicates (same text across multiple frames). Include the approximate timestamp if helpful.

Return only the extracted text, nothing else."""))

                log(f"Sending {len(frames)} frames to Gemini Vision...")
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=contents
                )
                screen_text = response.text
                log(f"Extracted {len(screen_text)} chars of on-screen text")
            pipeline_state["screen_text"] = screen_text

        # ================================================================
        # Steps 6-8 are shared by both pipelines
        # ================================================================

        # Step 6: Combine
        log("Combining all sources...", step=6)
        log(f"Caption: {len(caption)} chars | Transcript: {len(transcript)} chars | Screen text: {len(screen_text)} chars")

        # Step 7: Extract places
        log("Extracting places with Gemini (15-30 seconds)...", step=7)
        with open(PROMPT_FILE, "r") as f:
            prompt_template = f.read()
        prompt = prompt_template.replace("{CAPTION}", caption if caption else "(No caption available)")
        prompt = prompt.replace("{TRANSCRIPT}", transcript if transcript else "(No spoken transcript available)")
        prompt = prompt.replace("{OCR_TEXT}", screen_text if screen_text else "(No on-screen text detected)")

        raw = gemini_call(gemini_client, prompt).strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\s*\n?', '', raw)
            raw = re.sub(r'\n?```\s*$', '', raw)

        extraction = json.loads(raw)
        log("JSON parsed successfully!")

        # Step 8: Done
        log("Done!", step=8)
        pipeline_state["result"] = extraction

        # Cleanup
        cleanup_temp_files()
        log("Temporary files cleaned up.")

    except Exception as e:
        pipeline_state["error"] = str(e)
        log(f"❌ ERROR: {e}")
        cleanup_temp_files()
    finally:
        pipeline_state["running"] = False


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------

# Shared dark-mode styles used by the Home, City, and Detail pages. Inlined into
# each page's <style> via a {{BASE_CSS}} placeholder filled in by the server.
BASE_CSS = """
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f0f; color: #e0e0e0; min-height: 100vh; }
  a { color: inherit; text-decoration: none; }
  .container { max-width: 900px; margin: 0 auto; padding: 24px; }

  /* Page header (title row) */
  .page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
  .page-header h1 { font-size: 28px; color: #fff; }
  .subtitle { color: #888; margin-bottom: 24px; font-size: 14px; }

  /* Back link */
  .back-link { display: inline-block; color: #fe2c55; font-size: 14px; margin-bottom: 16px; }
  .back-link:hover { text-decoration: underline; }

  /* "+" Add button (in header) */
  .btn-add { display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; border-radius: 50%; background: #fe2c55; color: #fff; font-size: 24px; font-weight: 600; line-height: 1; }
  .btn-add:hover { background: #e0274d; }

  /* Cards (shared) */
  .card { background: #1a1a1a; border: 1px solid #282828; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
  .card h2 { font-size: 18px; color: #fff; margin-bottom: 12px; }
  .card h3 { font-size: 15px; color: #fe2c55; margin: 14px 0 8px; }

  /* Tags */
  .meta-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  .tag { background: #282828; color: #ccc; padding: 4px 10px; border-radius: 20px; font-size: 12px; }
  .tag.vibe { background: #2a1a2e; color: #d4a0e0; }
  .tag.high { background: #1a2e1a; color: #4cd964; }
  .tag.medium { background: #2e2a1a; color: #f5a623; }
  .tag.low { background: #2e1a1a; color: #ff6b6b; }
  .tag.review { background: #2e1a1a; color: #ff6b6b; font-weight: 600; }

  /* Empty state */
  .empty-state { text-align: center; padding: 80px 20px; color: #666; font-size: 16px; }
"""

# Home page — list of country cards. Empty state if no TikToks exist.
HTML_HOME = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TikTok Travel Saver</title>
<style>
{{BASE_CSS}}
  /* Home-page-specific */
  .country-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
  .country-card { background: #1a1a1a; border: 1px solid #282828; border-radius: 12px; padding: 24px; cursor: pointer; transition: transform 0.15s ease, border-color 0.15s ease; display: block; }
  .country-card:hover { transform: translateY(-2px); border-color: #fe2c55; }
  .country-icon { font-size: 28px; margin-bottom: 12px; }
  .country-name { font-size: 20px; font-weight: 600; color: #fff; margin-bottom: 4px; }
  .country-cities { font-size: 13px; color: #888; margin-bottom: 12px; }
  .country-count { font-size: 13px; color: #fe2c55; font-weight: 600; }
</style>
</head>
<body>
<div class="container">
  <header class="page-header">
    <h1>🗺️ TikTok Travel Saver</h1>
    <a href="/add" class="btn-add" title="Add a new TikTok">+</a>
  </header>

  <div id="countryGrid" class="country-grid"></div>
  <div id="emptyState" class="empty-state" style="display:none">No trips yet. Click + to add your first TikTok.</div>
</div>

<script>
const FAKE_DATA = {{DATA_JSON}};

// Group TikToks by country. Each group also tracks the unique cities inside.
function renderHome() {
  const groups = {};
  for (const t of FAKE_DATA.tiktoks) {
    if (!groups[t.country]) groups[t.country] = { country: t.country, cities: new Set(), count: 0 };
    groups[t.country].cities.add(t.city);
    groups[t.country].count++;
  }
  const countries = Object.values(groups);
  const grid = document.getElementById('countryGrid');
  const empty = document.getElementById('emptyState');
  if (countries.length === 0) {
    empty.style.display = 'block';
    return;
  }
  let html = '';
  for (const c of countries) {
    const url = '/country/' + encodeURIComponent(c.country);
    const cityCount = c.cities.size;
    const cityLabel = cityCount === 1 ? '1 city' : cityCount + ' cities';
    const tiktokLabel = c.count === 1 ? '1 TikTok' : c.count + ' TikToks';
    html += `<a href="${url}" class="country-card">
      <div class="country-icon">🌏</div>
      <div class="country-name">${c.country}</div>
      <div class="country-cities">${cityLabel}</div>
      <div class="country-count">${tiktokLabel}</div>
    </a>`;
  }
  grid.innerHTML = html;
}
renderHome();
</script>
</body>
</html>
"""

# Country page — list of city cards filtered to one country.
HTML_COUNTRY = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{COUNTRY_NAME}} — TikTok Travel Saver</title>
<style>
{{BASE_CSS}}
  /* Country-page-specific */
  .city-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
  .city-card { background: #1a1a1a; border: 1px solid #282828; border-radius: 12px; padding: 24px; cursor: pointer; transition: transform 0.15s ease, border-color 0.15s ease; display: block; }
  .city-card:hover { transform: translateY(-2px); border-color: #fe2c55; }
  .city-icon { font-size: 28px; margin-bottom: 12px; }
  .city-name { font-size: 20px; font-weight: 600; color: #fff; margin-bottom: 4px; }
  .city-count { font-size: 13px; color: #fe2c55; font-weight: 600; }
</style>
</head>
<body>
<div class="container">
  <a href="/" class="back-link">← Back</a>
  <header class="page-header">
    <h1>{{COUNTRY_NAME}}</h1>
  </header>

  <div id="cityGrid" class="city-grid"></div>
  <div id="emptyState" class="empty-state" style="display:none">No cities for this country yet.</div>
</div>

<script>
const FAKE_DATA = {{DATA_JSON}};
const COUNTRY_NAME = {{COUNTRY_NAME_JSON}};

function renderCountry() {
  const groups = {};
  for (const t of FAKE_DATA.tiktoks) {
    if (t.country !== COUNTRY_NAME) continue;
    if (!groups[t.city]) groups[t.city] = { city: t.city, count: 0 };
    groups[t.city].count++;
  }
  const cities = Object.values(groups);
  const grid = document.getElementById('cityGrid');
  const empty = document.getElementById('emptyState');
  if (cities.length === 0) {
    empty.style.display = 'block';
    return;
  }
  let html = '';
  for (const c of cities) {
    const url = '/city/' + encodeURIComponent(c.city);
    const label = c.count === 1 ? '1 TikTok' : c.count + ' TikToks';
    html += `<a href="${url}" class="city-card">
      <div class="city-icon">📍</div>
      <div class="city-name">${c.city}</div>
      <div class="city-count">${label}</div>
    </a>`;
  }
  grid.innerHTML = html;
}
renderCountry();
</script>
</body>
</html>
"""

# City page — list of TikTok cards filtered to one city.
HTML_CITY = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{CITY_NAME}} — TikTok Travel Saver</title>
<style>
{{BASE_CSS}}
  /* City-page-specific */
  .tiktok-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
  .tiktok-card { background: #1a1a1a; border: 1px solid #282828; border-radius: 12px; padding: 18px; cursor: pointer; transition: transform 0.15s ease, border-color 0.15s ease; display: block; }
  .tiktok-card:hover { transform: translateY(-2px); border-color: #fe2c55; }
  .tiktok-thumb { background: #111; border: 1px solid #222; border-radius: 8px; height: 140px; display: flex; align-items: center; justify-content: center; color: #444; font-size: 36px; margin-bottom: 12px; }
  .tiktok-title { font-size: 16px; font-weight: 600; color: #fff; margin-bottom: 6px; line-height: 1.3; }
  .tiktok-author { font-size: 12px; color: #888; margin-bottom: 10px; }
  .tiktok-meta { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .tiktok-places { font-size: 12px; color: #aaa; }
</style>
</head>
<body>
<div class="container">
  <a href="{{BACK_HREF}}" class="back-link">← Back to {{BACK_LABEL}}</a>
  <header class="page-header">
    <h1>{{CITY_NAME}}</h1>
  </header>

  <div id="tiktokGrid" class="tiktok-grid"></div>
  <div id="emptyState" class="empty-state" style="display:none">No TikToks for this city yet.</div>
</div>

<script>
const FAKE_DATA = {{DATA_JSON}};
const CITY_NAME = {{CITY_NAME_JSON}};

function renderCity() {
  const filtered = FAKE_DATA.tiktoks.filter(t => t.city === CITY_NAME);
  const grid = document.getElementById('tiktokGrid');
  const empty = document.getElementById('emptyState');
  if (filtered.length === 0) {
    empty.style.display = 'block';
    return;
  }
  let html = '';
  for (const t of filtered) {
    const title = (t.video_summary && t.video_summary.main_topic) || 'Untitled';
    const author = t.author || '';
    const placeCount = (t.places || []).length;
    const placeLabel = placeCount === 1 ? '1 place' : placeCount + ' places';
    const url = '/tiktok/' + encodeURIComponent(t.id);
    const reviewBadge = t.status === 'needs_review' ? '<span class="tag review">Needs Review</span>' : '';
    html += `<a href="${url}" class="tiktok-card">
      <div class="tiktok-thumb">🎬</div>
      <div class="tiktok-title">${title}</div>
      <div class="tiktok-author">${author}</div>
      <div class="tiktok-meta">
        <span class="tiktok-places">${placeLabel}</span>
        ${reviewBadge}
      </div>
    </a>`;
  }
  grid.innerHTML = html;
}
renderCity();
</script>
</body>
</html>
"""

# Detail page — full extracted info for one TikTok. Reuses the same render logic
# that the existing HTML_PAGE uses for results, but reads data from a server-injected
# <script> tag instead of polling /status.
HTML_DETAIL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TikTok Detail — TikTok Travel Saver</title>
<style>
{{BASE_CSS}}
  /* Detail-page-specific (mirrors HTML_PAGE results section) */
  .place-card { background: #111; border: 1px solid #222; border-radius: 10px; padding: 16px; margin-bottom: 12px; }
  .place-name { font-size: 16px; font-weight: 600; color: #fff; }
  .place-type { font-size: 12px; color: #888; margin-left: 8px; }
  .place-parent { font-size: 12px; color: #666; }
  .place-detail { font-size: 13px; color: #aaa; margin-top: 6px; line-height: 1.5; }
  .place-detail strong { color: #ccc; }
  .evidence { display: flex; gap: 6px; margin-top: 8px; }
  .ev { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
  .ev.on { background: #1a2e1a; color: #4cd964; }
  .ev.off { background: #1a1a1a; color: #555; }

  .note-item { padding: 8px 0; border-bottom: 1px solid #222; font-size: 13px; color: #aaa; }
  .note-item:last-child { border-bottom: none; }
  .note-type { color: #fe2c55; font-weight: 600; text-transform: uppercase; font-size: 11px; margin-right: 6px; }
  .review-item { padding: 8px 0; border-bottom: 1px solid #222; font-size: 13px; }
  .review-item:last-child { border-bottom: none; }
  .review-issue { color: #f5a623; font-weight: 600; }
  .review-reason { color: #888; }

  .summary-text { color: #bbb; font-size: 14px; line-height: 1.6; }
  .map-query { font-size: 12px; color: #666; font-family: monospace; margin-top: 4px; }
  .raw-data-content { background: #111; border: 1px solid #222; border-radius: 8px; padding: 14px; margin-top: 8px; font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace; font-size: 12px; line-height: 1.7; color: #aaa; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto; }
  .raw-data-empty { color: #555; font-style: italic; }
</style>
</head>
<body>
<div class="container">
  <a href="{{BACK_HREF}}" class="back-link">← Back to {{CITY_NAME}}</a>
  <div id="results"></div>
</div>

<script>
const TIKTOK = {{DATA_JSON}};

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : text;
  return div.innerHTML;
}

function renderResults(r, transcript, screenText) {
  const el = document.getElementById('results');
  let html = '';

  // Video summary
  const s = r.video_summary || {};
  html += `<div class="card">
    <h2>${escapeHtml(s.main_topic) || 'Video Summary'}</h2>
    <p class="summary-text">${escapeHtml(s.summary) || ''}</p>
    <div class="meta-row" style="margin-top:10px">
      <span class="tag">${escapeHtml(s.destination_city) || '?'}, ${escapeHtml(s.destination_country) || '?'}</span>
      <span class="tag ${s.usefulness_for_itinerary || ''}">${escapeHtml(s.usefulness_for_itinerary) || '?'} usefulness</span>
      ${(s.overall_vibe || []).map(v => `<span class="tag vibe">${escapeHtml(v)}</span>`).join('')}
    </div>
  </div>`;

  // Raw data: Transcript + Screen Text
  html += `<div class="card">
    <h2>🔍 Raw Extracted Data</h2>
    <h3>Audio Transcript</h3>
    ${transcript ? `<div class="raw-data-content">${escapeHtml(transcript)}</div>` : '<div class="raw-data-empty">No spoken transcript detected (music-only video)</div>'}
    <h3 style="margin-top:16px">On-Screen Text (Gemini Vision)</h3>
    ${screenText ? `<div class="raw-data-content">${escapeHtml(screenText)}</div>` : '<div class="raw-data-empty">No on-screen text detected</div>'}
  </div>`;

  // Places
  const places = r.places || [];
  html += `<div class="card"><h2>📍 Places (${places.length})</h2>`;
  for (const p of places) {
    const parentTxt = p.parent_place ? `<span class="place-parent">inside ${escapeHtml(p.parent_place)}</span>` : '';
    const confClass = p.confidence || 'medium';
    html += `<div class="place-card">
      <div>
        <span class="place-name">${escapeHtml(p.name) || '(unnamed)'}</span>
        <span class="place-type">${escapeHtml(p.place_type) || ''}</span>
        ${parentTxt}
        <span class="tag ${confClass}" style="margin-left:8px;font-size:11px">${escapeHtml(p.confidence)}</span>
      </div>`;

    if (p.creator_notes && p.creator_notes.length) {
      html += `<div class="place-detail">${p.creator_notes.map(n => `• ${escapeHtml(n)}`).join('<br>')}</div>`;
    }
    if (p.mentioned_foods_or_items && p.mentioned_foods_or_items.length) {
      html += `<div class="place-detail"><strong>Food/items:</strong> ${p.mentioned_foods_or_items.map(escapeHtml).join(', ')}</div>`;
    }
    if (p.warnings_or_requirements && p.warnings_or_requirements.length) {
      html += `<div class="place-detail" style="color:#f5a623"><strong>⚠️</strong> ${p.warnings_or_requirements.map(escapeHtml).join('; ')}</div>`;
    }
    if (p.best_for && p.best_for.length) {
      html += `<div class="meta-row" style="margin-top:8px">${p.best_for.map(b => `<span class="tag">${escapeHtml(b)}</span>`).join('')}</div>`;
    }

    const se = p.source_evidence || {};
    html += `<div class="evidence">
      <span class="ev ${se.caption ? 'on' : 'off'}">caption</span>
      <span class="ev ${se.transcript ? 'on' : 'off'}">transcript</span>
      <span class="ev ${se.ocr ? 'on' : 'off'}">ocr</span>
    </div>`;
    html += `<div class="map-query">🔍 ${escapeHtml(p.map_search_query) || ''}</div>`;
    html += `</div>`;
  }
  html += `</div>`;

  // Non-place notes
  const notes = r.non_place_notes || [];
  if (notes.length) {
    html += `<div class="card"><h2>📝 Notes (${notes.length})</h2>`;
    for (const n of notes) {
      const related = n.related_place ? ` → <em>${escapeHtml(n.related_place)}</em>` : '';
      html += `<div class="note-item"><span class="note-type">${escapeHtml(n.type) || '?'}</span>${escapeHtml(n.text) || ''}${related}</div>`;
    }
    html += `</div>`;
  }

  // Needs review
  const reviews = r.needs_user_review || [];
  if (reviews.length) {
    html += `<div class="card"><h2>⚠️ Needs Review (${reviews.length})</h2>`;
    for (const rv of reviews) {
      html += `<div class="review-item"><span class="review-issue">${escapeHtml(rv.issue) || '?'}</span><br><span class="review-reason">${escapeHtml(rv.reason) || ''}</span></div>`;
    }
    html += `</div>`;
  }

  el.innerHTML = html;
}

renderResults(TIKTOK, TIKTOK.transcript || '', TIKTOK.screen_text || '');
</script>
</body>
</html>
"""


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TikTok Travel Saver</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f0f; color: #e0e0e0; min-height: 100vh; }
  .container { max-width: 900px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 28px; margin-bottom: 4px; color: #fff; }
  .subtitle { color: #888; margin-bottom: 24px; font-size: 14px; }

  /* Input */
  .input-row { display: flex; gap: 10px; margin-bottom: 24px; }
  input[type=text] { flex: 1; padding: 12px 16px; border-radius: 10px; border: 1px solid #333; background: #1a1a1a; color: #fff; font-size: 15px; outline: none; }
  input[type=text]:focus { border-color: #fe2c55; }
  button { padding: 12px 24px; border-radius: 10px; border: none; background: #fe2c55; color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; white-space: nowrap; }
  button:hover { background: #e0274d; }
  button:disabled { background: #444; cursor: not-allowed; }

  /* Progress bar */
  .progress-container { margin-bottom: 20px; display: none; }
  .progress-bar { height: 6px; background: #222; border-radius: 3px; overflow: hidden; }
  .progress-fill { height: 100%; background: linear-gradient(90deg, #fe2c55, #ff6b81); border-radius: 3px; transition: width 0.4s ease; width: 0%; }
  .step-label { font-size: 13px; color: #888; margin-top: 6px; }

  /* Log */
  .log-box { background: #1a1a1a; border: 1px solid #282828; border-radius: 10px; padding: 16px; margin-bottom: 24px; max-height: 300px; overflow-y: auto; font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace; font-size: 13px; line-height: 1.7; display: none; }
  .log-line { color: #aaa; }
  .log-line.step { color: #fe2c55; font-weight: 600; margin-top: 8px; }
  .log-line.warn { color: #f5a623; }
  .log-line.error { color: #ff4444; }
  .log-line.done { color: #4cd964; font-weight: 600; }

  /* Results */
  .results { display: none; }
  .card { background: #1a1a1a; border: 1px solid #282828; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
  .card h2 { font-size: 18px; color: #fff; margin-bottom: 12px; }
  .card h3 { font-size: 15px; color: #fe2c55; margin: 14px 0 8px; }
  .meta-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  .tag { background: #282828; color: #ccc; padding: 4px 10px; border-radius: 20px; font-size: 12px; }
  .tag.vibe { background: #2a1a2e; color: #d4a0e0; }
  .tag.high { background: #1a2e1a; color: #4cd964; }
  .tag.medium { background: #2e2a1a; color: #f5a623; }
  .tag.low { background: #2e1a1a; color: #ff6b6b; }

  .place-card { background: #111; border: 1px solid #222; border-radius: 10px; padding: 16px; margin-bottom: 12px; }
  .place-name { font-size: 16px; font-weight: 600; color: #fff; }
  .place-type { font-size: 12px; color: #888; margin-left: 8px; }
  .place-parent { font-size: 12px; color: #666; }
  .place-detail { font-size: 13px; color: #aaa; margin-top: 6px; line-height: 1.5; }
  .place-detail strong { color: #ccc; }
  .evidence { display: flex; gap: 6px; margin-top: 8px; }
  .ev { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
  .ev.on { background: #1a2e1a; color: #4cd964; }
  .ev.off { background: #1a1a1a; color: #555; }

  .note-item { padding: 8px 0; border-bottom: 1px solid #222; font-size: 13px; color: #aaa; }
  .note-item:last-child { border-bottom: none; }
  .note-type { color: #fe2c55; font-weight: 600; text-transform: uppercase; font-size: 11px; margin-right: 6px; }
  .review-item { padding: 8px 0; border-bottom: 1px solid #222; font-size: 13px; }
  .review-item:last-child { border-bottom: none; }
  .review-issue { color: #f5a623; font-weight: 600; }
  .review-reason { color: #888; }

  .summary-text { color: #bbb; font-size: 14px; line-height: 1.6; }
  .map-query { font-size: 12px; color: #666; font-family: monospace; margin-top: 4px; }

  /* Raw data sections */
  .raw-data-toggle { cursor: pointer; color: #fe2c55; font-size: 13px; font-weight: 600; margin-top: 8px; display: inline-block; }
  .raw-data-toggle:hover { text-decoration: underline; }
  .raw-data-content { background: #111; border: 1px solid #222; border-radius: 8px; padding: 14px; margin-top: 8px; font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace; font-size: 12px; line-height: 1.7; color: #aaa; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto; }
  .raw-data-empty { color: #555; font-style: italic; }
</style>
</head>
<body>
<div class="container">
  <h1>🗺️ TikTok Travel Saver</h1>
  <p class="subtitle">Paste a TikTok URL to extract places and travel info</p>

  <div class="input-row">
    <input type="text" id="urlInput" placeholder="https://www.tiktok.com/@user/video/123..." />
    <button id="goBtn" onclick="startPipeline()">Extract Places</button>
  </div>

  <div class="progress-container" id="progressContainer">
    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
    <div class="step-label" id="stepLabel">Starting...</div>
  </div>

  <div class="log-box" id="logBox"></div>

  <div class="results" id="results"></div>
</div>

<script>
const STEP_NAMES = {
  1: "Fetching caption",
  2: "Downloading video",
  3: "Transcribing audio",
  4: "Extracting video frames",
  5: "Reading on-screen text (Gemini Vision)",
  6: "Combining sources",
  7: "Extracting places with AI",
  8: "Done"
};

let pollTimer = null;
let lastLogCount = 0;

function startPipeline() {
  const url = document.getElementById('urlInput').value.trim();
  if (!url) return alert('Please paste a TikTok URL');

  document.getElementById('goBtn').disabled = true;
  document.getElementById('progressContainer').style.display = 'block';
  document.getElementById('logBox').style.display = 'block';
  document.getElementById('logBox').innerHTML = '';
  document.getElementById('results').style.display = 'none';
  document.getElementById('results').innerHTML = '';
  lastLogCount = 0;

  fetch('/start', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({url}) });
  pollTimer = setInterval(pollStatus, 800);
}

function pollStatus() {
  fetch('/status').then(r => r.json()).then(data => {
    // Progress bar
    const pct = Math.round((data.current_step / data.total_steps) * 100);
    document.getElementById('progressFill').style.width = pct + '%';
    const stepName = STEP_NAMES[data.current_step] || '';
    document.getElementById('stepLabel').textContent = `Step ${data.current_step}/${data.total_steps}: ${stepName}`;

    // Logs
    const logBox = document.getElementById('logBox');
    for (let i = lastLogCount; i < data.logs.length; i++) {
      const line = document.createElement('div');
      line.className = 'log-line';
      const msg = data.logs[i];
      if (msg.startsWith('⚠️') || msg.startsWith('⚠')) line.className += ' warn';
      else if (msg.startsWith('❌')) line.className += ' error';
      else if (msg === 'Done!') line.className += ' done';
      else if (msg.match(/^(Fetching|Downloading|Transcribing|Extracting|Reading|Combining|Sending)/)) line.className += ' step';
      line.textContent = msg;
      logBox.appendChild(line);
    }
    lastLogCount = data.logs.length;
    logBox.scrollTop = logBox.scrollHeight;

    // Done
    if (!data.running) {
      clearInterval(pollTimer);
      document.getElementById('goBtn').disabled = false;
      if (data.result) renderResults(data.result, data.transcript, data.screen_text);
      if (data.error) {
        document.getElementById('stepLabel').textContent = 'Pipeline failed — see logs above';
      }
    }
  });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function renderResults(r, transcript, screenText) {
  const el = document.getElementById('results');
  el.style.display = 'block';
  let html = '';

  // Video summary
  const s = r.video_summary || {};
  html += `<div class="card">
    <h2>${s.main_topic || 'Video Summary'}</h2>
    <p class="summary-text">${s.summary || ''}</p>
    <div class="meta-row" style="margin-top:10px">
      <span class="tag">${s.destination_city || '?'}, ${s.destination_country || '?'}</span>
      <span class="tag ${s.usefulness_for_itinerary}">${s.usefulness_for_itinerary || '?'} usefulness</span>
      ${(s.overall_vibe || []).map(v => `<span class="tag vibe">${v}</span>`).join('')}
    </div>
  </div>`;

  // Raw data: Transcript + Screen Text
  html += `<div class="card">
    <h2>🔍 Raw Extracted Data</h2>
    <h3>Audio Transcript</h3>
    ${transcript ? `<div class="raw-data-content">${escapeHtml(transcript)}</div>` : '<div class="raw-data-empty">No spoken transcript detected (music-only video)</div>'}
    <h3 style="margin-top:16px">On-Screen Text (Gemini Vision)</h3>
    ${screenText ? `<div class="raw-data-content">${escapeHtml(screenText)}</div>` : '<div class="raw-data-empty">No on-screen text detected</div>'}
  </div>`;

  // Places
  const places = r.places || [];
  html += `<div class="card"><h2>📍 Places (${places.length})</h2>`;
  for (const p of places) {
    const parentTxt = p.parent_place ? `<span class="place-parent">inside ${p.parent_place}</span>` : '';
    const confClass = p.confidence || 'medium';
    html += `<div class="place-card">
      <div>
        <span class="place-name">${p.name}</span>
        <span class="place-type">${p.place_type || ''}</span>
        ${parentTxt}
        <span class="tag ${confClass}" style="margin-left:8px;font-size:11px">${p.confidence}</span>
      </div>`;

    if (p.creator_notes && p.creator_notes.length) {
      html += `<div class="place-detail">${p.creator_notes.map(n => `• ${n}`).join('<br>')}</div>`;
    }
    if (p.mentioned_foods_or_items && p.mentioned_foods_or_items.length) {
      html += `<div class="place-detail"><strong>Food/items:</strong> ${p.mentioned_foods_or_items.join(', ')}</div>`;
    }
    if (p.warnings_or_requirements && p.warnings_or_requirements.length) {
      html += `<div class="place-detail" style="color:#f5a623"><strong>⚠️</strong> ${p.warnings_or_requirements.join('; ')}</div>`;
    }
    if (p.best_for && p.best_for.length) {
      html += `<div class="meta-row" style="margin-top:8px">${p.best_for.map(b => `<span class="tag">${b}</span>`).join('')}</div>`;
    }

    const se = p.source_evidence || {};
    html += `<div class="evidence">
      <span class="ev ${se.caption ? 'on' : 'off'}">caption</span>
      <span class="ev ${se.transcript ? 'on' : 'off'}">transcript</span>
      <span class="ev ${se.ocr ? 'on' : 'off'}">ocr</span>
    </div>`;
    html += `<div class="map-query">🔍 ${p.map_search_query || ''}</div>`;
    html += `</div>`;
  }
  html += `</div>`;

  // Non-place notes
  const notes = r.non_place_notes || [];
  if (notes.length) {
    html += `<div class="card"><h2>📝 Notes (${notes.length})</h2>`;
    for (const n of notes) {
      const related = n.related_place ? ` → <em>${n.related_place}</em>` : '';
      html += `<div class="note-item"><span class="note-type">${n.type || '?'}</span>${n.text || ''}${related}</div>`;
    }
    html += `</div>`;
  }

  // Needs review
  const reviews = r.needs_user_review || [];
  if (reviews.length) {
    html += `<div class="card"><h2>⚠️ Needs Review (${reviews.length})</h2>`;
    for (const rv of reviews) {
      html += `<div class="review-item"><span class="review-issue">${rv.issue || '?'}</span><br><span class="review-reason">${rv.reason || ''}</span></div>`;
    }
    html += `</div>`;
  }

  el.innerHTML = html;
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

def safe_json_for_html(data):
    """Encode data as JSON safe to embed inside an HTML <script> tag.

    Escapes the few sequences a browser parser would otherwise treat as
    closing the script element or starting an HTML comment.
    """
    return (
        json.dumps(data)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def find_tiktok_by_id(tiktok_id):
    for t in FAKE_DATA.get("tiktoks", []):
        if t.get("id") == tiktok_id:
            return t
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logging

    def _send_html(self, body):
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_404(self, message="Not found"):
        encoded = message.encode("utf-8")
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            # Home page — list of city cards.
            body = (
                HTML_HOME
                .replace("{{BASE_CSS}}", BASE_CSS)
                .replace("{{DATA_JSON}}", safe_json_for_html(FAKE_DATA))
            )
            self._send_html(body)

        elif path.startswith("/country/"):
            # Country page — list of city cards filtered to this country.
            country_name = unquote(path[len("/country/"):])
            if not country_name:
                self._send_404("Country name missing")
                return
            body = (
                HTML_COUNTRY
                .replace("{{BASE_CSS}}", BASE_CSS)
                .replace("{{COUNTRY_NAME_JSON}}", safe_json_for_html(country_name))
                .replace("{{COUNTRY_NAME}}", html_lib.escape(country_name))
                .replace("{{DATA_JSON}}", safe_json_for_html(FAKE_DATA))
            )
            self._send_html(body)

        elif path.startswith("/city/"):
            # City page — list of TikTok cards filtered to this city.
            city_name = unquote(path[len("/city/"):])
            if not city_name:
                self._send_404("City name missing")
                return
            # Look up country from the first matching TikTok so we can build the
            # back link to its country page. Falls back to home if no match.
            country_name = next(
                (t["country"] for t in FAKE_DATA.get("tiktoks", []) if t.get("city") == city_name),
                None,
            )
            if country_name:
                back_href = "/country/" + quote(country_name, safe="")
                back_label = country_name
            else:
                back_href = "/"
                back_label = "Home"
            body = (
                HTML_CITY
                .replace("{{BASE_CSS}}", BASE_CSS)
                .replace("{{BACK_HREF}}", html_lib.escape(back_href, quote=True))
                .replace("{{BACK_LABEL}}", html_lib.escape(back_label))
                .replace("{{CITY_NAME_JSON}}", safe_json_for_html(city_name))
                .replace("{{CITY_NAME}}", html_lib.escape(city_name))
                .replace("{{DATA_JSON}}", safe_json_for_html(FAKE_DATA))
            )
            self._send_html(body)

        elif path.startswith("/tiktok/"):
            # Detail page — full extracted info for one TikTok.
            tiktok_id = unquote(path[len("/tiktok/"):])
            tiktok = find_tiktok_by_id(tiktok_id)
            if not tiktok:
                self._send_404(f"TikTok '{tiktok_id}' not found")
                return
            back_href = "/city/" + quote(tiktok["city"], safe="")
            body = (
                HTML_DETAIL
                .replace("{{BASE_CSS}}", BASE_CSS)
                .replace("{{BACK_HREF}}", html_lib.escape(back_href, quote=True))
                .replace("{{CITY_NAME}}", html_lib.escape(tiktok["city"]))
                .replace("{{DATA_JSON}}", safe_json_for_html(tiktok))
            )
            self._send_html(body)

        elif path == "/add":
            # Existing single-page pipeline experience, unchanged.
            self._send_html(HTML_PAGE)

        elif path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(pipeline_state, default=str).encode())

        else:
            self._send_404()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/start":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            url = body.get("url", "")

            if not pipeline_state["running"]:
                t = threading.Thread(target=run_pipeline, args=(url,), daemon=True)
                t.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404)
            self.end_headers()


def main():
    port = 5050
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"🗺️  TikTok Travel Saver — Web Viewer")
    print(f"   Open http://localhost:{port} in your browser")
    print(f"   Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        cleanup_temp_files()


if __name__ == "__main__":
    main()
