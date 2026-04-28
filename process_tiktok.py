#!/usr/bin/env python3
"""
TikTok Travel Saver — Full Processing Pipeline

Usage:
    python3 process_tiktok.py "https://www.tiktok.com/@user/video/123456"

Runs the complete pipeline:
    1. Fetch caption via oEmbed
    2. Download video + audio via yt-dlp
    3. Transcribe audio via AssemblyAI
    4. Extract frames & run OCR
    5. Clean OCR via Gemini
    6. Combine all 3 sources
    7. Extract structured places via Gemini
    8. Save to final-extraction.json & clean up temp files
"""

import os
import sys
import json
import re
import time
import subprocess
import urllib.request

import base64
import cv2
from google import genai
from google.genai import types
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(PROJECT_DIR, "prompt-extract-places.txt")
OUTPUT_FILE = os.path.join(PROJECT_DIR, "final-extraction.json")

# Temp files (deleted at the end)
TEMP_VIDEO = os.path.join(PROJECT_DIR, "temp-video.mp4")
TEMP_AUDIO = os.path.join(PROJECT_DIR, "temp-audio.mp3")


def gemini_call(client, prompt, max_retries=3):
    """Call Gemini with automatic retry on transient network errors."""
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text
        except Exception as e:
            if attempt < max_retries:
                print(f"  ⚠️  Gemini call failed (attempt {attempt}/{max_retries}): {e}")
                print(f"  Retrying in 5 seconds...")
                time.sleep(5)
            else:
                raise


def load_env():
    """Load API keys from .env file into environment variables."""
    env_path = os.path.join(PROJECT_DIR, ".env")
    if not os.path.exists(env_path):
        print("ERROR: .env file not found. Create one with your API keys.")
        sys.exit(1)
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()


def cleanup_temp_files():
    """Remove temporary video and audio files."""
    for filepath in [TEMP_VIDEO, TEMP_AUDIO]:
        if os.path.exists(filepath):
            os.remove(filepath)


# ---------------------------------------------------------------------------
# Step 1: Fetch caption via oEmbed
# ---------------------------------------------------------------------------

def fetch_caption(tiktok_url):
    """Fetch video caption and metadata from TikTok oEmbed API."""
    print("\n[Step 1/8] Fetching caption from TikTok...")
    oembed_url = f"https://www.tiktok.com/oembed?url={tiktok_url}"
    try:
        with urllib.request.urlopen(oembed_url) as response:
            data = json.loads(response.read())
    except Exception as e:
        print(f"  ERROR: Failed to fetch caption: {e}")
        sys.exit(1)

    caption = data.get("title", "")
    author = data.get("author_name", "")
    print(f"  Caption: {caption[:80]}{'...' if len(caption) > 80 else ''}")
    print(f"  Author: {author}")
    return caption, author


# ---------------------------------------------------------------------------
# Step 2: Download video + audio via yt-dlp
# ---------------------------------------------------------------------------

def download_video(tiktok_url):
    """Download TikTok video and extract audio using yt-dlp."""
    print("\n[Step 2/8] Downloading TikTok video...")

    # Download video
    try:
        result = subprocess.run(
            ["yt-dlp", "-o", TEMP_VIDEO, "--force-overwrites", tiktok_url],
            capture_output=True, text=True, cwd=PROJECT_DIR
        )
        if result.returncode != 0:
            print(f"  ERROR: Video download failed: {result.stderr[:200]}")
            sys.exit(1)
    except FileNotFoundError:
        print("  ERROR: yt-dlp not found. Install it with: brew install yt-dlp")
        sys.exit(1)

    if not os.path.exists(TEMP_VIDEO):
        print("  ERROR: Video file was not created.")
        sys.exit(1)

    video_size = os.path.getsize(TEMP_VIDEO) / (1024 * 1024)
    print(f"  Video downloaded ({video_size:.1f} MB)")

    # Extract audio
    print("  Extracting audio...")
    result = subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "mp3",
         "-o", TEMP_AUDIO, "--force-overwrites", tiktok_url],
        capture_output=True, text=True, cwd=PROJECT_DIR
    )
    if result.returncode != 0:
        print(f"  ERROR: Audio extraction failed: {result.stderr[:200]}")
        sys.exit(1)

    if not os.path.exists(TEMP_AUDIO):
        print("  ERROR: Audio file was not created.")
        sys.exit(1)

    audio_size = os.path.getsize(TEMP_AUDIO) / (1024 * 1024)
    print(f"  Audio extracted ({audio_size:.1f} MB)")


# ---------------------------------------------------------------------------
# Step 3: Transcribe audio via AssemblyAI
# ---------------------------------------------------------------------------

def transcribe_audio():
    """Upload audio to AssemblyAI and get transcript."""
    print("\n[Step 3/8] Transcribing audio with AssemblyAI...")

    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        print("  ERROR: ASSEMBLYAI_API_KEY not found in .env file.")
        sys.exit(1)

    base_url = "https://api.assemblyai.com"

    def api_request(method, path, data=None, binary=None):
        headers = {"Authorization": api_key}
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

    # Upload audio
    print("  Uploading audio...")
    with open(TEMP_AUDIO, "rb") as f:
        audio_data = f.read()
    upload_result = api_request("POST", "/v2/upload", binary=audio_data)
    upload_url = upload_result["upload_url"]
    print("  Uploaded successfully.")

    # Request transcription
    print("  Requesting transcription...")
    transcript_result = api_request("POST", "/v2/transcript", data={
        "audio_url": upload_url,
        "speech_models": ["universal-2"]
    })
    transcript_id = transcript_result["id"]

    # Poll until done
    print("  Waiting for transcription (usually 15-30 seconds)...")
    while True:
        poll = api_request("GET", f"/v2/transcript/{transcript_id}")
        status = poll["status"]
        if status == "completed":
            break
        elif status == "error":
            print(f"  ERROR: Transcription failed: {poll.get('error')}")
            sys.exit(1)
        time.sleep(3)

    transcript_text = poll.get("text") or ""
    if not transcript_text.strip():
        print("  ⚠️  No spoken transcript detected. Continuing with caption + OCR only.")
        return ""
    word_count = len(transcript_text.split())
    print(f"  Transcription complete ({word_count} words)")
    return transcript_text


# ---------------------------------------------------------------------------
# Steps 4-5: Extract frames & read on-screen text with Gemini Vision
# ---------------------------------------------------------------------------

def extract_frames(sample_interval=3):
    """Extract sampled frames from video as JPEG bytes."""
    video = cv2.VideoCapture(TEMP_VIDEO)
    fps = video.get(cv2.CAP_PROP_FPS)
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    print(f"  Video: {duration:.1f}s, {fps:.0f} fps")
    print(f"  Sampling 1 frame every {sample_interval}s (~{int(duration / sample_interval)} frames)...")

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
    print(f"  Extracted {len(frames)} frames")
    return frames


def read_screen_text(gemini_client, frames):
    """Send sampled frames to Gemini Vision to read all on-screen text."""
    print("\n[Step 5/8] Reading on-screen text with Gemini Vision...")

    if not frames:
        print("  No frames to analyze.")
        return ""

    # Build multimodal content: images + prompt
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

    print(f"  Sending {len(frames)} frames to Gemini Vision...")
    response = gemini_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents
    )
    ocr_text = response.text
    print(f"  Extracted {len(ocr_text)} chars of on-screen text")
    return ocr_text


# ---------------------------------------------------------------------------
# Photo Carousel Support
# ---------------------------------------------------------------------------

def is_photo_carousel(url):
    """Check if the URL is a TikTok photo carousel (not a video)."""
    return "/photo/" in url


def fetch_carousel_data(tiktok_url):
    """Use a headless Chromium browser (Playwright) to load the TikTok carousel page
    and extract caption, author, and image URLs from the fully-rendered JSON blob.

    Returns (caption, author, image_urls).
    Returns (None, None, []) if scraping fails so the caller can fall back.
    """
    print("\n[Step 1/8] Fetching carousel data with headless browser (Playwright)...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            print("  Loading TikTok page (this takes ~10 seconds)...")
            page.goto(tiktok_url, wait_until="networkidle", timeout=30000)
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"  WARNING: Playwright failed to load page: {e}")
        return None, None, []

    # Extract __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON blob
    match = re.search(
        r'<script\s+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not match:
        print("  WARNING: Could not find __UNIVERSAL_DATA_FOR_REHYDRATION__ in rendered page.")
        return None, None, []

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"  WARNING: Failed to parse JSON blob: {e}")
        return None, None, []

    # Navigate to itemStruct
    try:
        item = data["__DEFAULT_SCOPE__"]["webapp.video-detail"]["itemInfo"]["itemStruct"]
    except (KeyError, TypeError):
        # Dump available keys to help diagnose future structure changes
        ds_keys = list(data.get("__DEFAULT_SCOPE__", {}).keys())
        print(f"  WARNING: Could not find itemStruct. DEFAULT_SCOPE keys: {ds_keys}")
        return None, None, []

    caption = item.get("desc", "")
    author = item.get("author", {}).get("uniqueId", "")

    # Extract image URLs from imagePost
    image_urls = []
    image_post = item.get("imagePost", {})
    if image_post:
        images = image_post.get("images", [])
        for img in images:
            url_list = img.get("imageURL", {}).get("urlList", [])
            if url_list:
                image_urls.append(url_list[0])

    print(f"  Caption: {caption[:80]}{'...' if len(caption) > 80 else ''}")
    print(f"  Author: {author}")
    print(f"  Images found: {len(image_urls)}")

    return caption, author, image_urls


def download_carousel_images(image_urls):
    """Download carousel images into memory. Returns list of dicts with jpeg_bytes."""
    print(f"\n[Step 2/8] Downloading {len(image_urls)} carousel images...")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    images = []
    for i, url in enumerate(image_urls):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response:
                img_bytes = response.read()
            images.append({"index": i + 1, "jpeg_bytes": img_bytes})
            size_kb = len(img_bytes) / 1024
            print(f"  Image {i + 1}/{len(image_urls)}: {size_kb:.0f} KB")
        except Exception as e:
            print(f"  WARNING: Failed to download image {i + 1}: {e}")

    print(f"  Downloaded {len(images)}/{len(image_urls)} images")
    return images


def read_carousel_images(gemini_client, images):
    """Send carousel images to Gemini Vision to read all on-screen text."""
    print("\n[Step 4/8] Reading on-screen text from carousel images with Gemini Vision...")

    if not images:
        print("  No images to analyze.")
        return ""

    # Build multimodal content: images + prompt
    contents = []
    for img in images:
        raw = img["jpeg_bytes"]
        # Auto-detect image format
        if raw[:4] == b'RIFF':
            mime = "image/webp"
        elif raw[:8] == b'\x89PNG\r\n\x1a\n':
            mime = "image/png"
        else:
            mime = "image/jpeg"
        contents.append(types.Part.from_bytes(data=raw, mime_type=mime))

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

    print(f"  Sending {len(images)} images to Gemini Vision...")
    response = gemini_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents
    )
    screen_text = response.text
    print(f"  Extracted {len(screen_text)} chars of on-screen text")
    return screen_text


# ---------------------------------------------------------------------------
# Steps 6-7: Combine sources & extract places with Gemini
# ---------------------------------------------------------------------------

def extract_places(gemini_client, caption, transcript, cleaned_ocr):
    """Combine all 3 sources and extract structured places via Gemini."""
    print("\n[Step 6/8] Combining all sources...")
    print(f"  Caption: {len(caption)} chars")
    print(f"  Transcript: {len(transcript)} chars")
    print(f"  Cleaned OCR: {len(cleaned_ocr)} chars")

    # Load prompt template
    if not os.path.exists(PROMPT_FILE):
        print(f"  ERROR: {PROMPT_FILE} not found.")
        sys.exit(1)

    with open(PROMPT_FILE, "r") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace("{CAPTION}", caption if caption else "(No caption available)")
    prompt = prompt.replace("{TRANSCRIPT}", transcript if transcript else "(No spoken transcript available)")
    prompt = prompt.replace("{OCR_TEXT}", cleaned_ocr if cleaned_ocr else "(No on-screen text detected)")

    print(f"\n[Step 7/8] Extracting places with Gemini (15-30 seconds)...")

    raw = gemini_call(gemini_client, prompt).strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*\n?', '', raw)
        raw = re.sub(r'\n?```\s*$', '', raw)

    try:
        result = json.loads(raw)
        print("  JSON parsed successfully!")
    except json.JSONDecodeError as e:
        print(f"  ERROR: Failed to parse Gemini response as JSON: {e}")
        debug_file = os.path.join(PROJECT_DIR, "debug-raw-response.txt")
        with open(debug_file, "w") as f:
            f.write(raw)
        print(f"  Raw response saved to {debug_file} for debugging.")
        sys.exit(1)

    return result


# ---------------------------------------------------------------------------
# Step 8: Save & summarize
# ---------------------------------------------------------------------------

def save_and_summarize(result):
    """Save final JSON and print a human-readable summary."""
    print(f"\n[Step 8/8] Saving results to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2)
    print("  Saved!")

    # Clean up temp files
    print("\n  Cleaning up temporary files...")
    cleanup_temp_files()
    print("  Temp files removed.")

    # Summary
    print("\n" + "=" * 60)
    print("DONE — EXTRACTION SUMMARY")
    print("=" * 60)

    summary = result.get("video_summary", {})
    print(f"\n  Topic: {summary.get('main_topic', 'N/A')}")
    print(f"  Destination: {summary.get('destination_city', '?')}, {summary.get('destination_country', '?')}")
    print(f"  Vibe: {', '.join(summary.get('overall_vibe', []))}")
    print(f"  Usefulness: {summary.get('usefulness_for_itinerary', 'N/A')}")
    print(f"  Summary: {summary.get('summary', 'N/A')}")

    places = result.get("places", [])
    print(f"\n  Places found: {len(places)}")
    for i, place in enumerate(places, 1):
        pin = "📍" if place.get("should_create_map_pin") else "📝"
        confidence = place.get("confidence", "?")
        parent = f" (inside {place['parent_place']})" if place.get("parent_place") else ""
        print(f"    {pin} {i}. {place['name']} [{place.get('place_type', '?')}] — {confidence}{parent}")

    notes = result.get("non_place_notes", [])
    print(f"\n  Non-place notes: {len(notes)}")
    for note in notes:
        related = f" → {note['related_place']}" if note.get("related_place") else ""
        text = note.get("text", "")
        print(f"    - [{note.get('type', '?')}] {text[:60]}{'...' if len(text) > 60 else ''}{related}")

    reviews = result.get("needs_user_review", [])
    print(f"\n  Needs review: {len(reviews)}")
    for review in reviews:
        print(f"    ⚠️  {review.get('issue', '?')}: {review.get('reason', '?')}")

    print(f"\n  Output: {OUTPUT_FILE}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process_tiktok.py \"TIKTOK_URL\"")
        print("Example: python3 process_tiktok.py \"https://www.tiktok.com/@nina.pemb/video/7497965157923032342\"")
        sys.exit(1)

    tiktok_url = sys.argv[1]
    carousel = is_photo_carousel(tiktok_url)

    print("=" * 60)
    print("TikTok Travel Saver — Full Pipeline")
    print("=" * 60)
    print(f"URL: {tiktok_url}")
    if carousel:
        print("Mode: Photo Carousel (no video/audio)")

    # Load environment
    load_env()

    # Validate API keys
    if not os.environ.get("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY not found in .env file.")
        sys.exit(1)
    if not carousel and not os.environ.get("ASSEMBLYAI_API_KEY"):
        print("ERROR: ASSEMBLYAI_API_KEY not found in .env file.")
        sys.exit(1)

    # Initialize Gemini client (reused for vision + extraction)
    gemini_client = genai.Client(
        api_key=os.environ["GOOGLE_API_KEY"],
        http_options=types.HttpOptions(api_version='v1')
    )

    # Run pipeline
    try:
        if carousel:
            # --- Photo carousel pipeline ---
            caption, author, image_urls = fetch_carousel_data(tiktok_url)

            if caption is None:
                # HTML scraping failed — try oEmbed as fallback for caption
                print("\n  Falling back to oEmbed for caption...")
                try:
                    caption, author = fetch_caption(tiktok_url)
                except Exception:
                    caption, author = "", ""
                image_urls = []

            images = download_carousel_images(image_urls) if image_urls else []

            print("\n[Step 3/8] Skipping audio transcription (photo carousel has no audio)")
            transcript = ""

            screen_text = read_carousel_images(gemini_client, images)
            result = extract_places(gemini_client, caption, transcript, screen_text)
            save_and_summarize(result)
        else:
            # --- Normal video pipeline ---
            caption, author = fetch_caption(tiktok_url)
            download_video(tiktok_url)
            transcript = transcribe_audio()
            print("\n[Step 4/8] Extracting video frames...")
            frames = extract_frames(sample_interval=3)
            screen_text = read_screen_text(gemini_client, frames)
            result = extract_places(gemini_client, caption, transcript, screen_text)
            save_and_summarize(result)
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        cleanup_temp_files()
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        cleanup_temp_files()
        sys.exit(1)


if __name__ == "__main__":
    main()
