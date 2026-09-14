"""Controlled vocabulary for every label the app shows.

The extraction prompt asks Gemini to pick from these lists, and
`normalize_extraction` snaps whatever comes back (or was saved before the
lists existed) onto them so a trip never ends up with "cafe", "café",
"coffee shop" and "coffee" as four different labels.

Each group is an ordered list of {key, label, help, synonyms}. `key` is what
gets stored, `label` is what the UI shows, `help` is the one-line explanation
on the "How it works" page, `synonyms` are alternate spellings we map onto it.
"""

from __future__ import annotations

import difflib
import re

PLACE_TYPES = [
    {"key": "food", "label": "Food", "help": "Restaurants, street-food stalls, bakeries, taquerias — anywhere you go to eat.",
     "synonyms": ["restaurant", "eatery", "diner", "taqueria", "bakery", "ramen", "izakaya", "street food", "food stall", "market stall", "pizzeria", "bistro", "food hall", "dessert shop", "ice cream"]},
    {"key": "cafe", "label": "Café", "help": "Coffee, tea and dessert spots — places to sit down for a bit.",
     "synonyms": ["café", "coffee", "coffee shop", "tea house", "teahouse", "matcha", "patisserie"]},
    {"key": "bar", "label": "Bar & drinks", "help": "Bars, wineries, breweries, cocktail spots and nightlife venues.",
     "synonyms": ["pub", "winery", "brewery", "wine bar", "cocktail bar", "nightclub", "club", "nightlife", "lounge", "sake bar", "rooftop bar"]},
    {"key": "sight", "label": "Sightseeing", "help": "Landmarks, temples, shrines, monuments, museums and viewpoints.",
     "synonyms": ["landmark", "attraction", "temple", "shrine", "monument", "museum", "gallery", "viewpoint", "overlook", "castle", "palace", "church", "cathedral", "tower", "observation deck", "historic site", "ruins"]},
    {"key": "nature", "label": "Nature", "help": "Parks, gardens, beaches, hikes, mountains and other outdoor spots.",
     "synonyms": ["park", "garden", "beach", "hike", "trail", "mountain", "forest", "lake", "waterfall", "island", "national park", "bamboo grove"]},
    {"key": "neighborhood", "label": "Neighborhood", "help": "Districts, streets and areas worth wandering rather than a single address.",
     "synonyms": ["district", "area", "street", "quarter", "old town", "alley", "ward", "town"]},
    {"key": "shopping", "label": "Shopping", "help": "Shops, markets, malls and bookstores.",
     "synonyms": ["shop", "store", "market", "mall", "bookshop", "bookstore", "boutique", "flea market", "department store", "souvenir shop", "vintage"]},
    {"key": "activity", "label": "Activity", "help": "Things you do rather than see — tours, classes, theme parks, baths, shows.",
     "synonyms": ["experience", "tour", "class", "workshop", "theme park", "amusement park", "onsen", "hot spring", "spa", "bathhouse", "show", "theater", "theatre", "stadium", "arcade", "karaoke"]},
    {"key": "hotel", "label": "Stay", "help": "Hotels, hostels, ryokans and other places to sleep.",
     "synonyms": ["hostel", "ryokan", "accommodation", "lodging", "guesthouse", "airbnb", "resort", "stay"]},
    {"key": "transit", "label": "Transit", "help": "Stations, airports, ferries and passes — how you get around.",
     "synonyms": ["station", "train station", "airport", "ferry", "bus", "metro", "subway", "port", "terminal", "transport", "transportation"]},
    {"key": "other", "label": "Other", "help": "A real place that doesn't fit the categories above.",
     "synonyms": ["unknown", "misc", "place"]},
]

TAGS = [
    {"key": "views", "label": "Views", "help": "Skylines, sunsets, lookouts — go for the view.",
     "synonyms": ["view", "sunset", "sunrise", "skyline", "scenic", "panorama", "lookout"]},
    {"key": "photography", "label": "Photo spot", "help": "Especially photogenic; creators call these out for pictures.",
     "synonyms": ["photo", "photos", "photo spot", "instagram", "instagrammable", "aesthetic", "picturesque"]},
    {"key": "history", "label": "History & culture", "help": "Temples, old towns, museums, traditions.",
     "synonyms": ["historic", "historical", "culture", "cultural", "heritage", "architecture", "traditional", "art"]},
    {"key": "local-favorite", "label": "Local favorite", "help": "Hidden gems and places locals actually go, not tourist traps.",
     "synonyms": ["local favorites", "local", "locals", "hidden gem", "off the beaten path", "authentic", "underrated", "non-touristy"]},
    {"key": "food", "label": "Food & drink", "help": "Mostly about eating and drinking — restaurants, street food, markets.",
     "synonyms": ["street food", "snacks", "market food", "food market", "food and wine", "eating", "foodie", "lunch", "dinner", "brunch", "breakfast", "food tour", "restaurants"]},
    {"key": "nightlife", "label": "Nightlife", "help": "Best after dark — bars, late-night eats, live music.",
     "synonyms": ["late night", "night", "evening", "bars", "drinks", "live music", "party", "night out"]},
    {"key": "relaxed", "label": "Relaxed", "help": "Slow wandering, strolls, cafés — no schedule needed.",
     "synonyms": ["relax", "chill", "casual", "casual exploring", "walking", "walk", "stroll", "evening stroll", "slow", "leisurely", "wander", "peaceful", "quiet"]},
    {"key": "adventure", "label": "Active", "help": "Hikes, cycling, water sports — you'll break a sweat.",
     "synonyms": ["active", "hiking", "hike", "outdoors", "outdoor", "cycling", "biking", "surfing", "sports", "nature", "trek"]},
    {"key": "budget", "label": "Budget", "help": "Free or cheap.",
     "synonyms": ["cheap", "free", "affordable", "inexpensive", "budget-friendly", "value"]},
    {"key": "splurge", "label": "Splurge", "help": "Fine dining, luxury stays, big-ticket experiences.",
     "synonyms": ["luxury", "fine dining", "upscale", "expensive", "fancy", "high-end", "michelin", "treat"]},
    {"key": "first-timer", "label": "First-timer", "help": "Classic must-sees if it's your first visit.",
     "synonyms": ["first time", "first-time visitor", "first time visitor", "must see", "must-see", "must do", "must-do", "classic", "iconic", "popular", "famous", "sightseeing", "touristy", "bucket list"]},
    {"key": "with-kids", "label": "With kids", "help": "Family-friendly.",
     "synonyms": ["kids", "family", "family-friendly", "family friendly", "children", "child-friendly"]},
    {"key": "date-night", "label": "Date night", "help": "Romantic — dinners, sunsets, quiet corners.",
     "synonyms": ["romantic", "date", "couples", "honeymoon", "anniversary"]},
    {"key": "rainy-day", "label": "Rainy day", "help": "Indoors — good when the weather turns.",
     "synonyms": ["indoor", "indoors", "rain", "bad weather", "museum day"]},
]

CONFIDENCE = [
    {"key": "high", "label": "High", "help": "Named clearly, usually in more than one source. Safe to plan around.", "synonyms": ["certain", "confident", "very high", "sure"]},
    {"key": "medium", "label": "Medium", "help": "Probably right, but only mentioned once or a little vaguely. Worth a quick check.", "synonyms": ["med", "moderate"]},
    {"key": "low", "label": "Low", "help": "Ambiguous — might be a generic category or a mis-hearing. Verify before trusting.", "synonyms": ["uncertain", "unsure", "very low"]},
]

USEFULNESS = [
    {"key": "high", "label": "High usefulness", "help": "Specific, named places you can put on an itinerary.", "synonyms": []},
    {"key": "medium", "label": "Medium usefulness", "help": "Some concrete places, mixed with general vibes or tips.", "synonyms": ["med", "moderate"]},
    {"key": "low", "label": "Low usefulness", "help": "Mostly mood or general advice; few or no specific places.", "synonyms": []},
]

SOURCES = [
    {"key": "caption", "label": "Caption", "help": "The text the creator wrote when posting.", "synonyms": []},
    {"key": "transcript", "label": "Transcript", "help": "What the creator said out loud, transcribed from the audio.", "synonyms": []},
    {"key": "ocr", "label": "On-screen text", "help": "Text that appeared in the video or carousel images, read by OCR.", "synonyms": []},
]

NOTE_TYPES = [
    {"key": "food", "label": "Food", "help": "Dishes or drinks to try, not tied to one pinnable place.", "synonyms": ["dish", "drink"]},
    {"key": "tip", "label": "Tip", "help": "General advice or a heads-up from the creator.", "synonyms": ["warning", "advice", "note", "etiquette", "safety"]},
    {"key": "activity", "label": "Activity", "help": "Something to do that isn't a single named place.", "synonyms": ["experience", "thing to do"]},
    {"key": "vibe", "label": "Vibe", "help": "How the creator described the feel of an area or trip.", "synonyms": ["mood", "atmosphere"]},
    {"key": "booking", "label": "Booking", "help": "Reservations, tickets, things to book ahead.", "synonyms": ["reservation", "tickets", "ticket"]},
    {"key": "transportation", "label": "Getting around", "help": "Trains, passes, walking routes, how to get somewhere.", "synonyms": ["transport", "transit", "directions", "travel"]},
    {"key": "cost", "label": "Cost", "help": "Prices, budgets, what's free.", "synonyms": ["price", "budget", "money"]},
    {"key": "timing", "label": "Timing", "help": "Best time of day, season, opening hours, how long to spend.", "synonyms": ["time", "hours", "season", "schedule", "when to go"]},
    {"key": "unknown", "label": "Other", "help": "Doesn't fit the other note types.", "synonyms": ["other", "misc"]},
]

GROUPS = {
    "place_types": PLACE_TYPES,
    "tags": TAGS,
    "confidence": CONFIDENCE,
    "usefulness": USEFULNESS,
    "sources": SOURCES,
    "note_types": NOTE_TYPES,
}

_FOLD_RE = re.compile(r"[^a-z0-9]+")


def fold(text: str) -> str:
    return _FOLD_RE.sub(" ", (text or "").lower()).strip()


def _index(group: list[dict]) -> dict[str, str]:
    idx: dict[str, str] = {}
    for item in group:
        for alias in [item["key"], item["label"], *item["synonyms"]]:
            idx.setdefault(fold(alias), item["key"])
    return idx


_INDEXES = {name: _index(group) for name, group in GROUPS.items()}
_KEYS = {name: [item["key"] for item in group] for name, group in GROUPS.items()}


def snap(group: str, value: str | None, default: str | None = None) -> str | None:
    """Map a free-text value onto a key in `group`.

    Exact key/label/synonym match first, then a close-spelling match
    (`difflib` ratio >= 0.85 and same first letter, so "restaraunt" -> food
    but "certain" never becomes "uncertain"). Returns `default` when nothing fits.
    """
    f = fold(value) if isinstance(value, str) else ""
    if not f:
        return default
    idx = _INDEXES[group]
    if f in idx:
        return idx[f]
    close = difflib.get_close_matches(f, [k for k in idx if k[:1] == f[:1]], n=1, cutoff=0.85)
    if close:
        return idx[close[0]]
    # "coffee shops" -> "coffee shop"
    if f.endswith("s") and f[:-1] in idx:
        return idx[f[:-1]]
    # "ramen shop" -> ramen -> food; "night market" -> market -> shopping.
    # The modifier usually carries the meaning, so try words left to right.
    words = f.split()
    if len(words) > 1:
        for w in words:
            if w in idx:
                return idx[w]
    return default


def snap_list(group: str, values, limit: int | None = None) -> list[str]:
    """Snap a list of free-text tags, dropping unknowns and duplicates."""
    out: list[str] = []
    for v in values or []:
        key = snap(group, v)
        if key and key not in out:
            out.append(key)
    return out[:limit] if limit else out


def keys(group: str) -> list[str]:
    return list(_KEYS[group])


def normalize_extraction(extraction: dict) -> dict:
    """Return a copy of a Gemini extraction with every label snapped to the vocabulary."""
    if not isinstance(extraction, dict):
        return extraction
    out = dict(extraction)

    summary = dict(out.get("video_summary") or {})
    summary["overall_vibe"] = snap_list("tags", summary.get("overall_vibe"), limit=4)
    summary["usefulness_for_itinerary"] = snap(
        "usefulness", summary.get("usefulness_for_itinerary"), default="medium")
    out["video_summary"] = summary

    places = []
    for p in out.get("places") or []:
        if not isinstance(p, dict):
            continue
        p = dict(p)
        p["place_type"] = snap("place_types", p.get("place_type"), default="other")
        p["confidence"] = snap("confidence", p.get("confidence"), default="medium")
        p["best_for"] = snap_list("tags", p.get("best_for"), limit=4)
        places.append(p)
    out["places"] = places

    notes = []
    for n in out.get("non_place_notes") or []:
        if not isinstance(n, dict):
            continue
        n = dict(n)
        n["type"] = snap("note_types", n.get("type"), default="unknown")
        notes.append(n)
    out["non_place_notes"] = notes
    return out


def for_ui() -> dict:
    """Groups with keys, labels and help text, for embedding in pages."""
    return {
        name: [{"key": i["key"], "label": i["label"], "help": i["help"]} for i in group]
        for name, group in GROUPS.items()
    }
