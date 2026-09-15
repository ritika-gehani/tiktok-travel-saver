"""
Offline country → city lookup used by the "Create trip" typeahead.

Backed by data/destinations.json (regenerate with scripts/build_destinations.py).
Matching is case- and accent-insensitive; prefix matches rank first, then
substring matches, each in the dataset's order (largest cities first).
Cities also match through their bundled aliases (Seville → Sevilla), but the
canonical name is what gets shown and stored.
"""
import json
import os
import unicodedata

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(PROJECT_DIR, "data", "destinations.json")

with open(DATA_FILE, encoding="utf-8") as _f:
    _COUNTRIES: dict[str, dict] = json.load(_f)


def fold(s: str) -> str:
    """Lowercase and strip accents so 'Kyōto' matches 'kyoto'."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)
    ).lower().strip()


_COUNTRY_INDEX = {fold(name): name for name in _COUNTRIES}
_CITY_INDEX = {
    name: {
        **{fold(alias): city for alias, city in info.get("aliases", {}).items()},
        **{fold(city): city for city in info["cities"]},
    }
    for name, info in _COUNTRIES.items()
}


def _rank(candidates: list[str], q: str, limit: int, aliases: dict[str, str] | None = None) -> list[str]:
    q = fold(q)
    if not q:
        return candidates[:limit]
    prefix, word, inner = [], [], []
    for c in candidates:
        f = fold(c)
        if f.startswith(q):
            prefix.append(c)
        elif any(w.startswith(q) for w in f.replace("-", " ").split()):
            word.append(c)
        elif len(q) >= 3 and q in f:
            inner.append(c)
    ranked = prefix + word + inner
    if aliases and len(ranked) < limit:
        seen = set(ranked)
        for alias, canonical in aliases.items():
            if canonical not in seen and fold(alias).startswith(q):
                seen.add(canonical)
                ranked.append(canonical)
    return ranked[:limit]


def search_countries(q: str, limit: int = 8) -> list[dict]:
    return [
        {"name": name, "code": _COUNTRIES[name]["code"], "flag": flag(_COUNTRIES[name]["code"])}
        for name in _rank(list(_COUNTRIES), q, limit)
    ]


def search_cities(country: str, q: str, limit: int = 8) -> list[str]:
    canonical = canonical_country(country)
    if not canonical:
        return []
    info = _COUNTRIES[canonical]
    return _rank(info["cities"], q, limit, info.get("aliases"))


def canonical_country(country: str) -> str | None:
    return _COUNTRY_INDEX.get(fold(country))


def canonical_city(country: str, city: str) -> str | None:
    canonical = canonical_country(country)
    if not canonical:
        return None
    return _CITY_INDEX[canonical].get(fold(city))


def country_code(country: str) -> str:
    canonical = canonical_country(country)
    return _COUNTRIES[canonical]["code"] if canonical else ""


def flag(code: str) -> str:
    """Regional-indicator emoji for a two-letter ISO country code."""
    if len(code) != 2:
        return "🌍"
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code.upper())
