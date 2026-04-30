# TikTok Travel Saver

Extract travel destinations and place recommendations from TikTok videos and photo carousels. Paste a link, get structured place data — then save it to your personal travel library, organized by country and city.

**Supports:** TikTok videos, photo carousels, and short links (`tiktok.com/t/...`)

---

## What It Does

1. You paste a TikTok URL
2. The app downloads the content (video or carousel images)
3. AI reads on-screen text, listens to spoken audio, and reads the caption
4. AI extracts every place mentioned — restaurants, landmarks, neighborhoods, etc.
5. You get structured JSON with names, addresses, types, and confidence scores
6. **Save to your library** (web UI) — stored in Supabase, browsable by Country → City → TikTok

---

## Quick Start

### 1. Install dependencies

```bash
# Command-line tools
brew install yt-dlp

# Python packages
pip3 install yt-dlp opencv-python google-genai assemblyai playwright python-dotenv supabase

# Playwright browser (needed for photo carousels)
playwright install chromium
```

### 2. Set up API keys & Supabase

Create a `.env` file in the project folder:

```bash
GOOGLE_API_KEY=your_google_gemini_api_key
ASSEMBLYAI_API_KEY=your_assemblyai_api_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

- **Google Gemini API key** — get one at [ai.google.dev](https://ai.google.dev/) (free tier available)
- **AssemblyAI API key** — get one at [assemblyai.com](https://www.assemblyai.com/) (free tier available, only needed for videos)
- **Supabase URL & service_role key** — create a free project at [supabase.com](https://supabase.com), then get them from Project Settings → API. Only needed for the web UI's library feature.

### 3. Create the Supabase table

In your Supabase dashboard, open the SQL Editor and run:

```sql
CREATE TABLE IF NOT EXISTS tiktoks (
  id           text PRIMARY KEY,
  url          text NOT NULL UNIQUE,
  author       text,
  city         text NOT NULL,
  country      text NOT NULL,
  status       text NOT NULL DEFAULT 'needs_review',
  cover_path   text,
  data         jsonb NOT NULL,
  transcript   text DEFAULT '',
  screen_text  text DEFAULT '',
  created_at   timestamptz NOT NULL DEFAULT now(),
  reviewed_at  timestamptz
);
CREATE INDEX IF NOT EXISTS idx_tiktoks_country_city ON tiktoks (country, city);
CREATE INDEX IF NOT EXISTS idx_tiktoks_created_at  ON tiktoks (created_at DESC);
ALTER TABLE tiktoks DISABLE ROW LEVEL SECURITY;
```

### 4. Run it

**Option A: Command line** (extraction only, no saving)
```bash
python3 process_tiktok.py "https://www.tiktok.com/@user/video/1234567890"
```

**Option B: Web UI** (extraction + library)
```bash
python3 web_viewer.py
# Open http://localhost:5050 in your browser
```

The web UI lets you:
- **Browse** your saved TikToks at `/` (organized by Country → City → TikTok)
- **Add new** TikToks at `/add` — paste any TikTok link, then click "Save to Library" after extraction

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
├── web_viewer.py              # Web UI: HTTP server + extraction pipeline
├── db.py                      # Supabase database operations
├── templates/                 # HTML/CSS templates for the web UI
│   ├── base.css               # Shared dark-mode styles
│   ├── home.html              # Home page (country grid)
│   ├── country.html           # Country page (city grid)
│   ├── city.html              # City page (TikTok grid)
│   ├── detail.html            # Single TikTok detail view
│   └── add.html               # New TikTok extraction form
├── prompt-extract-places.txt  # AI prompt for place extraction
├── final-extraction.json      # Output from last CLI run
├── PRODUCT_PLAN.md            # Product vision & roadmap
├── .env                       # API keys + Supabase creds (not committed)
├── .gitignore
├── README.md                  # This file
└── TECHNICAL.md               # Detailed technical documentation
```

---

## Technical Documentation

For a deep dive into how everything works — the pipeline architecture, scraping approach, output schema, and more — see **[TECHNICAL.md](TECHNICAL.md)**.
