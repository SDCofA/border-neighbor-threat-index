import json
import os
import tempfile
import unittest

import borderneighboursthreatindex as analyzer_module


class CandidateSnapshotGateTests(unittest.TestCase):
    def make_analyzer(self, tempdir):
        analyzer = object.__new__(analyzer_module.BNTIAnalyzer)
        analyzer.output_path = tempdir
        analyzer.history_file = os.path.join(tempdir, "bnti_history.csv")
        analyzer.openrouter_model = "openrouter/free"
        analyzer.category_weights = dict(analyzer_module.BNTIAnalyzer.LLM_CATEGORY_WEIGHTS)
        analyzer.translate_top_threats = lambda dashboard_data: dashboard_data
        analyzer.load_history = lambda: []
        analyzer._trim_history = lambda history: history
        analyzer._build_history_payload = lambda history, include_live=False, live_index=None: []
        analyzer.generate_forecast = lambda history: []
        analyzer._build_dashboard_data = analyzer_module.BNTIAnalyzer._build_dashboard_data.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._write_dashboard_files = analyzer_module.BNTIAnalyzer._write_dashboard_files.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._promote_candidate_snapshot = analyzer_module.BNTIAnalyzer._promote_candidate_snapshot.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        return analyzer

    def test_failed_candidate_does_not_replace_live_snapshot(self):
        with tempfile.TemporaryDirectory() as tempdir:
            analyzer = self.make_analyzer(tempdir)
            json_path = os.path.join(tempdir, "bnti_data.json")
            js_path = os.path.join(tempdir, "bnti_data.js")
            original = {"meta": {"main_index": 4.34}, "countries": {"Syria": {"events": []}}}
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(original, handle)
            with open(js_path, "w", encoding="utf-8") as handle:
                handle.write("window.BNTI_DATA = " + json.dumps(original))

            promoted = analyzer._promote_candidate_snapshot(
                {"publishable": False},
                json_path=json_path,
                js_path=js_path,
            )

            self.assertFalse(promoted)
            with open(json_path, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), original)

    def test_successful_candidate_replaces_live_snapshot(self):
        with tempfile.TemporaryDirectory() as tempdir:
            analyzer = self.make_analyzer(tempdir)
            json_path = os.path.join(tempdir, "bnti_data.json")
            js_path = os.path.join(tempdir, "bnti_data.js")
            candidate = {
                "publishable": True,
                "country_results": {"Iraq": {"index": 6.5, "raw_score": 5.0, "events": []}},
                "turkey_index": 6.5,
                "status": "ELEVATED",
                "history_records": [],
                "regional_summary_6h": {
                    "slot_start": "2026-03-28T00:00:00",
                    "slot_end": "2026-03-28T06:00:00",
                    "generated_at": "2026-03-28T06:00:00",
                    "next_refresh_at": "2026-03-28T12:00:00",
                    "headline": "Regional pressure remains centered on Iraq.",
                    "bullets": ["One.", "Two.", "Three."],
                    "watch": None,
                },
            }

            promoted = analyzer._promote_candidate_snapshot(
                candidate,
                json_path=json_path,
                js_path=js_path,
            )

            self.assertTrue(promoted)
            with open(json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data["meta"]["main_index"], 6.5)
            self.assertIn("Iraq", data["countries"])
            self.assertEqual(
                data["briefing"]["regional_summary_6h"]["headline"],
                "Regional pressure remains centered on Iraq.",
            )

    def test_workflow_uses_hourly_headroom_backup_key_and_health_gates(self):
        workflow_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            ".github",
            "workflows",
            "bnti_update.yml",
        )
        with open(workflow_path, "r", encoding="utf-8") as handle:
            workflow = handle.read()

        self.assertIn("17 * * * *", workflow)
        self.assertIn("OPENROUTER_API_KEY_BACKUP", workflow)
        self.assertIn("check_snapshot_health.py bnti_data.json --max-age-minutes 20", workflow)
        self.assertIn("check_snapshot_health.py /tmp/bnti-live.json --max-age-minutes 480", workflow)
        self.assertIn("paths-ignore:", workflow)
        self.assertIn("deploy_only:", workflow)
        self.assertIn("inputs.deploy_only", workflow)
        self.assertIn("needs.update-intelligence.result == 'skipped'", workflow)
        self.assertNotIn("huggingface-xlm-roberta-large-xnli-v2", workflow)

    def test_requirements_drop_transformer_stack(self):
        requirements_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "requirements.txt",
        )
        with open(requirements_path, "r", encoding="utf-8") as handle:
            requirements = handle.read()

        self.assertNotIn("transformers>=", requirements)
        self.assertNotIn("torch>=", requirements)


if __name__ == "__main__":
    unittest.main()
