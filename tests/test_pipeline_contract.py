import json
from pathlib import Path

from borderneighboursthreatindex import BNTIAnalyzer


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "bnti_update.yml"
WORKFLOW_SHA256 = "95227d3c8c4decdf085abbe141a0eb7adc9716ba85a187ccab50500b9f62b981"


def test_update_workflow_fails_loudly_and_publishes_expected_outputs():
    text = WORKFLOW.read_text(encoding="utf-8")
    for output in ("bnti_data.js", "bnti_data.json", "bnti_history.csv"):
        assert output in text
    assert "python -m pytest -q" in text
    assert "continue-on-error: true" not in text
    assert "|| echo" not in text
    assert "exit 0" not in text
    assert "actions/upload-pages-artifact@v3" in text
    assert "path: '.'" in text


def test_scoring_and_six_point_projection_fixture_is_preserved():
    engine = BNTIAnalyzer.__new__(BNTIAnalyzer)
    assert [engine.calculate_final_index(value) for value in (0, 2.5, 5.0, 8.0)] == [
        1.0,
        5.06,
        7.29,
        8.68,
    ]
    history = [
        {"timestamp": f"2026-07-18T0{hour}:00:00", "main_index": 2.0 + hour}
        for hour in range(6)
    ]
    projection = engine.generate_forecast(history)
    assert len(projection) == 6
    assert [point["type"] for point in projection] == ["forecast"] * 6
    assert [point["main_index"] for point in projection] == [8.0, 9.0, 10.0, 10.0, 10.0, 10.0]


def test_pipeline_writes_semantically_equal_json_and_javascript(tmp_path):
    engine = BNTIAnalyzer.__new__(BNTIAnalyzer)
    payload = {"meta": {"main_index": 4.25}, "countries": {"Syria": {"index": 4.25}}}
    json_path = tmp_path / "bnti_data.json"
    js_path = tmp_path / "bnti_data.js"
    engine._write_dashboard_files(payload, str(json_path), str(js_path))
    json_payload = json.loads(json_path.read_text(encoding="utf-8"))
    js_text = js_path.read_text(encoding="utf-8")
    js_payload = json.loads(js_text.removeprefix("window.BNTI_DATA = ").removesuffix(";"))
    assert json_payload == js_payload == payload


def test_pre_edit_runtime_contract_is_recorded_for_reproducibility():
    contract = ROOT / "docs" / "baseline" / "task-8-runtime-contract.json"
    assert contract.is_file()
    recorded = json.loads(contract.read_text(encoding="utf-8"))
    assert recorded["base_sha"] == "9fef5cb11e9f5a9e37c20392cdf0d35ca3a039a0"
    assert recorded["workflow_sha256"] == WORKFLOW_SHA256
    assert recorded["countries"] == [
        "Armenia",
        "Georgia",
        "Greece",
        "Iran",
        "Iraq",
        "Syria",
        "Bulgaria",
    ]
