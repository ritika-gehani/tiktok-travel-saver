# TikTok Travel Saver

Extract travel destinations and place recommendations from TikTok videos and photo carousels. Paste a link, get structured place data.

**Supports:** TikTok videos, photo carousels, and short links (`tiktok.com/t/...`)

---

## What It Does

1. You paste a TikTok URL
2. The app downloads the content (video or carousel images)
3. AI reads on-screen text, listens to spoken audio, and reads the caption
4. AI extracts every place mentioned — restaurants, landmarks, neighborhoods, etc.
5. You get structured JSON with names, addresses, types, and confidence scores

---

## Quick Start

### 1. Install dependencies

```bash
# Command-line tools
brew install yt-dlp

# Python packages
pip3 install yt-dlp opencv-python google-genai assemblyai playwright python-dotenv

# Playwright browser (needed for photo carousels)
playwright install chromium
```

### 2. Set up API keys

Create a `.env` file in the project folder:

```bash
GOOGLE_API_KEY=your_google_gemini_api_key
ASSEMBLYAI_API_KEY=your_assemblyai_api_key
```

- **Google Gemini API key** — get one at [ai.google.dev](https://ai.google.dev/) (free tier available)
- **AssemblyAI API key** — get one at [assemblyai.com](https://www.assemblyai.com/) (free tier available, only needed for videos)

### 3. Run it

**Option A: Command line**
```bash
python3 process_tiktok.py "https://www.tiktok.com/@user/video/1234567890"
```

**Option B: Web UI**
```bash
python3 web_viewer.py
# Open http://localhost:5050 in your browser
```

Paste any TikTok link — full URL, short link, video, or photo carousel. The app figures out the rest.

---

## Example Output

Running on a Kyoto photo spot carousel:

```
Places found: 6
  1. Kifune Shrine [shrine] — high confidence
  2. Kibuneguchi Station [transit] — high confidence
  3. Kurama Temple East Gate [landmark] — high confidence
  4. Shogaku-ji Temple [shrine] — high confidence
  5. Gion Minamigawa [neighborhood] — high confidence
  6. Monju [neighborhood] — high confidence

Needs review: 4
  (addresses where the creator didn't write a place name)
```

Full output is saved to `final-extraction.json`. See [TECHNICAL.md](TECHNICAL.md) for a complete breakdown of every field in the output.

---

## Supported URL Formats

| Format | Example | Works? |
|--------|---------|--------|
| Full video URL | `tiktok.com/@user/video/123` | Yes |
| Full carousel URL | `tiktok.com/@user/photo/123` | Yes |
| Short link | `tiktok.com/t/ZP8gcrqJT/` | Yes (auto-resolves) |
| With tracking params | `...?_r=1&_t=ZP-95sQtDfwkEZ` | Yes (ignored) |

---

## Project Structure

```
tiktok-travel-saver/
├── process_tiktok.py          # CLI pipeline (run from terminal)
├── web_viewer.py              # Web UI pipeline (run in browser)
├── prompt-extract-places.txt  # AI prompt for place extraction
├── final-extraction.json      # Output from last run
├── .env                       # API keys (not committed)
├── .gitignore
├── README.md                  # This file
└── TECHNICAL.md               # Detailed technical documentation
```

---

## Technical Documentation

For a deep dive into how everything works — the pipeline architecture, scraping approach, output schema, and more — see **[TECHNICAL.md](TECHNICAL.md)**.
