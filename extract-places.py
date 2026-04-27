import os
import json
import re
from google import genai
from google.genai import types

# Load API key from .env file
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

load_env()

# Configuration
API_KEY = os.environ.get("GOOGLE_API_KEY")
PROJECT_DIR = os.path.dirname(__file__)
CAPTION_FILE = os.path.join(PROJECT_DIR, "caption-data.json")
TRANSCRIPT_FILE = os.path.join(PROJECT_DIR, "transcript-output.txt")
OCR_FILE = os.path.join(PROJECT_DIR, "cleaned-ocr.txt")
PROMPT_FILE = os.path.join(PROJECT_DIR, "prompt-extract-places.txt")
OUTPUT_FILE = os.path.join(PROJECT_DIR, "extracted-places.json")

if not API_KEY:
    print("ERROR: No Google API key found. Check your .env file.")
    exit(1)

# Check all input files exist
for filepath, label in [
    (CAPTION_FILE, "caption-data.json"),
    (TRANSCRIPT_FILE, "transcript-output.txt"),
    (OCR_FILE, "cleaned-ocr.txt"),
    (PROMPT_FILE, "prompt-extract-places.txt"),
]:
    if not os.path.exists(filepath):
        print(f"ERROR: {label} not found. Run the previous steps first.")
        exit(1)

print("=" * 60)
print("Place Extraction with Google Gemini")
print("=" * 60)

# Step 1: Read caption data
print("\nStep 1: Reading caption data...")
with open(CAPTION_FILE, "r") as f:
    caption_data = json.load(f)
caption_text = caption_data.get("title", "")
author_name = caption_data.get("author_name", "")
print(f"  Caption: {caption_text[:80]}...")
print(f"  Author: {author_name}")

# Step 2: Read and parse transcript
print("\nStep 2: Reading transcript...")
with open(TRANSCRIPT_FILE, "r") as f:
    transcript_raw = f.read()

# Extract just the transcript text between the === markers
lines = transcript_raw.split("\n")
transcript_text = ""
in_transcript = False
for line in lines:
    if line.startswith("TRANSCRIPT"):
        in_transcript = True
        continue
    if in_transcript and line.startswith("===="):
        if transcript_text:
            break
        continue
    if in_transcript:
        transcript_text += line + " "
transcript_text = transcript_text.strip()
print(f"  Transcript: {transcript_text[:80]}...")
print(f"  Word count: {len(transcript_text.split())} words")

# Step 3: Read cleaned OCR
print("\nStep 3: Reading cleaned OCR text...")
with open(OCR_FILE, "r") as f:
    ocr_text = f.read().strip()
print(f"  OCR text: {ocr_text[:80]}...")

# Step 4: Load prompt template and fill in placeholders
print("\nStep 4: Building prompt...")
with open(PROMPT_FILE, "r") as f:
    prompt_template = f.read()

prompt = prompt_template.replace("{CAPTION}", caption_text)
prompt = prompt.replace("{TRANSCRIPT}", transcript_text)
prompt = prompt.replace("{OCR_TEXT}", ocr_text)

print(f"  Total prompt length: {len(prompt)} characters")

# Step 5: Send to Gemini
print("\nStep 5: Sending to Gemini (this may take 15-30 seconds)...")
client = genai.Client(
    api_key=API_KEY,
    http_options=types.HttpOptions(api_version='v1')
)

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=prompt
)

raw_response = response.text
print(f"  Response received ({len(raw_response)} characters)")

# Step 6: Parse JSON from response
print("\nStep 6: Parsing JSON response...")

# Strip markdown code fences if Gemini wraps the JSON in them
cleaned_response = raw_response.strip()
if cleaned_response.startswith("```"):
    cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response)
    cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)

try:
    result = json.loads(cleaned_response)
    print("  JSON parsed successfully!")
except json.JSONDecodeError as e:
    print(f"  ERROR: Failed to parse JSON: {e}")
    print(f"  Raw response saved to extracted-places-raw.txt for debugging")
    with open(os.path.join(PROJECT_DIR, "extracted-places-raw.txt"), "w") as f:
        f.write(raw_response)
    exit(1)

# Step 7: Save results
print("\nStep 7: Saving results...")
with open(OUTPUT_FILE, "w") as f:
    json.dump(result, f, indent=2)
print(f"  Saved to: {OUTPUT_FILE}")

# Step 8: Print summary
print("\n" + "=" * 60)
print("EXTRACTION SUMMARY")
print("=" * 60)

# Video summary
summary = result.get("video_summary", {})
print(f"\nVideo Topic: {summary.get('main_topic', 'N/A')}")
print(f"Destination: {summary.get('destination_city', '?')}, {summary.get('destination_country', '?')}")
print(f"Vibe: {', '.join(summary.get('overall_vibe', []))}")
print(f"Usefulness: {summary.get('usefulness_for_itinerary', 'N/A')}")
print(f"Summary: {summary.get('summary', 'N/A')}")

# Places
places = result.get("places", [])
print(f"\nPlaces found: {len(places)}")
for i, place in enumerate(places, 1):
    pin = "📍" if place.get("should_create_map_pin") else "📝"
    confidence = place.get("confidence", "?")
    parent = f" (inside {place['parent_place']})" if place.get("parent_place") else ""
    print(f"  {pin} {i}. {place['name']} [{place.get('place_type', '?')}] — confidence: {confidence}{parent}")

# Non-place notes
notes = result.get("non_place_notes", [])
print(f"\nNon-place notes: {len(notes)}")
for note in notes:
    related = f" → {note['related_place']}" if note.get("related_place") else ""
    print(f"  - [{note.get('type', '?')}] {note['text'][:60]}...{related}" if len(note.get('text', '')) > 60 else f"  - [{note.get('type', '?')}] {note.get('text', '')}{related}")

# Needs review
reviews = result.get("needs_user_review", [])
print(f"\nNeeds user review: {len(reviews)}")
for review in reviews:
    print(f"  ⚠️  {review.get('issue', '?')}: {review.get('reason', '?')}")

print("\n" + "=" * 60)
print(f"Full results: {OUTPUT_FILE}")
print("=" * 60)
