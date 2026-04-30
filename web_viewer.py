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
from db import db_fetch_all, db_find_by_id, db_save_tiktok

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

# ---------------------------------------------------------------------------
# HTML / CSS templates - loaded from templates/ directory
# ---------------------------------------------------------------------------

def load_template(name: str) -> str:
    """Read a template file from the templates/ directory."""
    path = os.path.join(PROJECT_DIR, "templates", name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

BASE_CSS     = load_template("base.css")
HTML_HOME    = load_template("home.html")
HTML_COUNTRY = load_template("country.html")
HTML_CITY    = load_template("city.html")
HTML_DETAIL  = load_template("detail.html")
HTML_PAGE    = load_template("add.html")


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
    return db_find_by_id(tiktok_id)


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
            # Home page — list of country cards.
            live_data = db_fetch_all()
            body = (
                HTML_HOME
                .replace("{{BASE_CSS}}", BASE_CSS)
                .replace("{{DATA_JSON}}", safe_json_for_html(live_data))
            )
            self._send_html(body)

        elif path.startswith("/country/"):
            # Country page — list of city cards filtered to this country.
            country_name = unquote(path[len("/country/"):])
            if not country_name:
                self._send_404("Country name missing")
                return
            live_data = db_fetch_all()
            body = (
                HTML_COUNTRY
                .replace("{{BASE_CSS}}", BASE_CSS)
                .replace("{{COUNTRY_NAME_JSON}}", safe_json_for_html(country_name))
                .replace("{{COUNTRY_NAME}}", html_lib.escape(country_name))
                .replace("{{DATA_JSON}}", safe_json_for_html(live_data))
            )
            self._send_html(body)

        elif path.startswith("/city/"):
            # City page — list of TikTok cards filtered to this city.
            city_name = unquote(path[len("/city/"):])
            if not city_name:
                self._send_404("City name missing")
                return
            live_data = db_fetch_all()
            # Look up country from the first matching TikTok so we can build the
            # back link to its country page. Falls back to home if no match.
            country_name = next(
                (t["country"] for t in live_data.get("tiktoks", []) if t.get("city") == city_name),
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
                .replace("{{DATA_JSON}}", safe_json_for_html(live_data))
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

    def _send_json(self, data, status=200):
        encoded = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/start":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            url = body.get("url", "")

            if not pipeline_state["running"]:
                t = threading.Thread(target=run_pipeline, args=(url,), daemon=True)
                t.start()

            self._send_json({"ok": True})

        elif path == "/save":
            # Save the current pipeline result to Supabase.
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            tiktok_url = body.get("url", "")
            extraction = body.get("result") or pipeline_state.get("result")
            transcript = body.get("transcript") or pipeline_state.get("transcript", "")
            screen_text = body.get("screen_text") or pipeline_state.get("screen_text", "")
            if not tiktok_url or not extraction:
                self._send_json({"error": "Missing url or result"}, status=400)
                return
            try:
                saved = db_save_tiktok(tiktok_url, extraction, transcript, screen_text)
                self._send_json({"ok": True, "id": saved.get("id"), "city": saved.get("city"), "country": saved.get("country")})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)

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
