#!/usr/bin/env python3
"""
Regenerate data/destinations.json — the offline country → cities list that
powers the "Create trip" typeahead.

Source: the GeoNames cities15000 dataset via the `geonamescache` package
(cities with population >= 15,000). Cities are stored largest-first so the
typeahead can rank prefix matches by population without storing it.

For larger cities (population >= 100,000) we also keep close-spelling
alternate names (Seville → Sevilla, Lisboa → Lisbon, München → Munich) so a
traveller's spelling still finds the canonical entry. Aliases are matched,
never displayed.

Usage:
    pip install geonamescache
    python3 scripts/build_destinations.py
"""
import difflib
import json
import os
import re
import unicodedata
from collections import defaultdict

import geonamescache

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "destinations.json")
ALIAS_MIN_POPULATION = 100_000
ALIAS_SHAPE = re.compile(r"^[A-Z][A-Za-z' -]{3,}$")
ALIAS_MIN_SIMILARITY = 0.7


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def aliases_for(city: dict) -> list[str]:
    if city["population"] < ALIAS_MIN_POPULATION:
        return []
    base = fold(city["name"])
    seen, out = {base}, []
    for alt in city.get("alternatenames", []):
        f = fold(alt)
        if not alt.isascii() or not ALIAS_SHAPE.match(alt) or len(alt.split()) > 2 or f in seen:
            continue
        if difflib.SequenceMatcher(None, base, f).ratio() < ALIAS_MIN_SIMILARITY:
            continue
        seen.add(f)
        out.append(alt)
    return out


def main() -> None:
    gc = geonamescache.GeonamesCache()
    countries = gc.get_countries()
    by_country: dict[str, list[dict]] = defaultdict(list)
    for city in gc.get_cities().values():
        country = countries.get(city["countrycode"])
        if country:
            by_country[country["name"]].append(city)

    out = {}
    for code, country in countries.items():
        cities = by_country.get(country["name"])
        if not cities:
            continue
        seen: set[str] = set()
        ordered: list[str] = []
        aliases: dict[str, str] = {}
        for city in sorted(cities, key=lambda c: -c["population"]):
            name = city["name"]
            if name in seen:
                continue
            seen.add(name)
            ordered.append(name)
            for alias in aliases_for(city):
                aliases.setdefault(alias, name)
        canonical_folded = {fold(n) for n in ordered}
        aliases = {a: n for a, n in aliases.items() if fold(a) not in canonical_folded}
        out[country["name"]] = {"code": code, "cities": ordered, "aliases": aliases}

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(out.items())), f, ensure_ascii=False, separators=(",", ":"))
    n_cities = sum(len(v["cities"]) for v in out.values())
    n_aliases = sum(len(v["aliases"]) for v in out.values())
    print(f"Wrote {len(out)} countries, {n_cities} cities, {n_aliases} aliases → {OUT}")


if __name__ == "__main__":
    main()
