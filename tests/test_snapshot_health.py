import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("snapshot_health", ROOT / "scripts" / "check_snapshot_health.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def snapshot(timestamp):
    return {"meta": {"generated_at": timestamp}, "countries": {str(i): {} for i in range(7)}}


def test_health_gate_accepts_recent_complete_snapshot():
    now = datetime(2026, 8, 30, 6, 36, tzinfo=timezone.utc)
    assert MODULE.validate_snapshot(snapshot("2026-08-30T06:20:00Z"), 20, now) == 16


def test_health_gate_rejects_stale_future_and_incomplete_snapshots():
    now = datetime(2026, 8, 30, 6, 36, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="old"):
        MODULE.validate_snapshot(snapshot("2026-08-30T03:00:00Z"), 20, now)
    with pytest.raises(ValueError, match="future"):
        MODULE.validate_snapshot(snapshot("2026-08-30T07:00:00Z"), 20, now)
    with pytest.raises(ValueError, match="seven"):
        MODULE.validate_snapshot({"meta": {"generated_at": "2026-08-30T06:20:00Z"}, "countries": {}}, 20, now)
