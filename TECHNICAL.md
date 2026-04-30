# Technical Documentation

Deep dive into how TikTok Travel Saver works — the pipeline, scraping, AI extraction, and output format.

---

## Table of Contents

- [Pipeline Overview](#pipeline-overview)
- [Supported Content Types](#supported-content-types)
- [Step-by-Step Pipeline](#step-by-step-pipeline)
- [Photo Carousel Scraping](#photo-carousel-scraping)
- [Output Schema](#output-schema)
- [Output Field Reference](#output-field-reference)
- [Real Example Output](#real-example-output)
- [Web UI Architecture](#web-ui-architecture)
- [Persistence (Supabase)](#persistence-supabase)
- [Technical Stack](#technical-stack)
- [Known Limitations](#known-limitations)

---

## Pipeline Overview

```
TikTok URL
    │
    ▼
[Resolve short link if needed]
    │
    ▼
[Detect: video or carousel?]
    │
    ├──────────────────────────────────┐
    ▼                                  ▼
  VIDEO                            CAROUSEL
    │                                  │
    ├─ oEmbed API → caption            ├─ Playwright browser → load page
    ├─ yt-dlp → video + audio          ├─ DOM scraping → caption + images
    ├─ AssemblyAI → transcript         ├─ Download all images
    ├─ OpenCV → video frames           ├─ (no audio to transcribe)
    └─ Gemini Vision → OCR text        └─ Gemini Vision → OCR text
    │                                  │
    └──────────────┬───────────────────┘
                   ▼
    [Caption + Transcript + OCR Text]
                   │
                   ▼
    [Gemini 2.5 Flash: Extract Places]
                   │
                   ▼
    [Structured JSON → final-extraction.json]
```

---

## Supported Content Types

### TikTok Videos
- URL pattern: `tiktok.com/@user/video/123`
- Downloads video and audio separately
- Transcribes spoken words using AssemblyAI
- Extracts video frames every 3 seconds using OpenCV
- Reads on-screen text from frames using Gemini Vision

### TikTok Photo Carousels
- URL pattern: `tiktok.com/@user/photo/123`
- Opens page in a headless Chromium browser (Playwright)
- Extracts caption (hashtags) and image URLs from the rendered page
- Downloads all carousel images
- Reads on-screen text from images using Gemini Vision
- No audio processing (carousels are silent)

### Short Links
- URL pattern: `tiktok.com/t/ABC123/`
- Automatically follows HTTP redirects to get the full URL
- Then processes as video or carousel based on the resolved URL

---

## Step-by-Step Pipeline

### Step 1: URL Resolution
If the URL is a short link (`/t/...`), send an HTTP HEAD request and follow the redirect to get the full URL. This happens before anything else so the app knows whether it's a video or carousel.

### Step 2: Fetch Metadata & Content

**For Videos:**
1. Call TikTok's oEmbed API to get caption and author
2. Download video (MP4) and audio (MP3) using yt-dlp
3. Transcribe audio to text using AssemblyAI
4. Extract video frames every 3 seconds using OpenCV
5. Send frames to Gemini Vision to read on-screen text (OCR)

**For Carousels:**
1. Launch headless Chromium browser with anti-bot detection measures
2. Navigate to the TikTok page and wait for it to fully load (~10 seconds)
3. Extract hashtags from the page's visible text as the caption
4. Extract the author username from the page text
5. Find all `<img>` tags with `photomode-image` in the src URL (carousel slides)
6. Deduplicate image URLs (TikTok repeats them for different carousel positions)
7. Download all images immediately (URLs expire after a few hours)
8. Send all images to Gemini Vision to read on-screen text (OCR)

### Step 3: Combine Text Sources
Merge all extracted text into one blob:
- **Caption** — hashtags or full description from the creator
- **Transcript** — spoken words (videos only, empty for carousels)
- **On-screen text** — OCR from video frames or carousel images

### Step 4: AI Place Extraction
Send the combined text to Gemini 2.5 Flash with a detailed extraction prompt. The prompt asks for structured place data including names, types, addresses, confidence scores, and more.

### Step 5: Save Results
- Write structured JSON to `final-extraction.json`
- Print a summary to the terminal
- Clean up temporary files (video, audio, frames)

---

## Photo Carousel Scraping

This was the hardest technical challenge. Here's what we tried and why each approach failed:

### Approach 1: Direct HTTP Request (failed)
TikTok detects Python's `urllib` as a bot and returns a skeleton HTML page with no content.

### Approach 2: Headless Browser — Parse JSON Blob (failed)
Even with Playwright, TikTok's `__UNIVERSAL_DATA_FOR_REHYDRATION__` JSON blob no longer contains the `itemStruct` key with post data.

### Approach 3: Headless Browser — Parse Rendered DOM (works!)
The page renders correctly in Chromium with anti-detection flags. We extract data directly from the rendered HTML:

**Anti-detection measures:**
- `--disable-blink-features=AutomationControlled` — removes automation signals from the browser
- `navigator.webdriver = undefined` — hides a JavaScript property that bots have but real browsers don't

**What we extract from the DOM:**
- **Caption:** Regex for hashtags (`#word`) in the page's visible body text
- **Author:** Regex for the username pattern (`username_\n· 1-N`) in body text
- **Images:** All `<img>` tag `src` attributes containing `photomode-image` (filters out avatars, icons, etc.), deduplicated

**Trade-offs:**
- Adds ~10 seconds per carousel (browser launch + page load)
- Requires Playwright + Chromium (~150MB disk space)
- Fragile — if TikTok changes their HTML structure, this could break

---

## Output Schema

The app outputs a JSON file with this top-level structure:

```json
{
  "video_summary": { ... },
  "places": [ ... ],
  "non_place_notes": [ ... ],
  "needs_user_review": [ ... ]
}
```

Each section is explained in detail below.

---

## Output Field Reference

### `video_summary`

High-level metadata about the TikTok content.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `main_topic` | string | What the video/carousel is about | `"Favorite Photo Locations in Kyoto"` |
| `destination_city` | string | Primary city featured | `"Kyoto"` |
| `destination_country` | string | Country | `"Japan"` |
| `overall_vibe` | string[] | Tags describing the content's mood/style | `["photography", "sightseeing", "casual exploring"]` |
| `usefulness_for_itinerary` | string | How useful this is for trip planning: `"high"`, `"medium"`, or `"low"` | `"high"` |
| `summary` | string | 1-2 sentence description | `"This video showcases the creator's favorite photo locations in Kyoto, Japan."` |

**Usefulness scores explained:**
- **high** — Contains specific, actionable place recommendations you can put in an itinerary
- **medium** — Mentions places but not in a detailed or actionable way
- **low** — Mostly vibes, no specific places (e.g., generic "travel montage" videos)

---

### `places`

Array of every place mentioned in the content. Each place has:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `name` | string or null | Place name. `null` if only an address was given | `"Kifune Shrine"` |
| `place_type` | string | Category of place | `"shrine"`, `"restaurant"`, `"neighborhood"` |
| `city` | string | City where the place is located | `"Kyoto"` |
| `country` | string | Country | `"Japan"` |
| `parent_place` | string or null | If this place is inside a larger place | `"Kurama Temple"` (for "Kurama Temple, West Gate") |
| `map_search_query` | string | Ready-to-paste Google Maps search string | `"Kifune Shrine, Kyoto, Japan"` |
| `should_create_map_pin` | boolean | Whether this deserves its own pin on a map | `true` |
| `confidence` | string | How confident the AI is: `"high"`, `"medium"`, or `"low"` | `"high"` |
| `why_confidence` | string | Explanation of the confidence rating | `"Explicitly named in English and Japanese"` |
| `source_evidence` | object | Which data sources mentioned this place | `{"caption": false, "transcript": false, "ocr": true}` |
| `creator_notes` | string[] | What the creator said about this place | `["One of the creator's favorite photo locations"]` |
| `best_for` | string[] | Activity tags | `["photography", "sightseeing", "nature"]` |
| `warnings_or_requirements` | string[] | Entry fees, reservations, dress codes, etc. | `["Admission fee required"]` |
| `mentioned_foods_or_items` | string[] | Specific dishes or items mentioned | `["okonomiyaki", "yakisoba"]` |
| `raw_mentions` | string[] | Exact text found in the video/images | `["180 Kuramakibunecho, Sakyo Ward, Kyoto"]` |

**Confidence scores explained:**
- **high** — The place was explicitly named and clearly a recommendation. You can trust this.
  - Example: `"Kifune Shrine"` — named directly with a full address
- **medium** — Probably a real place, but the AI is less certain. Might be vague or inferred.
  - Example: `"Shiragiko Inari"` — named on a sign in the image, but not explicitly recommended
- **low** — Weak evidence. Might just be an address with no name, or mentioned in passing.
  - Example: `null` name with only `"95-9, Oguracho Kasugamori, Uji, Kyoto"` — just an address

**Place types:**
`restaurant`, `cafe`, `bar`, `hotel`, `shrine`, `temple`, `landmark`, `beach`, `park`, `neighborhood`, `transit`, `attraction`, `market`, `museum`, `activity`, `unknown`

**Source evidence explained:**
- `caption: true` — The place was mentioned in the TikTok caption/hashtags
- `transcript: true` — The creator said the place name out loud (videos only)
- `ocr: true` — The place name appeared as text overlay on the video/image

A place can have multiple sources set to `true` (e.g., the creator says "Osaka Castle" and it also appears as text on screen).

---

### `non_place_notes`

Useful information that isn't a specific place — vibes, activities, cultural context.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `type` | string | Category: `"vibe"`, `"activity"`, `"warning"`, `"tip"` | `"activity"` |
| `text` | string | The note content | `"Mentions 'omamori' (amulets), suggesting these are available at the shrines."` |
| `related_place` | string or null | Which place this note relates to | `null` |

**Note types:**
- **vibe** — General mood or cultural context (e.g., "The creator emphasizes this area is great for nightlife")
- **activity** — Something to do that isn't a specific place (e.g., "Try the street food stalls")
- **warning** — Something to watch out for (e.g., "Very crowded on weekends")
- **tip** — Practical advice (e.g., "Go early morning for fewer tourists")

---

### `needs_user_review`

Items the AI flagged as ambiguous — things a human should verify.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `issue` | string | What needs to be checked | `"Specific place name for address '1, Saganonomiyacho, Ukyo, Kyoto'"` |
| `reason` | string | Why the AI couldn't resolve it | `"The video provides an address but does not explicitly name the place."` |

Common reasons for review flags:
- Creator gave an address but no place name
- Place name is ambiguous (could be multiple locations)
- AI couldn't determine if something is a real place or just a description

---

## Web UI Architecture

The web UI is a single-process Python HTTP server that serves multiple roles:

### File layout

```
web_viewer.py        # HTTP server, routing, extraction pipeline (~660 lines)
db.py                # Supabase client + DB operations (~110 lines)
templates/           # HTML/CSS files loaded at server startup
  base.css           # Shared styles
  home.html          # Country grid
  country.html       # City grid (filtered to one country)
  city.html          # TikTok grid (filtered to one city)
  detail.html        # Single TikTok detail view
  add.html           # Extraction form (URL input + progress + save button)
```

### Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Home page — lists all countries with TikToks |
| GET | `/country/<name>` | All cities within a country |
| GET | `/city/<name>` | All TikToks within a city |
| GET | `/tiktok/<id>` | Full detail view for one TikTok |
| GET | `/add` | Extraction form |
| GET | `/status` | JSON snapshot of pipeline state (polled by `/add`) |
| POST | `/start` | Kick off extraction for a URL |
| POST | `/save` | Persist the latest extraction to Supabase |

### Templating

Templates use a simple `{{PLACEHOLDER}}` substitution scheme. The server reads each template file once at startup, then on each request replaces placeholders like `{{BASE_CSS}}`, `{{DATA_JSON}}`, `{{CITY_NAME}}` with their values before writing the body. There's no Jinja or Flask — just `str.replace()`.

**Why so simple?** This kept the dependency footprint small and made it easy to embed the entire UI in one Python file initially. Splitting templates into separate files (Stage 2 of refactoring) preserved this approach but gave us syntax highlighting and easier editing.

---

## Persistence (Supabase)

The web UI stores saved TikToks in a single Postgres table on Supabase.

### Schema

```sql
CREATE TABLE tiktoks (
  id           text PRIMARY KEY,             -- e.g. "osaka-7612758606290619679"
  url          text NOT NULL UNIQUE,         -- original TikTok URL
  author       text,                         -- e.g. "@traveljapan"
  city         text NOT NULL,                -- from video_summary.destination_city
  country      text NOT NULL,                -- from video_summary.destination_country
  status       text NOT NULL DEFAULT 'needs_review',
  cover_path   text,                         -- thumbnail (not yet implemented)
  data         jsonb NOT NULL,               -- full extraction blob
  transcript   text DEFAULT '',
  screen_text  text DEFAULT '',
  created_at   timestamptz NOT NULL DEFAULT now(),
  reviewed_at  timestamptz                   -- set when status moves to 'reviewed'
);
```

### ID generation

IDs are deterministic, not random. They're built from the city name and the TikTok video ID:

```python
tiktok_id = f"{slug(city)}-{video_id_from_url}"
# e.g. "osaka-7612758606290619679"
```

This makes saves **idempotent** — saving the same TikTok twice updates the existing row instead of creating a duplicate (via `upsert`).

### Why no Row Level Security (RLS)?

RLS is disabled because only the Python server (using the `service_role` key) ever talks to the database. There are no browser clients hitting Supabase directly. If a future phase adds multi-user support or browser-side reads, RLS should be enabled with appropriate policies.

### Data flow on save

1. User clicks "Save to Library" on `/add` after extraction succeeds
2. Browser sends `POST /save` with the extraction JSON, transcript, screen text, and original URL
3. Server calls `db_save_tiktok()` which:
   - Pulls city/country from `video_summary`
   - Builds the slug ID
   - Upserts the row into Supabase
4. Server responds with `{ok: true, id, city, country}`
5. Browser auto-redirects to `/city/<city>` so the user sees the new entry

---

## Real Example Output

Input: A TikTok photo carousel of favorite photo spots in Kyoto (`@ktdiaries_`)

<details>
<summary>Click to expand full JSON output</summary>

```json
{
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
      "parent_place": null,
      "map_search_query": "Kifune Shrine, Kyoto, Japan",
      "should_create_map_pin": true,
      "confidence": "high",
      "why_confidence": "Explicitly named in English and Japanese, with a full address provided.",
      "source_evidence": { "caption": false, "transcript": false, "ocr": true },
      "creator_notes": ["One of the creator's favorite photo locations"],
      "best_for": ["photography", "sightseeing", "nature"],
      "warnings_or_requirements": [],
      "mentioned_foods_or_items": [],
      "raw_mentions": ["180 Kuramakibunecho, Sakyo Ward, Kyoto, 601-1112, Japan", "Kifune Shrine"]
    },
    {
      "name": "Kurama Temple",
      "place_type": "temple",
      "city": "Kyoto",
      "country": "Japan",
      "parent_place": null,
      "map_search_query": "Kurama Temple, Kyoto, Japan",
      "should_create_map_pin": true,
      "confidence": "high",
      "why_confidence": "Explicitly named in Japanese and English.",
      "source_evidence": { "caption": false, "transcript": false, "ocr": true },
      "creator_notes": ["One of the creator's favorite photo locations"],
      "best_for": ["photography", "sightseeing", "history"],
      "warnings_or_requirements": [],
      "mentioned_foods_or_items": [],
      "raw_mentions": ["Kurama Temple"]
    },
    {
      "name": "Shogaku-ji Temple",
      "place_type": "temple",
      "city": "Kyoto",
      "country": "Japan",
      "parent_place": null,
      "map_search_query": "Shogaku-ji Temple, Sagatenryujitateishicho, Ukyo, Kyoto, Kyoto, Japan",
      "should_create_map_pin": true,
      "confidence": "high",
      "why_confidence": "Explicitly named with a full address string.",
      "source_evidence": { "caption": false, "transcript": false, "ocr": true },
      "creator_notes": ["One of the creator's favorite photo locations"],
      "best_for": ["photography", "sightseeing", "history"],
      "warnings_or_requirements": [],
      "mentioned_foods_or_items": [],
      "raw_mentions": ["Shogaku-ji Temple, Sagatenryujitateishicho, Ukyo, Kyoto, Kyoto, Japan"]
    }
  ],
  "non_place_notes": [
    {
      "type": "vibe",
      "text": "Mentions 'childbirth/safe delivery,' which is a common prayer theme at Japanese shrines.",
      "related_place": null
    },
    {
      "type": "activity",
      "text": "Mentions 'omamori' (amulets), suggesting these are available at the photo locations.",
      "related_place": null
    }
  ],
  "needs_user_review": [
    {
      "issue": "Specific place name for address '1, Saganonomiyacho, Ukyo, Kyoto'",
      "reason": "The video provides an address as a 'fav photo location' but does not explicitly name the place."
    },
    {
      "issue": "Specific place name for address '95-9, Oguracho Kasugamori, Uji, Kyoto'",
      "reason": "The video provides an address as a 'fav photo location' but does not explicitly name the place."
    }
  ]
}
```

</details>

---

## Technical Stack

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `yt-dlp` | latest | Download TikTok videos and audio |
| `opencv-python` | latest | Extract video frames at intervals |
| `google-genai` | latest | Gemini Vision (OCR) + Gemini 2.5 Flash (place extraction) |
| `assemblyai` | latest | Audio transcription (videos only) |
| `playwright` | latest | Headless Chromium browser (carousels only) |
| `python-dotenv` | latest | Load API keys from `.env` file |
| `supabase` | latest | Cloud database client for the web UI library |

### External APIs

| API | Used For | Required For |
|-----|----------|--------------|
| Google Gemini 2.5 Flash | OCR + place extraction | Both videos and carousels |
| AssemblyAI | Audio transcription | Videos only |
| TikTok oEmbed | Video captions | Videos only |
| Supabase | Persistent storage of saved TikToks | Web UI "Save to Library" feature |

### Two Interfaces

**CLI (`process_tiktok.py`):**
- Run from terminal
- Prints progress step-by-step
- Saves output to `final-extraction.json` (single file, overwritten each run)
- Best for: testing, automation, batch processing

**Web UI (`web_viewer.py`):**
- Run locally at `http://localhost:5050`
- Live progress logs stream to the browser during extraction
- **Library mode** — saved TikToks browsable by Country → City → TikTok
- **Save to Library** — persists results to Supabase after extraction
- Best for: building a personal travel knowledge base over time

---

## Known Limitations

1. **TikTok bot detection** — If TikTok updates their anti-bot measures, the carousel scraping approach could break
2. **Text-dependent** — If the creator doesn't overlay text or speak place names, there's nothing to extract
3. **English-optimized** — Works best with English text; other languages may produce lower quality results
4. **Image URL expiration** — TikTok carousel image URLs expire after a few hours; images must be downloaded immediately
5. **Rate limits** — Processing many URLs quickly may trigger TikTok rate limiting
6. **Private/deleted posts** — Returns empty results with no error message
7. **API costs** — Gemini Vision charges per image; a 9-image carousel costs more than a single video
8. **No caching** — Re-processing the same URL runs the full pipeline again
