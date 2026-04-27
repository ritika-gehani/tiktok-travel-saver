import os
import json
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
OCR_FILE = os.path.join(os.path.dirname(__file__), "ocr-results.json")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "cleaned-ocr.txt")

if not API_KEY:
    print("ERROR: No Google API key found. Check your .env file.")
    exit(1)

if not os.path.exists(OCR_FILE):
    print("ERROR: ocr-results.json not found. Run test-video-ocr.py first.")
    exit(1)

print("=" * 60)
print("AI OCR Cleanup with Google Gemini")
print("=" * 60)
print(f"Input: {OCR_FILE}")
print(f"Output: {OUTPUT_FILE}\n")

# Load OCR results
with open(OCR_FILE, "r") as f:
    ocr_results = json.load(f)

print(f"Loaded {len(ocr_results)} OCR entries\n")

# Combine all OCR text into one string
all_ocr_text = "\n\n".join([
    f"[{entry['timestamp_seconds']}s] {entry['text']}"
    for entry in ocr_results
])

print(f"Total OCR text length: {len(all_ocr_text)} characters\n")

# Configure Gemini client with v1 API version
client = genai.Client(
    api_key=API_KEY,
    http_options=types.HttpOptions(api_version='v1')
)

# Create the prompt
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

print("Sending OCR text to Google Gemini for cleanup...")
print("(This may take 10-20 seconds)\n")

# Send to Gemini
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=prompt
)

# Extract the cleaned text
cleaned_text = response.text

print("=" * 60)
print("CLEANED OCR OUTPUT")
print("=" * 60)
print(cleaned_text)
print("=" * 60)

# Save to file
with open(OUTPUT_FILE, "w") as f:
    f.write(cleaned_text)

print(f"\nCleaned OCR saved to: {OUTPUT_FILE}")
print(f"Original OCR entries: {len(ocr_results)}")
print(f"Original character count: {len(all_ocr_text)}")
print(f"Cleaned character count: {len(cleaned_text)}")
print(f"Reduction: {100 * (1 - len(cleaned_text) / len(all_ocr_text)):.1f}%")
print("=" * 60)
