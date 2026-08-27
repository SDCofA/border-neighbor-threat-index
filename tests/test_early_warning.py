import json
from datetime import datetime, timedelta, timezone

import early_warning


def _countries():
    return {
        "Iran": {
            "index": 7.1,
            "events": [
                {
                    "title": "Embassy evacuation follows airspace closure",
                    "category": "military_conflict",
                    "link": "https://one.example/a",
                },
                {
                    "title": "Ordered departure amid military deployment",
                    "category": "diplomatic_tensions",
                    "link": "https://two.example/b",
                },
            ],
        },
        "Iraq": {
            "index": 5.0,
            "events": [
                {
                    "title": "Communications blackout and border closure",
                    "category": "border_security",
                    "link": "https://three.example/c",
                }
            ],
        },
    }


def test_narrative_precursors_require_traceable_event_evidence():
    component = early_warning._narrative_component(early_warning._flatten_events(_countries()))
    assert component["precursor_event_count"] == 3
    assert component["independent_sources"] == 3
    assert component["score"] > 35
    assert any(signal["evidence"] for signal in component["signals"])


def test_robust_z_resists_single_large_outlier():
    baseline = [0.8, 1.0, 1.1, 0.9, 1.2, 1.0, 0.95, 1.05, 25.0]
    assert early_warning._robust_z(3.0, baseline) > 5


def test_ensemble_renormalizes_when_market_feed_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        early_warning,
        "_market_component",
        lambda product, now: {
            "id": "cross_market_dislocation",
            "label": "Cross-market dislocation",
            "score": 0.0,
            "available": False,
            "series_available": 0,
            "indicators": [],
        },
    )
    result = early_warning.build_early_warning(
        _countries(),
        product="test",
        history=[
            {"iran_idx": 5.0, "iraq_idx": 4.0},
            {"iran_idx": 7.1, "iraq_idx": 5.0},
        ],
        now=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    assert result["classification"] == "precursor-anomaly-watch-not-event-probability"
    assert result["data_health"]["available_components"] == 2
    assert result["score"] > 0
    assert result["history"][-1]["score"] == result["score"]


def test_failed_market_fetch_rejects_cache_older_than_72_hours(monkeypatch, tmp_path):
    now = datetime(2026, 8, 27, tzinfo=timezone.utc)
    cache = tmp_path / "fred.json"
    cache.write_text(json.dumps({
        "fetched_at": (now - timedelta(hours=73)).isoformat(),
        "rows": [{"date": f"2026-08-{day:02d}", "value": day} for day in range(1, 11)],
    }), encoding="utf-8")
    monkeypatch.setattr(early_warning, "_cache_path", lambda product, series_id: cache)
    monkeypatch.setattr(early_warning.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    assert early_warning._fetch_fred_series("test", "SERIES", now) == ([], False)
