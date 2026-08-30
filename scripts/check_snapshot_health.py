#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("meta.generated_at is missing")
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def validate_snapshot(payload, max_age_minutes, now=None):
    now = now or datetime.now(timezone.utc)
    generated = parse_timestamp(payload.get("meta", {}).get("generated_at"))
    age_minutes = (now - generated).total_seconds() / 60
    if age_minutes < -5:
        raise ValueError("snapshot timestamp is in the future")
    if age_minutes > max_age_minutes:
        raise ValueError(f"snapshot is {age_minutes:.0f} minutes old")
    countries = payload.get("countries")
    if not isinstance(countries, dict) or len(countries) != 7:
        raise ValueError("snapshot must contain seven border countries")
    return age_minutes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--max-age-minutes", type=float, required=True)
    args = parser.parse_args()
    payload = json.loads(args.snapshot.read_text(encoding="utf-8"))
    age = validate_snapshot(payload, args.max_age_minutes)
    print(f"Snapshot healthy: {age:.1f} minutes old")


if __name__ == "__main__":
    main()
