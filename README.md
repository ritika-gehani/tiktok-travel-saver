# TikTok Travel Saver

Extract travel destinations and place recommendations from TikTok videos and photo carousels. Paste a link, get structured place data — then save it into a city trip (Tokyo, Kyoto, Lisbon…) so planning a trip means one calm page, not a scroll through every saved video.

**Supports:** TikTok videos, photo carousels, and short links (`tiktok.com/t/...`)

---

## What It Does

1. You paste a TikTok URL
2. The app downloads the content (video or carousel images)
3. AI reads on-screen text, listens to spoken audio, and reads the caption
4. AI extracts every place mentioned — restaurants, landmarks, neighborhoods, etc.
5. You get structured JSON with names, addresses, types, and confidence scores
6. **Save it into a trip** (web UI) — one trip per city; each trip page lists its TikToks and the places they surfaced

Trips are created country-first: type a country, then a city inside it (both
filter as you type, from a bundled offline list — unknown names show "no match"
rather than being accepted). Another city means another trip, even in the same
country.

---

## Quick Start

### 0. Just want to browse the app? (no keys needed)

```bash
python3 -m venv .venv && source .venv/bin/activate
make install      # python-dotenv, supabase, pytest
make test         # runs the HTTP tests against the local store
make run          # open http://localhost:5050
```

Without Supabase credentials the library is stored in a local JSON file
(`data/library.json`, ignored by git), seeded from `data/seed-library.json`
with five sample city trips so every page has content. Set `LIBRARY_FILE` to use a
different path. The file has the shape `{"trips": [...], "tiktoks": [...]}`; an
older list-only `library.json` is migrated in place on first load, grouping each
TikTok into a trip for its city. The paste-a-TikTok extraction flow needs the
extra setup below.

### 1. Install extraction dependencies

```bash
# Command-line tools
brew install yt-dlp

# Python packages + Playwright browser (needed for photo carousels)
make install-extraction
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

### 3. Create the Supabase tables (optional — skip to keep the local JSON store)

In your Supabase dashboard, open the SQL Editor and run:

```sql
CREATE TABLE IF NOT EXISTS trips (
  id            text PRIMARY KEY,
  country       text NOT NULL,
  city          text NOT NULL,
  start_date    date,
  end_date      date,
  planning_mode text NOT NULL DEFAULT 'collect',
  created_at    timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE trips DISABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS tiktoks (
  id           text PRIMARY KEY,
  url          text NOT NULL UNIQUE,
  author       text,
  trip_id      text REFERENCES trips (id),
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
CREATE INDEX IF NOT EXISTS idx_tiktoks_trip_id    ON tiktoks (trip_id);
CREATE INDEX IF NOT EXISTS idx_tiktoks_created_at ON tiktoks (created_at DESC);
ALTER TABLE tiktoks DISABLE ROW LEVEL SECURITY;
```

Already have a `tiktoks` table from an earlier version? Add the column and the
app will file existing rows into city trips on first load:

```sql
ALTER TABLE tiktoks ADD COLUMN IF NOT EXISTS trip_id text REFERENCES trips (id);
CREATE INDEX IF NOT EXISTS idx_tiktoks_trip_id ON tiktoks (trip_id);
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

The web UI:

| Route | What it is |
|-------|------------|
| `/` | Your city trips, one card each, plus **New trip** (country → city typeahead) |
| `/trip/<id>` | One city trip: paste box, saved TikToks, extracted places |
| `/tiktok/<id>` | Everything extracted from one TikTok |
| `/add?trip=<id>` | Extraction flow; saves into that trip |
| `GET /api/destinations?q=` / `?country=&q=` | Country / city typeahead |
| `POST /trips` | Create a trip — `{country, city, start_date?, end_date?, planning_mode?}`; unknown names are rejected |
| `POST /save` | Save an extraction — `{url, result, trip_id}` |

Paste any TikTok link — full URL, short link, video, or photo carousel. The app figures out the rest.

The country/city list lives in `data/destinations.json` (GeoNames cities with
population ≥ 15k, plus close-spelling aliases so "Seville" finds Sevilla). To
refresh it: `pip install geonamescache && python3 scripts/build_destinations.py`.

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
├── db.py                      # Trips + TikToks storage: Supabase, or local JSON when no keys are set
├── destinations.py            # Offline country → city typeahead and validation
├── scripts/build_destinations.py  # Regenerates data/destinations.json from GeoNames
├── data/destinations.json     # Bundled countries + cities (+ spelling aliases)
├── data/seed-library.json     # Sample trips and TikToks used to seed the local store
├── tests/                     # pytest HTTP tests for the web UI (make test)
├── templates/                 # HTML/CSS/JS templates for the web UI
│   ├── base.css               # Shared light design system
│   ├── results.js             # Shared extraction-result renderer (add + detail)
│   ├── home.html              # City trip cards + Create trip sheet
│   ├── trip.html              # One city trip: paste box, TikToks, places
│   ├── detail.html            # Single TikTok detail view
│   └── add.html               # Extraction flow, scoped to a trip
├── prompt-extract-places.txt  # AI prompt for place extraction
├── final-extraction.json      # Output from last CLI run
├── PRD.md                     # Product vision, audience and roadmap
├── V1_PRODUCT_SPEC.md         # Engineer-facing V1 requirements and acceptance criteria
├── PRODUCT_PLAN.md            # Earlier implementation plan and roadmap
├── Makefile                   # install / install-extraction / test / run
├── requirements.txt           # Core deps; requirements-extraction.txt adds the pipeline deps
├── .env                       # API keys + Supabase creds (not committed)
├── .gitignore
├── README.md                  # This file
└── TECHNICAL.md               # Detailed technical documentation
```

---

## Technical Documentation

For a deep dive into how everything works — the pipeline architecture, scraping approach, output schema, and more — see **[TECHNICAL.md](TECHNICAL.md)**.

For the product definition and roadmap, see **[PRD.md](PRD.md)**. For the
engineer-facing Version 1 requirements, current-state gap analysis, and
acceptance criteria, see **[V1_PRODUCT_SPEC.md](V1_PRODUCT_SPEC.md)**.
