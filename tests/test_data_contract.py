import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "bnti_data.json").read_text(encoding="utf-8"))
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
MAP_JS = (ROOT / "js" / "map.js").read_text(encoding="utf-8")
STREAM_JS = (ROOT / "js" / "stream.js").read_text(encoding="utf-8")

COUNTRIES = {"Armenia", "Georgia", "Greece", "Iran", "Iraq", "Syria", "Bulgaria"}


def test_dataset_shape_scores_and_map_country_paths_are_preserved():
    assert set(DATA) == {"meta", "countries", "history", "forecast", "early_warning", "methodology", "briefing"}
    assert set(DATA["countries"]) == COUNTRIES
    assert DATA["methodology"]["formula"] == (
        "PerCountry = 1 + 9*(1 - exp(-avg(weight)/5 * 1.2)); "
        "Composite = weighted_avg(PerCountry)"
    )
    assert DATA["methodology"]["scale"]["thresholds"] == {
        "STABLE": [1.0, 4.0],
        "ELEVATED": [4.0, 7.0],
        "CRITICAL": [7.0, 10.0],
    }
    map_countries = set(re.findall(r'data-country=["\']([^"\']+)', HTML))
    assert COUNTRIES <= map_countries
    assert map_countries - COUNTRIES <= {"Turkey"}
    assert all(1.0 <= float(country["index"]) <= 10.0 for country in DATA["countries"].values())
    warning = DATA["early_warning"]
    assert warning["classification"] == "precursor-anomaly-watch-not-event-probability"
    assert warning["horizon"] == "0-7 days"
    assert {row["id"] for row in warning["components"]} == {
        "narrative_pressure", "cross_market_dislocation", "synchronized_acceleration"
    }


def test_json_and_javascript_snapshots_are_byte_semantically_equivalent():
    source = (ROOT / "bnti_data.js").read_text(encoding="utf-8")
    match = re.fullmatch(r"\s*window\.BNTI_DATA\s*=\s*(\{.*\});\s*", source, re.S)
    assert match
    assert json.loads(match.group(1)) == DATA


def test_multilingual_source_and_translation_behavior_remains_supported():
    assert "detected_lang" in STREAM_JS
    assert "translated_title" in STREAM_JS
    assert "translate.google.com" in STREAM_JS
    assert "encodeURIComponent(e.link)" in STREAM_JS
    assert "rel=\"noopener\"" in STREAM_JS
    assert any(
        event.get("detected_lang") != "en"
        for country in DATA["countries"].values()
        for event in country.get("events", [])
    )


def test_map_search_and_detail_contract_is_accessible_without_mutating_scores():
    assert 'id="country-search"' in HTML
    assert 'id="country-detail"' in HTML
    assert "data?.countries" in MAP_JS
    assert "keydown" in MAP_JS
    assert "Enter" in MAP_JS and " " in MAP_JS
    assert "input" in MAP_JS
    assert "index =" not in MAP_JS
