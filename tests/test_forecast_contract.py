import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
CORE = (ROOT / "js" / "core.js").read_text(encoding="utf-8")
CHARTS = (ROOT / "js" / "charts.js").read_text(encoding="utf-8")
PIPELINE = (ROOT / "borderneighboursthreatindex.py").read_text(encoding="utf-8")


def test_ungoverned_linear_output_is_visibly_relabelled_as_scenario():
    assert "Trend + Forecast" not in HTML
    assert re.search(r"48H Trend \+ 6H Scenario", HTML)
    assert 'id="scenario-disclosure"' in HTML
    assert "Scenario projection — not a forecast" in HTML
    assert "assessment or scenario" in HTML.lower()


def test_scenario_disclosure_exposes_issue_horizon_method_uncertainty_and_provenance():
    for identifier in (
        "scenario-issued",
        "scenario-horizon",
        "scenario-method",
        "scenario-uncertainty",
        "scenario-assumptions",
        "scenario-provenance",
        "scenario-revisions",
    ):
        assert f'id="{identifier}"' in HTML
    assert "6 hours" in HTML
    assert "linear" in HTML.lower()
    assert "bnti_data.json" in HTML
    assert "No revision or outcome ledger" in HTML
    assert "generated_at" in CORE


def test_calculation_and_dataset_field_remain_unchanged_while_chart_copy_is_honest():
    assert 'def generate_forecast(self, history):' in PIPELINE
    assert '"type": "forecast"' in PIPELINE
    assert "np.polyfit(x, y, 1)" in PIPELINE
    assert "forecastPoints" in CHARTS
    assert "scenario" in CHARTS.lower()
    assert "forecast-like" not in HTML.lower()

