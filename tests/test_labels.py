"""Controlled vocabulary: every label the AI can emit is snapped to a fixed set."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import labels
from labels import for_ui, keys, normalize_extraction, snap, snap_list


def test_every_group_has_unique_keys_and_help_text():
    for group in labels.GROUPS:
        items = labels.GROUPS[group]
        assert len({i["key"] for i in items}) == len(items)
        assert all(i["label"] and i["help"] for i in items)


def test_canonical_keys_pass_through():
    for group in labels.GROUPS:
        for key in keys(group):
            assert snap(group, key) == key


@pytest.mark.parametrize("value, expected", [
    ("restaurant", "food"),
    ("Taqueria", "food"),
    ("coffee shop", "cafe"),
    ("café", "cafe"),
    ("winery", "bar"),
    ("izakaya", "food"),
    ("sake bar", "bar"),
    ("restaraunt", "food"),
    ("ramen shop", "food"),
    ("night market", "shopping"),
    ("shrine", "sight"),
    ("temple", "sight"),
    ("viewpoint", "sight"),
    ("landmark", "sight"),
    ("bookshop", "shopping"),
    ("Onsen", "activity"),
    ("ryokan", "hotel"),
    ("train station", "transit"),
    ("Neighbourhood", "neighborhood"),
])
def test_place_type_synonyms_and_spellings(value, expected):
    assert snap("place_types", value) == expected


@pytest.mark.parametrize("value, expected", [
    ("sunset", "views"),
    ("sightseeing", "first-timer"),
    ("casual exploring", "relaxed"),
    ("evening stroll", "relaxed"),
    ("late night", "nightlife"),
    ("live music", "nightlife"),
    ("local favorites", "local-favorite"),
    ("hidden gem", "local-favorite"),
    ("street food", "food"),
    ("hiking", "adventure"),
    ("family friendly", "with-kids"),
    ("romantic", "date-night"),
    ("cheap eats", "budget"),
    ("luxury", "splurge"),
])
def test_tag_synonyms(value, expected):
    assert snap("tags", value) == expected


def test_unknown_values_fall_back():
    assert snap("place_types", "spaceport") is None
    assert snap("place_types", "spaceport", default="other") == "other"
    assert snap("tags", "") is None
    assert snap("tags", None) is None


def test_close_spelling_never_flips_meaning():
    assert snap("confidence", "certain") == "high"
    assert snap("confidence", "uncertain") == "low"
    assert snap("place_types", "car") is None


def test_snap_list_dedupes_drops_unknowns_and_limits():
    tags = snap_list("tags", ["Sunset", "views", "??", "history", "History", "budget", "food", "relaxed"], limit=4)
    assert tags == ["views", "history", "budget", "food"]


def test_normalize_extraction_rewrites_every_label_field():
    raw = {
        "video_summary": {
            "usefulness_for_itinerary": "HIGH",
            "overall_vibe": ["street food", "late night", "??", "local favorites", "budget", "views"],
        },
        "places": [
            {"name": "A", "place_type": "taqueria", "confidence": "med", "best_for": ["dinner", "late night"]},
            {"name": "B", "place_type": "spaceport", "confidence": "certain", "best_for": None},
            "not a dict",
        ],
        "non_place_notes": [{"type": "warning", "text": "x"}, {"type": "???", "text": "y"}],
        "needs_user_review": ["kept as is"],
    }
    out = normalize_extraction(raw)

    assert out["video_summary"]["usefulness_for_itinerary"] == "high"
    assert out["video_summary"]["overall_vibe"] == ["food", "nightlife", "local-favorite", "budget"]
    a, b = out["places"]  # non-dict junk is dropped
    assert (a["place_type"], a["confidence"], a["best_for"]) == ("food", "medium", ["food", "nightlife"])
    assert (b["place_type"], b["confidence"], b["best_for"]) == ("other", "high", [])
    assert [n["type"] for n in out["non_place_notes"]] == ["tip", "unknown"]
    assert out["needs_user_review"] == ["kept as is"]
    assert raw["places"][0]["place_type"] == "taqueria", "input must not be mutated"


def test_normalize_extraction_is_idempotent_and_tolerates_empty():
    empty = normalize_extraction({})
    assert empty["places"] == [] and empty["video_summary"]["usefulness_for_itinerary"] == "medium"
    once = normalize_extraction({"places": [{"place_type": "shrine"}]})
    assert normalize_extraction(once) == once


def test_seed_library_only_uses_controlled_labels():
    with open(os.path.join(ROOT, "data", "seed-library.json")) as f:
        seed = json.load(f)
    place_types, tags, note_types = set(keys("place_types")), set(keys("tags")), set(keys("note_types"))
    for row in seed["tiktoks"]:
        data = row["data"]
        assert set(data["video_summary"]["overall_vibe"]) <= tags
        for place in data["places"]:
            assert place["place_type"] in place_types
            assert set(place.get("best_for", [])) <= tags
            assert place["confidence"] in keys("confidence")
        for note in data["non_place_notes"]:
            assert note["type"] in note_types


def test_prompt_lists_the_exact_vocabulary():
    with open(os.path.join(ROOT, "prompt-extract-places.txt")) as f:
        prompt = f.read()
    for key in keys("place_types"):
        assert f"\n- {key} " in prompt, key
    for key in keys("tags"):
        assert f"\n- {key} " in prompt, key
    for key in keys("note_types"):
        assert key in prompt


def test_for_ui_exposes_only_presentational_fields():
    ui = for_ui()
    assert set(ui) == set(labels.GROUPS)
    for items in ui.values():
        assert all(set(i) == {"key", "label", "help"} for i in items)
