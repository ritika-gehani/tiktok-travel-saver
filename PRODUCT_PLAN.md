# TikTok Travel Saver — Product Plan

> **Status:** Phase 1 (page scaffolding) shipped on 2026-04-29 — see commit `359577a`. Phase 2 (persistence) is next.
>
> _The country layer (Home → Country → City → TikTok) was added during Phase 1 in response to user feedback — it was not in the original draft. See "Information Architecture" below for the updated hierarchy._

---

## Glossary (what the AI output fields actually mean)

| Term | Plain English | Example |
|---|---|---|
| `video_summary` | AI-generated summary of the whole video — topic, city, vibe, usefulness. NOT the transcription. | `{"main_topic": "Favorite Photo Locations in Kyoto", "destination_city": "Kyoto", ...}` |
| Transcription / transcript | The creator's **spoken words** converted to text (by AssemblyAI). Separate from the summary. | "So these are my favorite spots in Kyoto, first up is Kifune Shrine..." |
| On-screen text / OCR | Text **visible on screen** in the video frames, extracted by Gemini Vision. | "Kifune Shrine", "180 Kuramakibunecho, Kyoto" |
| `places` | The list of real, map-pinnable locations the AI extracted. Each one becomes a place card. | Kifune Shrine, Kurama Temple, etc. |
| `non_place_notes` | Useful tips from the video that are **not tied to a specific place** — general travel advice, food tips, booking notes. | "Try omamori (amulets) at the shrines", "JR Pass covers the train" |
| `needs_user_review` | Things the AI wasn't sure about and wants YOU to double-check. | "Address given but no place name — which place is this?" |
| Backend routes / API endpoints | URLs your browser hits to talk to the Python server, which reads/writes the JSON data file. | `GET /api/tiktoks` = "give me all saved TikToks" |

---

## The Vision (in plain English)

Turn this app from a single-shot extraction tool into a **personal travel knowledge base** where:

1. Every TikTok you process becomes a **saved card** that lives in the app forever
2. Cards are **grouped by city** (e.g. all your Kyoto TikToks in one place)
3. Every card starts as **"Needs Review"** (red outline) — the AI did its best, but you're the final editor
4. You click into a card, **edit anything you want** (title, notes, tags, places)
5. You hit **"Mark as Reviewed"** → card turns green and is locked in as your trusted source
6. Eventually, this becomes your personal travel map / trip planner

**Design inspiration:** Clean iOS-style travel app (like the Yang Zihui mockup) — city cards with cover photos, tap into a city to see destinations, tap into a destination to see details and timeline.

---

## Information Architecture (4 levels)

```
Home Page (Countries)
   └── Country Page (e.g. "Japan")
          └── City Page (e.g. "Kyoto")
                 └── Detail Page (one TikTok — places, notes, all editable)
```

### Level 1 — Home Page (Countries)
- Shows a grid of **country cards** for every country where you've saved a TikTok
- Each country card shows:
  - Country name
  - City count + total TikTok count (e.g. "2 cities • 3 TikToks")
- Top right: **"+ Add TikTok"** button (see "Add TikTok Flow" below)
- **Status:** ✅ shipped in Phase 1 (with hardcoded data)

### Level 2 — Country Page (Cities)
- Shows all cities saved for the selected country as a **grid of cards**
- Each city card shows:
  - City name
  - TikTok count (e.g. "5 TikToks")
  - _(future)_ Cover image from the most recently added TikTok in that city
- Click → goes to city page
- **Status:** ✅ shipped in Phase 1 (with hardcoded data)

### Level 3 — City Page (TikToks)
- Shows all TikToks saved for the selected city as a **grid of cards**
- Each TikTok card shows:
  - **Cover image** (a screenshot from the video, or first photo of the carousel) _(Phase 2)_
  - Title (auto-generated from `main_topic`, editable later)
  - Author name (from TikTok)
  - Place count ("8 places")
  - **Red outline + "Needs Review" button** if not yet reviewed _(Phase 4)_
  - **Green outline + "Reviewed" label** once user confirms _(Phase 4)_
- Click anywhere on the card → goes to detail page
- **Status:** ✅ shipped in Phase 1 (without cover image / status badge yet)

### Level 4 — Detail Page (per TikTok)
- This is **everything we show today** in the existing single-page extraction view
- _(Phase 3)_ Edit affordances on every field — see "Editable Fields" below
- _(Phase 4)_ Top right: **"Mark as Reviewed"** button → status flips to reviewed
- **Status:** ✅ read-only view shipped in Phase 1; editing/review come later

---

## Editable Fields (the user becomes the final reviewer)

### Video Summary section
| Field | Edit type |
|---|---|
| Title (`main_topic`) | Inline text edit |
| Summary | Multi-line text edit |
| City | Inline text edit |
| Country | Inline text edit |
| Usefulness | Dropdown: high / medium / low |
| Vibe tags | Pill list — click x to delete, "+ add" to create new |

### Per-Place Card
| Field | Edit type |
|---|---|
| Name | Inline text edit |
| Place type | Dropdown (restaurant, cafe, landmark, etc.) |
| Parent place | Inline text edit |
| Confidence | Dropdown: high / medium / low |
| Creator notes | Each note is editable + deletable; "+ add note" button |
| Best-for tags | Pill list — click x to delete, "+ add" |
| Warnings | Each warning editable + deletable; "+ add" |
| Foods/items | Pill list — click x to delete, "+ add" |
| Map search query | Editable + click-to-copy + "Open in Google Maps" link |
| **Whole place** | Delete button (with confirmation) |

### Place list
- **"+ Add new place"** button at the bottom of the places section

### Notes section
- Each note: editable, deletable
- "+ Add note" button

### Needs-Review items (the AI's questions to you)
- Editable, deletable
- Once you've answered, you delete the item and it's gone

---

## Card States (the red/green outline system)

| Status | Outline | Label | Trigger |
|---|---|---|---|
| Needs Review | Red (e.g. `#fe2c55`) | "Needs Review" button | Default after extraction |
| Reviewed | Green (e.g. `#4cd964`) | "Reviewed" label/checkmark | User clicks "Mark as Reviewed" |
| (optional later) | Gray | "In Progress" | User started editing but didn't finish |

**Reversibility:** A reviewed card should have a "Mark as Needs Review Again" option in case you want to re-edit.

---

## "Add a TikTok" Flow (ADO-style city linking)

When the user clicks **"+ Add TikTok"**, a form/modal appears:

1. **URL input** — paste the TikTok link
2. **City selector dropdown** — shows all existing cities as pill tags
   - User can select an existing city (e.g. click the "Kyoto, Japan" pill)
   - OR click **"+ Create New City"** at the bottom of the dropdown
   - If they create a new city → they type city name + country → it becomes a new city on the home page
3. User hits **Enter / Submit**
4. Pipeline runs (with the existing progress bar + live log)
5. Result gets saved under the selected city
6. New TikTok card appears on that city's page with red "Needs Review" status

**Decision:** User picks the city **before** the pipeline runs. This way you always know exactly where it's going. No guessing, no surprises.

---

## What We Need to Build (technical pieces)

### A. Persistence Layer (the biggest missing piece)
**Right now:** Nothing is saved. Every browser refresh = empty page.
**Need:** A way to save extractions to disk so they persist across restarts.

**Two options:**
- **Option 1: JSON file** — A `data/tiktoks.json` file with a list of all saved TikToks. Simple, easy to inspect, no setup. Good for personal/local use.
- **Option 2: SQLite database** — A `data/tiktoks.db` file. Better for searching/filtering at scale, but adds complexity.

**Beginner recommendation:** Start with JSON. We can migrate later if needed.

### B. Cover Image Capture
- Currently we delete temp video/audio files at the end of the pipeline
- Need to **save one frame as the cover** before cleanup
- For videos: save the first or middle frame as `data/covers/<tiktok_id>.jpg`
- For carousels: save the first downloaded image

### C. Data Model

Each saved TikTok will be one record like this:

```json
{
  "id": "uuid-v4-string",
  "url": "https://www.tiktok.com/@user/video/123",
  "author": "user",
  "cover_image_path": "data/covers/abc123.jpg",
  "status": "needs_review",
  "created_at": "2026-04-29T16:00:00Z",
  "reviewed_at": null,
  "video_summary": { ...same as today... },
  "places": [ ...same as today... ],
  "non_place_notes": [ ...same as today... ],
  "needs_user_review": [ ...same as today... ],
  "transcript": "...",
  "screen_text": "..."
}
```

### D. New Backend Routes (the server endpoints we'll add)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Home page (list of cities) |
| GET | `/city/<city_name>` | City page (TikToks for that city) |
| GET | `/tiktok/<id>` | Detail page (one TikTok) |
| GET | `/api/tiktoks` | JSON of all saved TikToks |
| GET | `/api/tiktoks/<id>` | JSON of one TikTok |
| **PATCH** | `/api/tiktoks/<id>` | Update fields (title, places, etc.) |
| POST | `/api/tiktoks/<id>/review` | Mark as reviewed |
| DELETE | `/api/tiktoks/<id>` | Delete a TikTok |
| POST | `/start` | (existing) Run extraction pipeline → save result |
| GET | `/covers/<filename>` | Serve cover images |

---

## Build Order (phases)

### ✅ Phase 1: Page Scaffolding (DONE — 2026-04-29)
**What it gave us:** A working multi-page navigation skeleton with sample data, so we can see and tune the design before wiring up real data.

- New routes: `/`, `/country/<name>`, `/city/<name>`, `/tiktok/<id>`, plus existing `/add` for the extraction pipeline
- Hierarchical browsing: Home shows countries → click into country → cities → click into city → TikToks → click into TikTok → detail
- Hardcoded `FAKE_DATA` with 4 sample TikToks across Japan (Kyoto x2, Osaka x1) and Italy (Rome)
- Shared dark-mode `BASE_CSS`; server-side template injection via `{{...}}` placeholders
- `safe_json_for_html` helper for embedding JSON inside `<script>` tags safely
- Pipeline (`run_pipeline`) and CLI tool (`process_tiktok.py`) untouched

**Deferred to Phase 2:** persistence (everything is hardcoded sample data), cover images, connecting `/add` results to home page.

**Deferred to Phase 3+:** editing, review status badges, deletion.

### ⭐ Phase 2: Persistence + Wired-up Add Flow (NEXT)
**What it will give you:** TikToks persist across server restarts. `/add` actually saves results. Home/country/city/detail pages read real data instead of `FAKE_DATA`.

- Storage: `data/tiktoks.json` file with `load_tiktoks()` / `save_tiktoks()` helpers
- Capture cover image during pipeline → `data/covers/<tiktok_id>.jpg`
- Wire `/add` → after pipeline succeeds, show a **Save** form (city/country picker + Save button) → POST `/save` → append to JSON → redirect to `/tiktok/<new-id>`
- Replace `FAKE_DATA` references throughout `web_viewer.py` with file-loaded data
- Empty state on home page when nothing saved yet ("+ Add your first TikTok")
- Stable IDs (recommendation: slug from TikTok URL — e.g. `@user-1234567890`)

**Open sub-decisions for Phase 2:**
- _When does the user pick city/country?_ Original plan said *before* the pipeline runs. Easier interim: pick *after* extraction, with the AI's `destination_city` / `destination_country` as the default in the picker.
- _Cover image source?_ Middle frame of video / first carousel image. Probably middle frame is most representative.
- _Duplicates?_ If the same URL is saved twice, do we update or create new? (Recommend: warn + offer to update.)

**Out of scope (deferred to Phase 3):** editing, status changes, deletion.

### Phase 3: Edit Mode (the big one)
- Make every field editable inline on the detail page
- Tag add/remove UI (pill list with × buttons)
- Add/delete places, notes, warnings
- PATCH endpoint to save edits
- Auto-save on blur (or explicit "Save" button — we'll decide)

### Phase 4: Review Workflow
- "Mark as Reviewed" button on detail page
- Status badges and outline colors on cards (red/green) — already CSS-ready in `BASE_CSS`
- "Mark as Needs Review Again" to revert
- Optional: filter cards by status

### Phase 5: Polish
- "Open in Google Maps" link on every place
- Click-to-copy on map search query
- Confirmation modals for destructive actions (delete place, delete TikTok)
- Better mobile responsive layout
- Search bar on home page
- Sort options (most recent, alphabetical, # of places)
- Address city-name ambiguity: if two cities share a name across countries (e.g. "Kyoto, Japan" vs hypothetical "Kyoto, US"), use country-qualified URLs like `/city/<country>/<name>` or unique IDs

### Phase 6 (future / dreamy)
- Embedded map view showing all your saved places as pins
- Export trip plan to PDF / Apple Maps / Google My Maps
- Multiple users / login (if this ever becomes a real product)
- Auto-detect duplicate TikToks (same URL processed twice)

---

## Open Questions (let's decide before building)

1. **Storage:** JSON file or SQLite? (My recommendation: JSON for now — the backend routes/API endpoints read and write to this file)
2. **Duplicates:** If you process the same TikTok URL twice, do we update the existing one or create a new entry?
3. **Cover image source:** First frame of video? Middle frame? Or let user pick?
4. **Auto-save vs explicit save:** When you edit a field, should it save immediately on blur, or do we add a "Save" button?
5. **Undo:** If you delete a place by accident, should there be an undo? (Adds complexity.)
6. **Title editability:** The title (`main_topic`) is AI-generated. Should the original be preserved somewhere even if user edits?
7. **Review lock:** When a TikTok is "Reviewed", should it become read-only? Or still editable but with a different visual state?
8. **Empty state:** First time you open the app (no TikToks saved yet) — what does home page show? (Probably an empty-state with a big "+ Add your first TikTok" call to action.)
9. ~~City selection timing~~ **REVISITED IN PHASE 2:** original plan said *before* pipeline runs. Phase-2 sub-decision is whether to keep that or let user pick *after* extraction with AI's city as default.
10. ~~AI city as default~~ **REVISITED IN PHASE 2:** if we pick after extraction, AI's `destination_city` becomes the prefilled value.
11. ~~Information architecture: 3 vs 4 levels~~ **DECIDED (Phase 1):** 4 levels — Home (countries) → Country (cities) → City (TikToks) → Detail.

---

## What Stays the Same

- Pipeline logic (`run_pipeline()` in `web_viewer.py`) — unchanged
- Gemini prompt + JSON schema — unchanged
- API keys + `.env` — unchanged
- Existing CLI tool (`process_tiktok.py`) — unchanged

We're only adding a UI/persistence layer **on top of** what works today.

---

## Where We Are Now

- ✅ **Phase 1 shipped** — see commit `359577a`. Open `http://localhost:5050` to click through the new navigation.
- ⭐ **Phase 2 is next** — persistence + connecting `/add`. Before building, decide:
  - When does the user pick city/country (before vs after pipeline)?
  - Cover image: middle frame of video?
  - Duplicate-URL handling: warn + offer to update, or always create new?
- Open Questions 1–8 above are still on the table; questions 9–11 are now decided/revisited.
