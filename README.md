# TikTok Travel Saver - Feasibility Tests

**Goal:** Build an app that saves TikTok travel/food videos as organized map-based collections.

**Current phase:** Early feasibility testing — not building the full app yet. We're testing what data we can get from TikTok before making bigger technical decisions.

---

## What we've tested so far

### Test 1 ✅: TikTok oEmbed API
**What:** Can we get metadata from a TikTok link?
**How:** `test-tiktok-oembed.html` — a webpage that calls TikTok's public oEmbed endpoint.
**Result:** Yes — we get title, author, thumbnail, embed HTML.
**Limitations:** No GPS coordinates, hashtags buried in title text, caption quality varies.

### Test 2 ✅: Download TikTok audio
**What:** Can we extract the audio from a TikTok video?
**How:** `yt-dlp` — a command-line tool to download video audio.
**Result:** Yes — we can download just the audio as MP3.
**Note:** This uses an open-source tool that's technically against TikTok's terms of service. Fine for personal testing, not for a public app.

### Test 3 ✅: Transcribe audio to text
**What:** Can we convert the spoken audio into text?
**How:** AssemblyAI's transcription API (via `test-transcribe.py`).
**Result:** Yes — we get 213 words of transcript with rich place details (e.g., "Kushikatsu restaurants", "Osaka Castle rooftop cafe").
**Cost:** Free tier with AssemblyAI.

---

## Key findings so far

| Data source | Useful for places? |
|---|---|
| TikTok caption (oEmbed) | Partial — depends on creator writing it |
| Hashtags (from caption) | Vague — usually just city names |
| Audio transcript | **Excellent** — creators say specific place names out loud |

The transcript is dramatically more useful than the caption. Creators casually say "the rooftop cafe at Osaka Castle" without typing it — that's exactly what we need.

---

## Next test (not done yet)

### Test 4: Extract places from transcript using AI
**Goal:** Give the transcript to GPT and ask it to extract a clean list of specific places/restaurants.
**Why:** The transcript is raw text. We need structured place names to eventually show on a map.

---

## Project structure

```
tiktok-travel-saver/
├── test-tiktok-oembed.html    # Webpage to test TikTok oEmbed API
├── test-transcribe.py         # Python script to transcribe audio
├── tiktok-audio.mp3           # Sample audio file (downloaded)
├── .env                       # API keys (hidden, not committed)
├── .gitignore                 # Files to exclude from git
└── README.md                  # This file
```

---

## Setup instructions

1. Install Homebrew (if not already installed)
2. Install yt-dlp: `brew install yt-dlp`
3. Install Python packages: `pip3 install assemblyai --break-system-packages`
4. Create `.env` file with your AssemblyAI API key:
   ```
   ASSEMBLYAI_API_KEY=your_key_here
   ```

---

## Usage

**Test oEmbed:**
1. Open `test-tiktok-oembed.html` in your browser
2. Paste a TikTok URL
3. Click "Fetch Data"

**Test transcription:**
1. Download TikTok audio: `yt-dlp -x --audio-format mp3 -o "tiktok-audio.%(ext)s" "TIKTOK_URL"`
2. Run: `python3 test-transcribe.py`
