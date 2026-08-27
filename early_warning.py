"""Explainable precursor indicators for BNTI and WTI.

This module detects unusual combinations of narrative, market, and geographic
signals.  It does not assign a probability to a future event.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


PRECURSOR_BASKETS = {
    "force_posture": (
        "mobilization", "mobilisation", "reserve call-up", "troop buildup",
        "troop build-up", "military deployment", "airspace closed",
        "airspace closure", "no-fly zone", "combat readiness",
    ),
    "protective_action": (
        "embassy closure", "embassy evacuation", "leave immediately",
        "shelter in place", "civilian evacuation", "travel warning",
        "departure of non-emergency", "ordered departure",
    ),
    "coercive_pressure": (
        "ultimatum", "blockade", "emergency meeting", "article 5",
        "collective defence", "collective defense", "strategic forces",
        "border closure", "port closure",
    ),
    "systems_disruption": (
        "internet shutdown", "communications blackout", "power outage",
        "gps jamming", "navigation interference", "cyberattack",
        "cyber attack", "undersea cable", "subsea cable",
    ),
}

FRED_SERIES = {
    "wti_crude": {
        "id": "DCOILWTICO",
        "label": "WTI crude oil",
        "transform": "absolute_pct",
        "unit": "USD/barrel",
    },
    "vix": {
        "id": "VIXCLS",
        "label": "CBOE VIX",
        "transform": "positive_pct",
        "unit": "index",
    },
    "high_yield_spread": {
        "id": "BAMLH0A0HYM2",
        "label": "US high-yield spread",
        "transform": "positive_delta",
        "unit": "percentage points",
    },
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _robust_z(current: float, baseline: list[float]) -> float:
    clean = [float(value) for value in baseline if math.isfinite(float(value))]
    if len(clean) < 8:
        return 0.0
    median = statistics.median(clean)
    mad = statistics.median(abs(value - median) for value in clean)
    if mad > 1e-9:
        return (current - median) / (1.4826 * mad)
    spread = statistics.pstdev(clean)
    return (current - median) / spread if spread > 1e-9 else 0.0


def _source_domain(event: dict) -> str:
    link = str(event.get("link") or event.get("url") or "")
    host = urlparse(link).hostname or str(event.get("source") or "")
    if host.lower().removeprefix("www.") == "news.google.com":
        publisher = str(event.get("source") or "").strip()
        title = str(event.get("title") or "")
        if not publisher and " - " in title:
            publisher = title.rsplit(" - ", 1)[-1].strip()
        if publisher:
            return publisher.lower()
    return host.lower().removeprefix("www.")


def _event_text(event: dict) -> str:
    fields = (
        event.get("title"), event.get("translated_title"), event.get("llm_subject"),
        event.get("description"), event.get("summary"),
    )
    return " ".join(str(value) for value in fields if value).lower()


def _flatten_events(countries: dict) -> list[dict]:
    rows = []
    for country, block in countries.items():
        for event in block.get("events", []) or []:
            row = dict(event)
            row.setdefault("country", country)
            rows.append(row)
    return rows


def _narrative_component(events: list[dict]) -> dict:
    basket_hits = {name: [] for name in PRECURSOR_BASKETS}
    severe = 0
    domains = set()
    countries = set()
    for event in events:
        text = _event_text(event)
        domain = _source_domain(event)
        if domain:
            domains.add(domain)
        category = str(event.get("category") or "").lower()
        if category in {"military_conflict", "terrorism", "border_security"}:
            severe += 1
        for name, terms in PRECURSOR_BASKETS.items():
            matched = sorted({term for term in terms if term in text})
            if not matched:
                continue
            basket_hits[name].append({
                "country": event.get("country"),
                "title": event.get("translated_title") or event.get("title") or "Untitled signal",
                "link": event.get("link") or event.get("url"),
                "source": domain or event.get("source") or "unknown",
                "terms": matched,
            })
            if event.get("country"):
                countries.add(str(event["country"]))

    precursor_events = {
        (hit.get("link"), hit.get("title"))
        for hits in basket_hits.values() for hit in hits
    }
    total = max(len(events), 1)
    precursor_share = len(precursor_events) / total
    severe_share = severe / total
    confirmed_baskets = 0
    signals = []
    for name, hits in basket_hits.items():
        hit_domains = {hit["source"] for hit in hits if hit.get("source") != "unknown"}
        confirmed = len(hit_domains) >= 2
        if confirmed:
            confirmed_baskets += 1
        signals.append({
            "id": name,
            "label": name.replace("_", " ").title(),
            "event_count": len(hits),
            "independent_sources": len(hit_domains),
            "cross_source_confirmed": confirmed,
            "evidence": hits[:3],
        })

    score = _clamp(
        precursor_share * 180
        + severe_share * 35
        + confirmed_baskets * 12
        + min(len(countries), 4) * 3
    )
    return {
        "id": "narrative_pressure",
        "label": "Narrative precursor pressure",
        "score": round(score, 1),
        "available": bool(events),
        "events_considered": len(events),
        "precursor_event_count": len(precursor_events),
        "precursor_share": round(precursor_share, 4),
        "severe_event_share": round(severe_share, 4),
        "independent_sources": len(domains),
        "countries_with_precursors": sorted(countries),
        "signals": signals,
    }


def _cache_path(product: str, series_id: str) -> Path:
    root = Path(os.path.expanduser("~")) / ".cache" / product.lower() / "early-warning"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"fred-{series_id}.json"


def _fetch_fred_series(product: str, series_id: str, now: datetime) -> tuple[list[dict], bool]:
    cache = _cache_path(product, series_id)
    start = (now.date() - timedelta(days=240)).isoformat()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    try:
        response = requests.get(url, timeout=12, headers={"User-Agent": f"{product}-early-warning/1.0"})
        response.raise_for_status()
        rows = []
        for row in csv.DictReader(io.StringIO(response.text)):
            raw = row.get(series_id)
            if not raw or raw == ".":
                continue
            rows.append({"date": row["observation_date"], "value": float(raw)})
        if len(rows) < 10:
            raise ValueError("insufficient FRED observations")
        cache.write_text(json.dumps({"fetched_at": now.isoformat(), "rows": rows}), encoding="utf-8")
        return rows, False
    except Exception:
        if cache.exists():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                fetched_at = datetime.fromisoformat(str(payload.get("fetched_at", "")).replace("Z", "+00:00"))
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                cache_age = now - fetched_at.astimezone(timezone.utc)
                if timedelta(0) <= cache_age <= timedelta(hours=72) and len(payload.get("rows", [])) >= 10:
                    return payload["rows"], True
            except Exception:
                pass
        return [], False


def _series_indicator(key: str, spec: dict, rows: list[dict], cached: bool) -> dict:
    if len(rows) < 10:
        return {"id": key, "label": spec["label"], "available": False, "score": 0.0}
    values = [float(row["value"]) for row in rows]
    changes = []
    for index in range(5, len(values)):
        if spec["transform"].endswith("pct"):
            previous = values[index - 5]
            changes.append((values[index] / previous - 1.0) * 100 if previous else 0.0)
        else:
            changes.append(values[index] - values[index - 5])
    latest_change = changes[-1]
    z = _robust_z(latest_change, changes[:-1])
    if spec["transform"].startswith("absolute"):
        risk_z = abs(z)
    else:
        risk_z = max(0.0, z)
    score = _clamp((risk_z - 1.0) * 35.0)
    direction = "up" if latest_change > 0 else "down" if latest_change < 0 else "flat"
    return {
        "id": key,
        "label": spec["label"],
        "available": True,
        "score": round(score, 1),
        "latest_value": round(values[-1], 4),
        "five_session_change": round(latest_change, 4),
        "change_kind": "percent" if spec["transform"].endswith("pct") else "absolute",
        "direction": direction,
        "anomaly_z": round(z, 2),
        "observed_at": rows[-1]["date"],
        "unit": spec["unit"],
        "cached": cached,
        "source_url": f"https://fred.stlouisfed.org/series/{spec['id']}",
    }


def _market_component(product: str, now: datetime) -> dict:
    def load(item):
        key, spec = item
        rows, cached = _fetch_fred_series(product, spec["id"], now)
        return _series_indicator(key, spec, rows, cached)

    with ThreadPoolExecutor(max_workers=len(FRED_SERIES)) as executor:
        indicators = list(executor.map(load, FRED_SERIES.items()))
    available = [row for row in indicators if row.get("available")]
    ranked = sorted((float(row["score"]) for row in available), reverse=True)
    score = ranked[0] if len(ranked) == 1 else (ranked[0] * 0.65 + ranked[1] * 0.35 if ranked else 0.0)
    return {
        "id": "cross_market_dislocation",
        "label": "Cross-market dislocation",
        "score": round(score, 1),
        "available": bool(available),
        "series_available": len(available),
        "indicators": indicators,
    }


def _acceleration_component(countries: dict, history: list[dict] | None, prior_countries: dict | None) -> dict:
    deltas = []
    if prior_countries:
        for country, current in countries.items():
            previous = prior_countries.get(country, {})
            if "index" in current and "index" in previous:
                deltas.append((country, float(current["index"]) - float(previous["index"])))
    elif history and len(history) >= 2:
        previous, current = history[-2], history[-1]
        for key, value in current.items():
            if not key.endswith("_idx") or key not in previous:
                continue
            try:
                deltas.append((key.removesuffix("_idx").title(), float(value) - float(previous[key])))
            except (TypeError, ValueError):
                continue
    positive = [delta for _, delta in deltas if delta > 0.25]
    breadth = len(positive) / len(deltas) if deltas else 0.0
    mean_rise = statistics.mean(positive) if positive else 0.0
    score = _clamp(breadth * 65 + mean_rise * 18)
    return {
        "id": "synchronized_acceleration",
        "label": "Synchronized threat acceleration",
        "score": round(score, 1),
        "available": bool(deltas),
        "entities_compared": len(deltas),
        "rising_entities": len(positive),
        "rising_share": round(breadth, 4),
        "mean_positive_change": round(mean_rise, 3),
        "largest_changes": [
            {"entity": name, "change": round(delta, 3)}
            for name, delta in sorted(deltas, key=lambda row: row[1], reverse=True)[:5]
        ],
    }


def _level(score: float) -> str:
    if score >= 70:
        return "SEVERE"
    if score >= 50:
        return "HEIGHTENED"
    if score >= 25:
        return "WATCH"
    return "ROUTINE"


def build_early_warning(
    countries: dict,
    *,
    product: str,
    history: list[dict] | None = None,
    previous: dict | None = None,
    prior_countries: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Build an explainable precursor snapshot without claiming event probability."""

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    events = _flatten_events(countries)
    narrative = _narrative_component(events)
    market = _market_component(product, now)
    acceleration = _acceleration_component(countries, history, prior_countries)
    components = [narrative, market, acceleration]
    weights = {
        "narrative_pressure": 0.40,
        "cross_market_dislocation": 0.35,
        "synchronized_acceleration": 0.25,
    }
    available = [item for item in components if item.get("available")]
    denominator = sum(weights[item["id"]] for item in available)
    score = (
        sum(float(item["score"]) * weights[item["id"]] for item in available) / denominator
        if denominator else 0.0
    )
    market_coverage = market.get("series_available", 0) / len(FRED_SERIES)
    event_coverage = min(1.0, len(events) / 30)
    source_coverage = min(1.0, narrative.get("independent_sources", 0) / 10)
    confidence_score = 100 * (0.45 * market_coverage + 0.35 * event_coverage + 0.20 * source_coverage)
    confidence = "HIGH" if confidence_score >= 75 else "MEDIUM" if confidence_score >= 45 else "LOW"

    alerts = []
    for component in components:
        if component.get("available") and component.get("score", 0) >= 35:
            alerts.append({
                "id": component["id"],
                "level": _level(float(component["score"])),
                "title": component["label"],
                "score": component["score"],
                "why": {
                    "narrative_pressure": "Threat-language concentration and cross-source confirmation exceed routine conditions.",
                    "cross_market_dislocation": "One or more market moves are unusual relative to their recent robust baseline.",
                    "synchronized_acceleration": "Threat readings are rising together across multiple monitored entities.",
                }[component["id"]],
            })
    alerts.sort(key=lambda item: item["score"], reverse=True)

    history_rows = list((previous or {}).get("history", []))[-179:]
    history_rows.append({
        "timestamp": now.isoformat(),
        "score": round(score, 1),
        "level": _level(score),
        "components": {item["id"]: item["score"] for item in components},
    })
    return {
        "issued_at": now.isoformat(),
        "horizon": "0-7 days",
        "classification": "precursor-anomaly-watch-not-event-probability",
        "score": round(score, 1),
        "level": _level(score),
        "confidence": confidence,
        "confidence_score": round(confidence_score, 1),
        "components": components,
        "alerts": alerts,
        "history": history_rows,
        "data_health": {
            "events_considered": len(events),
            "independent_sources": narrative.get("independent_sources", 0),
            "market_series_available": market.get("series_available", 0),
            "available_components": len(available),
        },
        "method": {
            "name": "Robust multi-domain precursor ensemble",
            "aggregation": "availability-renormalized weighted mean",
            "weights": weights,
            "market_anomaly": "five-session change vs median/MAD baseline; 1.4826*MAD scale",
            "narrative_taxonomy": PRECURSOR_BASKETS,
            "warning": "An elevated reading is a triage signal, not proof that a specific event will occur.",
        },
        "sources": [
            {"name": "FRED", "url": "https://fred.stlouisfed.org/"},
            {"name": "Caldara-Iacoviello GPR methodology", "url": "https://www.matteoiacoviello.com/gpr.htm"},
            {"name": "ViEWS transparent early-warning design", "url": "https://viewsforecasting.org/"},
        ],
    }
