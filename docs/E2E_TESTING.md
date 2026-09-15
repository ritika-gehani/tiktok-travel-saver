# E2E testing guide — TikTok Travel Saver

How to run the app offline, walk every core flow, and report/fix what breaks.
Written for the weekly Devin regression sweep, but works for humans too.

## 1. What the app is

A small stdlib-Python web app (`web_viewer.py` + `templates/`) that files TikTok
travel videos into **trips — one trip per city**. Screens:

| Route | Screen |
|---|---|
| `/` | Home: greeting, stats (trips / TikToks / places / to review), search, trip cards, "Recent saves", **New trip** sheet |
| `/trip/<id>` | Trip page: paste box, saved TikToks, "Places so far" grouped by type |
| `/tiktok/<id>` | Detail page: summary, labels, places, "Looks good — approve" / "Undo approval" |
| `/how-it-works` | Plain-language explanation of the app and every label |
| `/add?trip=<id>` | Paste-a-TikTok extraction flow (needs API keys; see §5) |
| `/api/destinations` | Country / city typeahead JSON used by New trip |

## 2. Run it offline for testing

```bash
python3 -m venv .venv && source .venv/bin/activate
make install                                   # python-dotenv, supabase, pytest
LIBRARY_FILE=$(mktemp -d)/library.json PORT=5050 make run
# → http://localhost:5050  (seeded from data/seed-library.json on first load)
make test                                      # pytest -q, 70 tests, must stay green
```

- No API keys or Supabase needed. Always point `LIBRARY_FILE` at a throwaway copy
  so the seed library is never mutated between runs.
- Templates are loaded at import time: **restart the server after editing anything
  in `templates/`**.
- Seed data: 5 trips (Tokyo, Kyoto, Lisbon, Porto, Mexico City), 5 TikToks
  (one per trip, all `needs_review`), 19 places.

## 3. Golden-path test script

Start screen-recording before step 1. Annotate each numbered flow as it starts and
each expected result as an assertion.

1. **Home loads with seeded content** — Open `/`. Expect: a greeting, four stats
   reading `5 trips · 5 TikToks · 19 places · 5 to review`, "5 cities", five trip
   cards each showing `Country · <dates or "no dates yet">` (Tokyo, Kyoto, Mexico
   City have dates; Lisbon and Porto don't), `1 TikTok · N places`, a mode pill
   (Kyoto = "Itinerary", others "Collect ideas"), a `1 to review` pill, plus an
   "Add another city" card, and a "Recent saves" row with 5 entries.
2. **Search filters trips** — Type `lis` in the search box. Expect: only the Lisbon
   card and matching recent saves remain; "1 city". Clear it: all cards return.
3. **Search no-match** — Type `zzzz`. Expect: "Nothing matches that search." and
   "0 cities"; the Add card is hidden too. Press **Escape** while focused: box
   clears, everything returns. From the page body press **`/`**: search gains
   focus. Press **`n`**: the New trip sheet opens (Escape closes it).
4. **New trip — country typeahead** — Click **New trip**. Type `jap`. Expect: a
   menu with "Japan" and its flag, match highlighted; city box is disabled until a
   country is picked. Type `zzz`: menu shows `No country named "zzz"` + spelling
   hint. Pick Japan: flag appears, city box enables and is focused.
5. **New trip — unknown city** — With Japan picked, type `Atlantis` in city.
   Expect: `No city named "Atlantis" in Japan`, Create button stays disabled.
6. **New trip — duplicate city** — Type `Tok`, pick Tokyo. Expect: the note
   "You already have a Tokyo trip. Open it →" and the button reads
   "Create another Tokyo trip". The link opens `/trip/tokyo-japan`.
7. **New trip — create** — Pick Japan → Osaka, leave dates empty, click
   **Create trip**. Expect: redirect to `/trip/osaka-japan` showing "Osaka" with an
   empty TikTok list. Back on `/`, stats read 6 trips and an Osaka card exists.
   Also try an end date before the start date: inline error "The end date is
   before the start date.", no request sent.
8. **Trip page** — Open `/trip/kyoto-japan`. Expect: city heading, "How it works"
   link, a paste box, "Saved TikToks" (1) with topic/author/places, and "Places so
   far" grouped by place type with counts. Clicking a TikTok opens its detail page.
9. **Detail page — approve & undo** — From Kyoto open the TikTok. Expect: back link
   to the trip, summary, label chips with hover explanations, places list, status
   "Check the places below, then approve." Click **Looks good — approve**: button
   becomes **Undo approval**, status reads "Approved …". Reload: still approved;
   home "to review" drops to 4 and the Kyoto card loses its review pill. Click
   **Undo approval**: back to needs review everywhere.
10. **How it works** — Open `/how-it-works` (also via the header link and the
    detail page's "What do these labels mean?" → `#labels`). Expect: the intro plus
    sections Place types, Tags, Confidence, Usefulness, Sources, Notes, each label
    with a one-line meaning that matches `labels.py`.
11. **/add error path** — Open `/add?trip=kyoto-japan`, paste
    `https://www.tiktok.com/@x/video/1`, submit. Expect: the run ends with
    "Extraction failed" and the log says extraction dependencies are not
    installed. The UI must not hang or throw. `/add?trip=nope` → 404.
12. **404s** — `/trip/nope`, `/tiktok/nope`, `/nowhere` return HTTP 404 with a
    plain-text message; `/api/destinations?country=Narnia` returns 404 JSON.

Finally re-run `make test` — it must still report 70 passed.

## 4. Bug vs expected behaviour

**A bug**: a step above does not produce its expected result; a JS error in the
console; a 500; stale state after reload; a control that does nothing; text that
is cut off / overlapping at a normal desktop width; a label not in `labels.py`.

**Expected, not a bug**: `/add` failing without extraction deps or API keys;
Supabase being unused; `/status` returning a mostly-empty JSON object;
greeting changing with time of day; date display using en-US short months;
duplicate city trips being allowed after the warning.

## 5. Reporting conventions

- **One issue per bug.** Title: `[E2E] <flow>: <symptom>` (e.g.
  `[E2E] Search: Escape does not clear the box`).
- Required sections: **Steps**, **Expected**, **Actual**, **Evidence** (screenshot
  and/or recording timestamp), **Suspected cause** (file + line if known).
- **One branch + one PR per bug**, named `devin/e2e-fix-<slug>`. The PR must link
  the issue (`Fixes #N`), attach the fix recording, and add a pytest regression test
  in `tests/` that fails before and passes after the change. `make test` green.
- Never merge; a human reviews and merges.

## 6. Coding conventions for fixes

- Stdlib only; no new dependencies, no changes to `requirements*.txt`.
- Don't touch the extraction pipeline (`run_pipeline`, `process_tiktok.py`,
  `extract-places.py`, the prompt) or the Supabase path in `db.py`.
- Smallest safe change; prefer fixing the root cause over patching the symptom.
- Keep the light Notion-style design (`templates/base.css` tokens); no redesigns.
- Never edit or delete existing tests to make them pass — add new ones.
- Templates load at import time: restart the server to see template edits.
