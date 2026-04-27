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

import cv2
import pytesseract
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(PROJECT_DIR, "prompt-extract-places.txt")
OUTPUT_FILE = os.path.join(PROJECT_DIR, "final-extraction.json")

# Temp files (deleted at the end)
TEMP_VIDEO = os.path.join(PROJECT_DIR, "temp-video.mp4")
TEMP_AUDIO = os.path.join(PROJECT_DIR, "temp-audio.mp3")


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

    transcript_text = poll["text"]
    word_count = len(transcript_text.split())
    print(f"  Transcription complete ({word_count} words)")
    return transcript_text


# ---------------------------------------------------------------------------
# Step 4: Extract frames & run OCR
# ---------------------------------------------------------------------------

def run_ocr():
    """Extract video frames and run OCR with Tesseract."""
    print("\n[Step 4/8] Running OCR on video frames...")

    video = cv2.VideoCapture(TEMP_VIDEO)
    fps = video.get(cv2.CAP_PROP_FPS)
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    sample_interval = 1  # 1 frame per second

    print(f"  Video: {duration:.1f}s, {fps:.0f} fps")
    print(f"  Sampling ~{int(duration / sample_interval)} frames...")

    results = []
    frame_count = 0
    frames_to_skip = int(fps * sample_interval)

    while True:
        success, frame = video.read()
        if not success:
            break

        if frame_count % frames_to_skip == 0:
            timestamp = frame_count / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            text = pytesseract.image_to_string(gray).strip()

            if text:
                results.append({
                    "timestamp_seconds": round(timestamp, 2),
                    "text": text
                })

        frame_count += 1

    video.release()
    print(f"  OCR complete: found text in {len(results)} frames")
    return results


# ---------------------------------------------------------------------------
# Step 5: Clean OCR with Gemini
# ---------------------------------------------------------------------------

def clean_ocr(gemini_client, ocr_results):
    """Send raw OCR text to Gemini for cleanup."""
    print("\n[Step 5/8] Cleaning OCR text with Gemini...")

    if not ocr_results:
        print("  No OCR text to clean (video may have no on-screen text)")
        return ""

    all_ocr_text = "\n\n".join([
        f"[{entry['timestamp_seconds']}s] {entry['text']}"
        for entry in ocr_results
    ])

    prompt = f"""You are cleaning up OCR (optical character recognition) output from a TikTok travel video.

The OCR text below is messy and contains:
- Typos and character errors (e.g., "restaur'ts" instead of "restaurants")
- Random symbols and noise (e.g., "@@ ###", "\\\\", "===")
- Duplicate text (the same text appears in multiple frames)
- Partial words

Your task:
1. Read through all the OCR text
2. Fix obvious OCR errors to make text readable
3. Remove random symbols and nonsense
4. Remove duplicate text (keep only unique content)
5. Organize the cleaned text as bullet points
6. Each bullet point should include the place name and any relevant details
7. Return only the cleaned, organized text

Do not add any new information. Only clean and organize what is already there.

OCR Text:
{all_ocr_text}

Return the cleaned text as bullet points."""

    response = gemini_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )

    cleaned = response.text
    print(f"  Cleaned: {len(all_ocr_text)} chars → {len(cleaned)} chars ({100 * (1 - len(cleaned) / len(all_ocr_text)):.0f}% reduction)")
    return cleaned


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

    prompt = prompt_template.replace("{CAPTION}", caption)
    prompt = prompt.replace("{TRANSCRIPT}", transcript)
    prompt = prompt.replace("{OCR_TEXT}", cleaned_ocr)

    print(f"\n[Step 7/8] Extracting places with Gemini (15-30 seconds)...")

    response = gemini_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )

    raw = response.text.strip()

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
            f.write(response.text)
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

    print("=" * 60)
    print("TikTok Travel Saver — Full Pipeline")
    print("=" * 60)
    print(f"URL: {tiktok_url}")

    # Load environment
    load_env()

    # Validate API keys
    if not os.environ.get("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY not found in .env file.")
        sys.exit(1)
    if not os.environ.get("ASSEMBLYAI_API_KEY"):
        print("ERROR: ASSEMBLYAI_API_KEY not found in .env file.")
        sys.exit(1)

    # Initialize Gemini client (reused for steps 5 and 7)
    gemini_client = genai.Client(
        api_key=os.environ["GOOGLE_API_KEY"],
        http_options=types.HttpOptions(api_version='v1')
    )

    # Run pipeline
    try:
        caption, author = fetch_caption(tiktok_url)
        download_video(tiktok_url)
        transcript = transcribe_audio()
        ocr_results = run_ocr()
        cleaned_ocr = clean_ocr(gemini_client, ocr_results)
        result = extract_places(gemini_client, caption, transcript, cleaned_ocr)
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
