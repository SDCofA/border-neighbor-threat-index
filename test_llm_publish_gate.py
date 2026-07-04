import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

import requests

import borderneighboursthreatindex as analyzer_module


class FeedEntry(dict):
    __getattr__ = dict.get


class LLMPublishGateTests(unittest.TestCase):
    def make_analyzer(self):
        analyzer = object.__new__(analyzer_module.BNTIAnalyzer)
        analyzer.output_path = tempfile.mkdtemp()
        analyzer.history_file = analyzer.output_path + "\\bnti_history.csv"
        analyzer.openrouter_api_key = "primary-key"
        analyzer.openrouter_backup_api_key = "backup-key"
        analyzer.openrouter_model = "openrouter/free"
        analyzer.openrouter_batch_size = 2
        analyzer.border_countries = list(analyzer_module.BNTIAnalyzer.BORDER_COUNTRIES)
        analyzer.category_weights = dict(analyzer_module.BNTIAnalyzer.LLM_CATEGORY_WEIGHTS)
        analyzer.calculate_final_index = analyzer_module.BNTIAnalyzer.calculate_final_index.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_results = analyzer_module.BNTIAnalyzer._build_country_results.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._ensure_translated_titles = lambda events: events
        return analyzer

    def test_category_scores_use_llm_enum(self):
        self.assertEqual(analyzer_module.BNTIAnalyzer.LLM_CATEGORY_WEIGHTS["military_conflict"], 8.0)
        self.assertEqual(analyzer_module.BNTIAnalyzer.LLM_CATEGORY_WEIGHTS["terrorism"], 7.0)
        self.assertEqual(analyzer_module.BNTIAnalyzer.LLM_CATEGORY_WEIGHTS["trade_agreement"], -2.0)

    def test_process_country_returns_unscored_candidates(self):
        analyzer = self.make_analyzer()
        analyzer.fetch_feed_entries = lambda country, url: [
            FeedEntry(title="Baghdad airport security alert", link="https://example.com/a", published="2026-03-27T18:00:00"),
            FeedEntry(title="Baghdad airport security alert", link="https://example.com/a", published="2026-03-27T18:00:00"),
        ]

        country, candidates = analyzer.process_country("Iraq", ["https://feed.example/rss"])

        self.assertEqual(country, "Iraq")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source_country"], "Iraq")
        self.assertNotIn("category", candidates[0])
        self.assertNotIn("weight", candidates[0])

    def test_build_candidate_snapshot_rejects_partial_batch_success(self):
        analyzer = self.make_analyzer()
        responses = iter([
            '[{"id": 1, "primary_country": "Syria", "category": "military_conflict", "subject": "Syrian military pressure"},'
            '{"id": 2, "primary_country": "IRRELEVANT", "category": "neutral", "subject": "Sports coverage"}]',
            '[{"id": 1, "final_country": "Syria"}, {"id": 2, "final_country": "IRRELEVANT"}]',
            None,
            None,
        ])
        analyzer._call_openrouter = lambda prompt, max_retries=2: next(responses)
        analyzer._build_attribution_prompt = analyzer_module.BNTIAnalyzer._build_attribution_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_attribution_response = analyzer_module.BNTIAnalyzer._parse_attribution_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_audit_prompt = analyzer_module.BNTIAnalyzer._build_country_audit_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_country_audit_response = analyzer_module.BNTIAnalyzer._parse_country_audit_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)

        candidate = analyzer.build_candidate_snapshot({
            "Syria": [
                {"title": "Syria headline", "translated_title": "Syria headline", "link": "https://example.com/1", "date": "2026-03-27T18:00:00", "source_country": "Syria"},
                {"title": "Another Syria headline", "translated_title": "Another Syria headline", "link": "https://example.com/2", "date": "2026-03-27T18:10:00", "source_country": "Syria"},
                {"title": "Third Syria headline", "translated_title": "Third Syria headline", "link": "https://example.com/3", "date": "2026-03-27T18:20:00", "source_country": "Syria"},
            ]
        })

        self.assertFalse(candidate["publishable"])

    def test_build_candidate_snapshot_falls_back_when_openrouter_rate_limited(self):
        analyzer = self.make_analyzer()
        analyzer.MIN_PUBLISHABLE_TOTAL_SIGNALS = 1
        analyzer.MIN_PUBLISHABLE_ACTIVE_COUNTRIES = 1
        analyzer.MIN_SIGNAL_COVERAGE_RATIO = 0.0
        analyzer.MIN_ACTIVE_COUNTRY_COVERAGE_RATIO = 0.0
        analyzer._utc_now = lambda: datetime(2026, 3, 28, 8, 0, 0)
        analyzer.load_history = lambda: []
        analyzer._load_existing_summary = lambda: {
            "slot_start": "2026-03-28T00:00:00",
            "slot_end": "2026-03-28T06:00:00",
            "generated_at": "2026-03-28T06:00:00",
            "next_refresh_at": "2026-03-28T12:00:00",
            "headline": "Existing brief.",
            "bullets": ["One.", "Two.", "Three."],
            "watch": None,
        }
        analyzer._call_openrouter = lambda prompt, max_retries=2: None
        analyzer._build_attribution_prompt = analyzer_module.BNTIAnalyzer._build_attribution_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_attribution_response = analyzer_module.BNTIAnalyzer._parse_attribution_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_audit_prompt = analyzer_module.BNTIAnalyzer._build_country_audit_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_country_audit_response = analyzer_module.BNTIAnalyzer._parse_country_audit_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)

        candidate = analyzer.build_candidate_snapshot({
            "Iraq": [
                {
                    "title": "Baghdad airport security alert",
                    "translated_title": "Baghdad airport security alert",
                    "link": "https://example.com/a",
                    "date": "2026-03-28T07:15:00",
                    "source_country": "Iraq",
                }
            ]
        })

        self.assertTrue(candidate["publishable"])
        event = candidate["country_results"]["Iraq"]["events"][0]
        self.assertEqual(event["category"], "border_security")
        self.assertEqual(event["llm_primary_country"], "Iraq")
        self.assertEqual(event["llm_final_country"], "Iraq")
        self.assertEqual(event["confidence"], 0.35)
        self.assertFalse(event["ai_category"])
        self.assertEqual(event["ai_model"], "deterministic-fallback")
        self.assertEqual(event["fallback_reason"], "llm_attribution_failed")

    def test_build_candidate_snapshot_skips_llm_after_rate_limit_circuit_breaker(self):
        analyzer = self.make_analyzer()
        analyzer.MIN_PUBLISHABLE_TOTAL_SIGNALS = 1
        analyzer.MIN_PUBLISHABLE_ACTIVE_COUNTRIES = 1
        analyzer.MIN_SIGNAL_COVERAGE_RATIO = 0.0
        analyzer.MIN_ACTIVE_COUNTRY_COVERAGE_RATIO = 0.0
        analyzer._utc_now = lambda: datetime(2026, 3, 28, 8, 0, 0)
        analyzer.load_history = lambda: []
        analyzer._load_existing_summary = lambda: {
            "slot_start": "2026-03-28T00:00:00",
            "slot_end": "2026-03-28T06:00:00",
            "generated_at": "2026-03-28T06:00:00",
            "next_refresh_at": "2026-03-28T12:00:00",
            "headline": "Existing brief.",
            "bullets": ["One.", "Two.", "Three."],
            "watch": None,
        }
        analyzer.openrouter_batch_size = 1
        analyzer.openrouter_disabled_for_run = False
        call_count = {"value": 0}

        def fake_call(prompt, max_retries=2):
            call_count["value"] += 1
            analyzer.openrouter_disabled_for_run = True
            return None

        analyzer._call_openrouter = fake_call
        analyzer._build_attribution_prompt = analyzer_module.BNTIAnalyzer._build_attribution_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_attribution_response = analyzer_module.BNTIAnalyzer._parse_attribution_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_audit_prompt = analyzer_module.BNTIAnalyzer._build_country_audit_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_country_audit_response = analyzer_module.BNTIAnalyzer._parse_country_audit_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)

        candidate = analyzer.build_candidate_snapshot({
            "Iraq": [
                {"title": "Iraq alert one", "translated_title": "Iraq alert one", "link": "https://example.com/1", "date": "2026-03-28T07:15:00", "source_country": "Iraq"},
                {"title": "Iraq alert two", "translated_title": "Iraq alert two", "link": "https://example.com/2", "date": "2026-03-28T07:20:00", "source_country": "Iraq"},
            ]
        })

        self.assertTrue(candidate["publishable"])
        self.assertEqual(call_count["value"], 1)

    def test_build_country_results_scores_from_llm_category_only(self):
        analyzer = self.make_analyzer()
        all_events = [
            {"title": "Baghdad airport security alert", "translated_title": "Baghdad airport security alert", "link": "https://example.com/a", "date": "2026-03-27T18:00:00", "source_country": "Iraq"},
        ]
        attribution_map = {
            0: {
                "primary_country": "Iraq",
                "final_country": "Iraq",
                "category": "military_conflict",
                "subject": "Baghdad airport security",
            },
        }

        country_results = analyzer._build_country_results(all_events, attribution_map)

        self.assertEqual(country_results["Iraq"]["raw_score"], 8.0)
        self.assertEqual(country_results["Iraq"]["events"][0]["weight"], 8.0)
        self.assertEqual(country_results["Iraq"]["events"][0]["confidence"], 1.0)

    def test_build_candidate_snapshot_rejects_empty_feed_coverage(self):
        analyzer = self.make_analyzer()
        analyzer.load_history = lambda: [
            {
                "timestamp": "2026-03-27T18:00:00",
                "total_signals": 105,
                "armenia_signals": 15,
                "georgia_signals": 15,
                "greece_signals": 15,
                "iran_signals": 15,
                "iraq_signals": 15,
                "syria_signals": 15,
                "bulgaria_signals": 15,
            }
        ]
        analyzer._trim_history = lambda history: history

        candidate = analyzer.build_candidate_snapshot({
            country: [] for country in analyzer.border_countries
        })

        self.assertFalse(candidate["publishable"])
        self.assertEqual(candidate["reason"], "no_candidate_events")

    def test_build_candidate_snapshot_rejects_low_signal_coverage(self):
        analyzer = self.make_analyzer()
        analyzer.openrouter_batch_size = 10
        analyzer.load_history = lambda: [
            {
                "timestamp": "2026-03-27T18:00:00",
                "total_signals": 105,
                "armenia_signals": 15,
                "georgia_signals": 15,
                "greece_signals": 15,
                "iran_signals": 15,
                "iraq_signals": 15,
                "syria_signals": 15,
                "bulgaria_signals": 15,
            }
        ]
        analyzer._trim_history = lambda history: history
        responses = iter([
            '[{"id": 1, "primary_country": "Bulgaria", "category": "neutral", "subject": "Bulgarian domestic news"},'
            '{"id": 2, "primary_country": "Bulgaria", "category": "neutral", "subject": "Bulgarian domestic news"},'
            '{"id": 3, "primary_country": "Bulgaria", "category": "neutral", "subject": "Bulgarian domestic news"},'
            '{"id": 4, "primary_country": "Bulgaria", "category": "neutral", "subject": "Bulgarian domestic news"},'
            '{"id": 5, "primary_country": "Bulgaria", "category": "neutral", "subject": "Bulgarian domestic news"},'
            '{"id": 6, "primary_country": "Bulgaria", "category": "neutral", "subject": "Bulgarian domestic news"},'
            '{"id": 7, "primary_country": "Bulgaria", "category": "neutral", "subject": "Bulgarian domestic news"}]',
            '[{"id": 1, "final_country": "Bulgaria"},'
            '{"id": 2, "final_country": "Bulgaria"},'
            '{"id": 3, "final_country": "Bulgaria"},'
            '{"id": 4, "final_country": "Bulgaria"},'
            '{"id": 5, "final_country": "Bulgaria"},'
            '{"id": 6, "final_country": "Bulgaria"},'
            '{"id": 7, "final_country": "Bulgaria"}]',
        ])
        analyzer._call_openrouter = lambda prompt, max_retries=2: next(responses)
        analyzer._build_attribution_prompt = analyzer_module.BNTIAnalyzer._build_attribution_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_attribution_response = analyzer_module.BNTIAnalyzer._parse_attribution_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_audit_prompt = analyzer_module.BNTIAnalyzer._build_country_audit_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_country_audit_response = analyzer_module.BNTIAnalyzer._parse_country_audit_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)

        candidate = analyzer.build_candidate_snapshot({
            "Bulgaria": [
                {"title": f"Bulgaria headline {idx}", "translated_title": f"Bulgaria headline {idx}", "link": f"https://example.com/{idx}", "date": "2026-03-27T18:00:00", "source_country": "Bulgaria"}
                for idx in range(1, 8)
            ]
        })

        self.assertFalse(candidate["publishable"])
        self.assertEqual(candidate["reason"], "insufficient_feed_coverage")

    def test_build_candidate_snapshot_requires_summary_when_current_slot_missing(self):
        analyzer = self.make_analyzer()
        analyzer.MIN_PUBLISHABLE_TOTAL_SIGNALS = 1
        analyzer.MIN_PUBLISHABLE_ACTIVE_COUNTRIES = 1
        analyzer.MIN_SIGNAL_COVERAGE_RATIO = 0.0
        analyzer.MIN_ACTIVE_COUNTRY_COVERAGE_RATIO = 0.0
        analyzer._utc_now = lambda: datetime(2026, 3, 28, 6, 0, 0)
        analyzer._load_existing_summary = lambda: None
        analyzer._build_attribution_prompt = analyzer_module.BNTIAnalyzer._build_attribution_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_attribution_response = analyzer_module.BNTIAnalyzer._parse_attribution_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_audit_prompt = analyzer_module.BNTIAnalyzer._build_country_audit_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_country_audit_response = analyzer_module.BNTIAnalyzer._parse_country_audit_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer.load_history = lambda: []

        responses = iter([
            '[{"id": 1, "primary_country": "Iraq", "category": "military_conflict", "subject": "Baghdad airport security"}]',
            '[{"id": 1, "final_country": "Iraq"}]',
            None,
        ])
        analyzer._call_openrouter = lambda prompt, max_retries=2: next(responses)

        candidate = analyzer.build_candidate_snapshot({
            "Iraq": [
                {
                    "title": "Baghdad airport security alert",
                    "translated_title": "Baghdad airport security alert",
                    "link": "https://example.com/a",
                    "date": "2026-03-28T05:15:00",
                    "source_country": "Iraq",
                }
            ]
        })

        self.assertFalse(candidate["publishable"])
        self.assertEqual(candidate["reason"], "summary_generation_failed")

    def test_build_candidate_snapshot_reuses_existing_summary_between_refreshes(self):
        analyzer = self.make_analyzer()
        analyzer.MIN_PUBLISHABLE_TOTAL_SIGNALS = 1
        analyzer.MIN_PUBLISHABLE_ACTIVE_COUNTRIES = 1
        analyzer.MIN_SIGNAL_COVERAGE_RATIO = 0.0
        analyzer.MIN_ACTIVE_COUNTRY_COVERAGE_RATIO = 0.0
        analyzer._utc_now = lambda: datetime(2026, 3, 28, 8, 0, 0)
        analyzer.load_history = lambda: []
        analyzer._build_attribution_prompt = analyzer_module.BNTIAnalyzer._build_attribution_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_attribution_response = analyzer_module.BNTIAnalyzer._parse_attribution_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_audit_prompt = analyzer_module.BNTIAnalyzer._build_country_audit_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_country_audit_response = analyzer_module.BNTIAnalyzer._parse_country_audit_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        existing_summary = {
            "slot_start": "2026-03-28T00:00:00",
            "slot_end": "2026-03-28T06:00:00",
            "generated_at": "2026-03-28T06:00:00",
            "next_refresh_at": "2026-03-28T12:00:00",
            "headline": "Existing brief.",
            "bullets": ["One.", "Two.", "Three."],
            "watch": None,
        }
        analyzer._load_existing_summary = lambda: existing_summary
        call_count = {"value": 0}

        def fake_call(prompt, max_retries=2):
            call_count["value"] += 1
            if call_count["value"] == 1:
                return '[{"id": 1, "primary_country": "Iraq", "category": "military_conflict", "subject": "Baghdad airport security"}]'
            return '[{"id": 1, "final_country": "Iraq"}]'

        analyzer._call_openrouter = fake_call

        candidate = analyzer.build_candidate_snapshot({
            "Iraq": [
                {
                    "title": "Baghdad airport security alert",
                    "translated_title": "Baghdad airport security alert",
                    "link": "https://example.com/a",
                    "date": "2026-03-28T07:15:00",
                    "source_country": "Iraq",
                }
            ]
        })

        self.assertTrue(candidate["publishable"])
        self.assertEqual(candidate["regional_summary_6h"]["headline"], "Existing brief.")
        self.assertEqual(call_count["value"], 2)

    def test_build_candidate_snapshot_uses_country_audit_to_correct_cross_country_leak(self):
        analyzer = self.make_analyzer()
        analyzer.MIN_PUBLISHABLE_TOTAL_SIGNALS = 1
        analyzer.MIN_PUBLISHABLE_ACTIVE_COUNTRIES = 1
        analyzer.MIN_SIGNAL_COVERAGE_RATIO = 0.0
        analyzer.MIN_ACTIVE_COUNTRY_COVERAGE_RATIO = 0.0
        analyzer.load_history = lambda: []
        analyzer._load_existing_summary = lambda: {
            "slot_start": "2026-03-28T00:00:00",
            "slot_end": "2026-03-28T06:00:00",
            "generated_at": "2026-03-28T06:00:00",
            "next_refresh_at": "2026-03-28T12:00:00",
            "headline": "Existing brief.",
            "bullets": ["One.", "Two.", "Three."],
            "watch": None,
        }
        analyzer._build_attribution_prompt = analyzer_module.BNTIAnalyzer._build_attribution_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_attribution_response = analyzer_module.BNTIAnalyzer._parse_attribution_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_audit_prompt = analyzer_module.BNTIAnalyzer._build_country_audit_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_country_audit_response = analyzer_module.BNTIAnalyzer._parse_country_audit_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)

        responses = iter([
            '[{"id": 1, "primary_country": "Greece", "category": "military_conflict", "subject": "Iranian nuclear facilities"}]',
            '[{"id": 1, "final_country": "Iran"}]',
        ])
        analyzer._call_openrouter = lambda prompt, max_retries=2: next(responses)

        candidate = analyzer.build_candidate_snapshot({
            "Greece": [
                {
                    "title": "ΗΠΑ και Ισραήλ βομβάρδισαν πυρηνικό αντιδραστήρα βαρέος ύδατος και εργοστάσιο επεξεργασίας ουρανίου στο Ιράν",
                    "translated_title": "US, Israel bomb heavy water nuclear reactor and uranium processing plant in Iran",
                    "link": "https://example.com/greece-feed",
                    "date": "2026-03-28T05:15:00",
                    "source_country": "Greece",
                }
            ]
        })

        self.assertTrue(candidate["publishable"])
        self.assertEqual(len(candidate["country_results"]["Iran"]["events"]), 1)
        self.assertEqual(len(candidate["country_results"]["Greece"]["events"]), 0)
        self.assertEqual(
            candidate["country_results"]["Iran"]["events"][0]["llm_primary_country"],
            "Greece",
        )
        self.assertEqual(
            candidate["country_results"]["Iran"]["events"][0]["llm_final_country"],
            "Iran",
        )

    def test_build_candidate_snapshot_splits_invalid_country_audit_batches_until_valid(self):
        analyzer = self.make_analyzer()
        analyzer.openrouter_batch_size = 2
        analyzer.MIN_PUBLISHABLE_TOTAL_SIGNALS = 1
        analyzer.MIN_PUBLISHABLE_ACTIVE_COUNTRIES = 1
        analyzer.MIN_SIGNAL_COVERAGE_RATIO = 0.0
        analyzer.MIN_ACTIVE_COUNTRY_COVERAGE_RATIO = 0.0
        analyzer.load_history = lambda: []
        analyzer._load_existing_summary = lambda: {
            "slot_start": "2026-03-28T00:00:00",
            "slot_end": "2026-03-28T06:00:00",
            "generated_at": "2026-03-28T06:00:00",
            "next_refresh_at": "2026-03-28T12:00:00",
            "headline": "Existing brief.",
            "bullets": ["One.", "Two.", "Three."],
            "watch": None,
        }
        analyzer._build_attribution_prompt = analyzer_module.BNTIAnalyzer._build_attribution_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_attribution_response = analyzer_module.BNTIAnalyzer._parse_attribution_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_audit_prompt = analyzer_module.BNTIAnalyzer._build_country_audit_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_country_audit_response = analyzer_module.BNTIAnalyzer._parse_country_audit_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)

        responses = iter([
            '[{"id": 1, "primary_country": "Iran", "category": "military_conflict", "subject": "Iranian nuclear facilities"},'
            '{"id": 2, "primary_country": "Syria", "category": "neutral", "subject": "Syrian reconstruction"}]',
            '[{"id": 1, "final_country": "Iran"}]',
            '[{"id": 1, "final_country": "Iran"}]',
            '[{"id": 2, "final_country": "Syria"}]',
        ])
        analyzer._call_openrouter = lambda prompt, max_retries=2: next(responses)

        candidate = analyzer.build_candidate_snapshot({
            "Greece": [
                {
                    "title": "US, Israel bomb heavy water nuclear reactor and uranium processing plant in Iran - Kathimerini",
                    "translated_title": "US, Israel bomb heavy water nuclear reactor and uranium processing plant in Iran - Kathimerini",
                    "link": "https://example.com/iran",
                    "date": "2026-03-28T05:15:00",
                    "source_country": "Greece",
                }
            ],
            "Syria": [
                {
                    "title": "Syria silently rebuilds itself as war with Iran tarnishes Gulf infrastructure - Turkiye Today",
                    "translated_title": "Syria silently rebuilds itself as war with Iran tarnishes Gulf infrastructure - Turkiye Today",
                    "link": "https://example.com/syria",
                    "date": "2026-03-28T05:30:00",
                    "source_country": "Syria",
                }
            ],
        })

        self.assertTrue(candidate["publishable"])
        self.assertEqual(len(candidate["country_results"]["Iran"]["events"]), 1)
        self.assertEqual(len(candidate["country_results"]["Syria"]["events"]), 1)
        self.assertEqual(candidate["country_results"]["Iran"]["events"][0]["llm_final_country"], "Iran")
        self.assertEqual(candidate["country_results"]["Syria"]["events"][0]["llm_final_country"], "Syria")

    def test_build_candidate_snapshot_skips_bulk_translation_before_attribution(self):
        analyzer = self.make_analyzer()
        analyzer.MIN_PUBLISHABLE_TOTAL_SIGNALS = 1
        analyzer.MIN_PUBLISHABLE_ACTIVE_COUNTRIES = 1
        analyzer.MIN_SIGNAL_COVERAGE_RATIO = 0.0
        analyzer.MIN_ACTIVE_COUNTRY_COVERAGE_RATIO = 0.0
        analyzer.load_history = lambda: []
        analyzer._utc_now = lambda: datetime(2026, 3, 28, 8, 0, 0)
        analyzer._load_existing_summary = lambda: {
            "slot_start": "2026-03-28T00:00:00",
            "slot_end": "2026-03-28T06:00:00",
            "generated_at": "2026-03-28T06:00:00",
            "next_refresh_at": "2026-03-28T12:00:00",
            "headline": "Existing brief.",
            "bullets": ["One.", "Two.", "Three."],
            "watch": None,
        }
        analyzer._ensure_translated_titles = lambda events: self.fail("bulk translation should not run before attribution")
        analyzer._build_attribution_prompt = analyzer_module.BNTIAnalyzer._build_attribution_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_attribution_response = analyzer_module.BNTIAnalyzer._parse_attribution_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._build_country_audit_prompt = analyzer_module.BNTIAnalyzer._build_country_audit_prompt.__get__(analyzer, analyzer_module.BNTIAnalyzer)
        analyzer._parse_country_audit_response = analyzer_module.BNTIAnalyzer._parse_country_audit_response.__get__(analyzer, analyzer_module.BNTIAnalyzer)

        responses = iter([
            '[{"id": 1, "primary_country": "Iran", "category": "military_conflict", "subject": "Iranian nuclear facilities"}]',
            '[{"id": 1, "final_country": "Iran"}]',
        ])
        analyzer._call_openrouter = lambda prompt, max_retries=2: next(responses)

        candidate = analyzer.build_candidate_snapshot({
            "Greece": [
                {
                    "title": "ΗΠΑ και Ισραήλ βομβάρδισαν πυρηνικό αντιδραστήρα βαρέος ύδατος στο Ιράν",
                    "link": "https://example.com/iran",
                    "date": "2026-03-28T05:15:00",
                    "source_country": "Greece",
                }
            ]
        })

        self.assertTrue(candidate["publishable"])
        self.assertEqual(candidate["country_results"]["Iran"]["events"][0]["llm_final_country"], "Iran")

    def test_fetch_feed_entries_caps_user_agent_attempts_and_timeout(self):
        analyzer = self.make_analyzer()
        analyzer.user_agents = ["ua-1", "ua-2", "ua-3", "ua-4", "ua-5"]
        analyzer.cache_fresh_ttl_seconds = 3600
        analyzer.cache_stale_ttl_seconds = 21600
        analyzer._get_cached_entries = lambda url, ttl: ([], None)
        analyzer._extract_entries = lambda entries: []
        analyzer._write_cache_entries = lambda url, entries: None
        analyzer._fetch_proxy_entries = lambda url, session, headers: []

        class FakeSession:
            def __init__(self):
                self.calls = []
                self.mounts = []

            def mount(self, prefix, adapter):
                self.mounts.append((prefix, adapter))

            def get(self, url, headers=None, timeout=None, verify=True):
                self.calls.append({
                    "url": url,
                    "timeout": timeout,
                    "user_agent": headers.get("User-Agent") if headers else None,
                    "verify": verify,
                })
                raise requests.exceptions.ReadTimeout("timed out")

        fake_session = FakeSession()
        retry_configs = []

        def fake_http_adapter(max_retries=None):
            retry_configs.append(max_retries)
            return SimpleNamespace(max_retries=max_retries)

        with mock.patch("requests.Session", return_value=fake_session), mock.patch(
            "requests.adapters.HTTPAdapter", side_effect=fake_http_adapter
        ), mock.patch.object(analyzer_module.feedparser, "parse", return_value=SimpleNamespace(entries=[])):
            entries = analyzer.fetch_feed_entries("Iran", "https://example.com/rss")

        self.assertEqual(entries, [])
        self.assertEqual(
            len(fake_session.calls),
            analyzer_module.BNTIAnalyzer.FEED_MAX_USER_AGENT_ATTEMPTS,
        )
        self.assertTrue(
            all(
                call["timeout"] == analyzer_module.BNTIAnalyzer.FEED_REQUEST_TIMEOUT_SECONDS
                for call in fake_session.calls
            )
        )
        self.assertEqual(retry_configs[0].total, analyzer_module.BNTIAnalyzer.FEED_RETRY_TOTAL)
        self.assertEqual(retry_configs[0].connect, analyzer_module.BNTIAnalyzer.FEED_RETRY_CONNECT)
        self.assertEqual(retry_configs[0].read, analyzer_module.BNTIAnalyzer.FEED_RETRY_READ)

    def test_proxy_fetch_uses_bounded_timeout(self):
        analyzer = self.make_analyzer()
        analyzer._build_proxy_url = lambda url: "https://proxy.example"
        analyzer._parse_proxy_markdown = lambda content: []
        analyzer._extract_entries = lambda entries: []

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, headers=None, timeout=None):
                self.calls.append({"url": url, "timeout": timeout})
                return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        fake_session = FakeSession()
        analyzer._fetch_proxy_entries("https://example.com/rss", fake_session, {})

        self.assertEqual(len(fake_session.calls), 1)
        self.assertEqual(
            fake_session.calls[0]["timeout"],
            analyzer_module.BNTIAnalyzer.FEED_PROXY_TIMEOUT_SECONDS,
        )

    def test_fetch_feed_entries_skips_extra_network_fallbacks_after_timeout(self):
        analyzer = self.make_analyzer()
        analyzer.user_agents = ["ua-1"]
        analyzer.cache_fresh_ttl_seconds = 3600
        analyzer.cache_stale_ttl_seconds = 21600
        analyzer._get_cached_entries = lambda url, ttl: ([], None)
        analyzer._extract_entries = lambda entries: []
        analyzer._write_cache_entries = lambda url, entries: None
        proxy_calls = []
        analyzer._fetch_proxy_entries = lambda url, session, headers: proxy_calls.append(url) or []

        class FakeSession:
            def mount(self, prefix, adapter):
                return None

            def get(self, url, headers=None, timeout=None, verify=True):
                raise requests.exceptions.ReadTimeout("timed out")

        with mock.patch("requests.Session", return_value=FakeSession()), mock.patch(
            "requests.adapters.HTTPAdapter", side_effect=lambda max_retries=None: SimpleNamespace(max_retries=max_retries)
        ), mock.patch.object(
            analyzer_module.feedparser,
            "parse",
            side_effect=AssertionError("direct feedparser fallback should be skipped after timeouts"),
        ):
            entries = analyzer.fetch_feed_entries("Iran", "https://example.com/rss")

        self.assertEqual(entries, [])
        self.assertEqual(proxy_calls, [])


if __name__ == "__main__":
    unittest.main()
