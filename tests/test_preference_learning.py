"""Comprehensive tests for preference learning module."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from assistant.preference_learning import (
    ActionPattern,
    ContextualSuggestion,
    PreferenceLearner,
    UserExecutionProfile,
)


class AuditHistorySetup:
    """Helper to create sample audit histories."""

    @staticmethod
    def create_audit_file(temp_dir: Path, entries: list[dict]) -> Path:
        """Create a sample audit file with given entries."""
        audit_path = temp_dir / "action_audit.jsonl"
        with audit_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return audit_path

    @staticmethod
    def make_entry(
        action_kind: str,
        status: str = "confirmed",
        timestamp_offset_hours: int = 0,
        description: str = "test action",
    ) -> dict:
        """Create a sample audit entry."""
        dt = datetime.now(UTC) - timedelta(hours=timestamp_offset_hours)
        return {
            "status": status,
            "action_kind": action_kind,
            "description": description,
            "target": "test_target",
            "requested_by": "test_user",
            "result": "success" if status == "confirmed" else "cancelled",
            "created_at": dt.isoformat().replace("+00:00", "Z"),
        }


class PatternAnalysisTests(unittest.TestCase):
    """Tests for pattern analysis from audit history."""

    def test_analyze_empty_audit_history(self):
        """Pattern analysis on empty audit log returns empty dict."""
        with TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "action_audit.jsonl"
            learner = PreferenceLearner(audit_path)

            patterns = learner.analyze_audit_history()

            self.assertEqual(patterns, {})

    def test_analyze_nonexistent_audit_file(self):
        """Pattern analysis with no audit file returns empty dict."""
        learner = PreferenceLearner(Path("/nonexistent/path.jsonl"))
        patterns = learner.analyze_audit_history()
        self.assertEqual(patterns, {})

    def test_analyze_single_action_type(self):
        """Pattern analysis creates correct pattern for single action type."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("open_app", "cancelled"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            patterns = learner.analyze_audit_history()

            self.assertIn("open_app", patterns)
            pattern = patterns["open_app"]
            self.assertEqual(pattern.frequency, 3)
            self.assertEqual(pattern.successful_count, 2)
            self.assertEqual(pattern.failed_count, 1)
            self.assertAlmostEqual(pattern.success_rate, 2 / 3, places=2)

    def test_analyze_multiple_action_types(self):
        """Pattern analysis handles multiple action types correctly."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("open_file", "confirmed"),
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("delete_file", "cancelled"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            patterns = learner.analyze_audit_history()

            self.assertEqual(len(patterns), 3)
            self.assertIn("open_app", patterns)
            self.assertIn("open_file", patterns)
            self.assertIn("delete_file", patterns)

    def test_pattern_confidence_increases_with_frequency(self):
        """Confidence level increases as frequency increases."""
        with TemporaryDirectory() as temp_dir:
            # Create two patterns with same success rate but different frequencies
            entries_low = [
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_a", "confirmed"),
            ]
            entries_high = [
                AuditHistorySetup.make_entry("action_b", "confirmed")
                for _ in range(20)
            ]

            entries = entries_low + entries_high
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            patterns = learner.analyze_audit_history()

            conf_low = patterns["action_a"].confidence_level
            conf_high = patterns["action_b"].confidence_level
            self.assertLess(conf_low, conf_high)

    def test_pattern_time_of_day_extraction(self):
        """Pattern identifies preferred time of day."""
        with TemporaryDirectory() as temp_dir:
            now = datetime.now(UTC)
            entries = [
                # Morning actions (6:00 AM)
                {
                    "status": "confirmed",
                    "action_kind": "morning_task",
                    "description": "test",
                    "target": "test",
                    "requested_by": "user",
                    "result": "success",
                    "created_at": (now.replace(hour=6) - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
                },
                # Afternoon action (3:00 PM)
                {
                    "status": "confirmed",
                    "action_kind": "afternoon_task",
                    "description": "test",
                    "target": "test",
                    "requested_by": "user",
                    "result": "success",
                    "created_at": (now.replace(hour=15) - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                },
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            patterns = learner.analyze_audit_history()

            self.assertEqual(patterns["morning_task"].preferred_time_of_day, "morning")
            self.assertEqual(patterns["afternoon_task"].preferred_time_of_day, "afternoon")

    def test_analyze_respects_limit(self):
        """Pattern analysis respects the limit parameter."""
        with TemporaryDirectory() as temp_dir:
            # Create 100 entries
            entries = [
                AuditHistorySetup.make_entry("action", "confirmed", i % 10)
                for i in range(100)
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            patterns_all = learner.analyze_audit_history(limit=100)
            patterns_limited = learner.analyze_audit_history(limit=10)

            # All patterns should have the same action, but different frequencies
            self.assertIn("action", patterns_all)
            self.assertIn("action", patterns_limited)
            self.assertEqual(patterns_all["action"].frequency, 100)
            self.assertEqual(patterns_limited["action"].frequency, 10)


class ProfileBuildingTests(unittest.TestCase):
    """Tests for user profile building."""

    def test_build_profile_empty_history(self):
        """Profile building with empty history returns empty profile."""
        with TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "action_audit.jsonl"
            learner = PreferenceLearner(audit_path)

            profile = learner.build_user_profile()

            self.assertEqual(profile.total_actions, 0)
            self.assertEqual(profile.learning_data_points, 0)
            self.assertIsNone(profile.preferred_workflow)

    def test_build_profile_basic_stats(self):
        """Profile building calculates basic statistics correctly."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_b", "confirmed"),
                AuditHistorySetup.make_entry("action_a", "cancelled"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            profile = learner.build_user_profile()

            self.assertEqual(profile.total_actions, 3)
            self.assertEqual(profile.learning_data_points, 3)
            self.assertAlmostEqual(profile.approval_rate, 2 / 3, places=2)
            self.assertAlmostEqual(profile.rejection_rate, 1 / 3, places=2)

    def test_build_profile_most_frequent_actions(self):
        """Profile correctly identifies most frequent actions."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_b", "confirmed"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            profile = learner.build_user_profile()

            self.assertEqual(profile.most_frequent_actions[0][0], "action_a")
            self.assertEqual(profile.most_frequent_actions[0][1], 3)
            self.assertEqual(profile.preferred_workflow, "action_a")

    def test_build_profile_action_sequences(self):
        """Profile correctly tracks action sequences."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("edit_file", "confirmed"),
                AuditHistorySetup.make_entry("save_file", "confirmed"),
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("edit_file", "confirmed"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            profile = learner.build_user_profile()

            # After "open_app", user usually does "edit_file"
            self.assertIn("open_app", profile.action_sequences)
            sequences_after_open = profile.action_sequences["open_app"]
            self.assertEqual(sequences_after_open[0][0], "edit_file")
            self.assertEqual(sequences_after_open[0][1], 2)

    def test_profile_caching(self):
        """Profile is cached after first build."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditHistorySetup.make_entry("action", "confirmed")]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            profile1 = learner.build_user_profile()
            profile2 = learner.build_user_profile()

            # Should be same object (cached)
            self.assertIs(profile1, profile2)

    def test_clear_cache(self):
        """Cache clearing works correctly."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditHistorySetup.make_entry("action", "confirmed")]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            profile1 = learner.build_user_profile()
            learner.clear_cache()
            profile2 = learner.build_user_profile()

            # Should be different objects (cache was cleared)
            self.assertIsNot(profile1, profile2)
            # But with same data
            self.assertEqual(profile1.total_actions, profile2.total_actions)


class AdaptiveThresholdTests(unittest.TestCase):
    """Tests for adaptive confirmation thresholds."""

    def test_threshold_high_success_rate_lowers_threshold(self):
        """High success rate actions get lower confirmation threshold."""
        with TemporaryDirectory() as temp_dir:
            # Create action with 100% success rate
            entries = [
                AuditHistorySetup.make_entry("reliable_action", "confirmed")
                for _ in range(30)
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            threshold = learner.get_adaptive_threshold("reliable_action", base_threshold=0.5)

            # Should be lower than base threshold
            self.assertLess(threshold, 0.5)

    def test_threshold_low_success_rate_raises_threshold(self):
        """Low success rate actions get higher confirmation threshold."""
        with TemporaryDirectory() as temp_dir:
            # Create action with 20% success rate
            entries = [
                AuditHistorySetup.make_entry("risky_action", "confirmed"),
                AuditHistorySetup.make_entry("risky_action", "cancelled"),
                AuditHistorySetup.make_entry("risky_action", "cancelled"),
                AuditHistorySetup.make_entry("risky_action", "cancelled"),
                AuditHistorySetup.make_entry("risky_action", "cancelled"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            threshold = learner.get_adaptive_threshold("risky_action", base_threshold=0.5)

            # Should be higher than base threshold
            self.assertGreater(threshold, 0.5)

    def test_threshold_unknown_action_returns_base(self):
        """Unknown action returns base threshold."""
        with TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "action_audit.jsonl"
            learner = PreferenceLearner(audit_path)

            threshold = learner.get_adaptive_threshold("unknown_action", base_threshold=0.7)

            self.assertEqual(threshold, 0.7)

    def test_threshold_in_valid_range(self):
        """Adaptive thresholds are always in valid 0.1-0.9 range."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditHistorySetup.make_entry("action", "confirmed")
                for _ in range(100)
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            threshold = learner.get_adaptive_threshold("action", base_threshold=0.5)

            self.assertGreaterEqual(threshold, 0.1)
            self.assertLessEqual(threshold, 0.9)


class AutoApprovalTests(unittest.TestCase):
    """Tests for auto-approval decision logic."""

    def test_auto_approve_trusted_action(self):
        """Trusted actions are auto-approved."""
        with TemporaryDirectory() as temp_dir:
            # Create very reliable action done many times
            entries = [
                AuditHistorySetup.make_entry("trusted_action", "confirmed")
                for _ in range(30)
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            should_approve = learner.should_auto_approve("trusted_action", user_approval_rate=0.95)

            self.assertTrue(should_approve)

    def test_auto_approve_requires_high_frequency(self):
        """Auto-approval requires action to be done frequently."""
        with TemporaryDirectory() as temp_dir:
            # Create reliable but infrequent action
            entries = [
                AuditHistorySetup.make_entry("rare_action", "confirmed"),
                AuditHistorySetup.make_entry("rare_action", "confirmed"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            should_approve = learner.should_auto_approve("rare_action", user_approval_rate=0.95)

            self.assertFalse(should_approve)

    def test_auto_approve_requires_high_user_trust(self):
        """Auto-approval requires user to generally approve actions."""
        with TemporaryDirectory() as temp_dir:
            # Create frequent reliable action
            entries = [
                AuditHistorySetup.make_entry("frequent_action", "confirmed")
                for _ in range(30)
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            # But user has low approval rate overall
            should_approve = learner.should_auto_approve("frequent_action", user_approval_rate=0.5)

            self.assertFalse(should_approve)

    def test_auto_approve_unknown_action(self):
        """Unknown actions are not auto-approved."""
        learner = PreferenceLearner(Path("/nonexistent.jsonl"))
        should_approve = learner.should_auto_approve("unknown_action", user_approval_rate=0.95)
        self.assertFalse(should_approve)


class SuggestionTests(unittest.TestCase):
    """Tests for context-aware action suggestions."""

    def test_suggest_next_action_from_sequence(self):
        """Suggestion engine recommends most likely next action."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("edit_file", "confirmed"),
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("edit_file", "confirmed"),
                AuditHistorySetup.make_entry("save_file", "confirmed"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            suggestion = learner.suggest_next_action("open_app")

            self.assertIsNotNone(suggestion)
            self.assertEqual(suggestion.action, "edit_file")
            self.assertGreater(suggestion.confidence, 0.3)

    def test_suggest_no_next_action_for_unknown(self):
        """Unknown actions return no suggestion."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditHistorySetup.make_entry("action_a", "confirmed")]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            suggestion = learner.suggest_next_action("unknown_action")

            self.assertIsNone(suggestion)

    def test_suggest_requires_confidence_threshold(self):
        """Suggestions require at least 30% confidence."""
        with TemporaryDirectory() as temp_dir:
            # Create sequence where action_b follows action_a only 1/10 times
            entries = [
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_b", "confirmed"),  # 1 time
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_c", "confirmed"),  # 9 times
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_c", "confirmed"),
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_c", "confirmed"),
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_c", "confirmed"),
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_c", "confirmed"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            suggestion = learner.suggest_next_action("action_a")

            # Should suggest action_c (90%), not action_b (10%)
            self.assertIsNotNone(suggestion)
            self.assertEqual(suggestion.action, "action_c")

    def test_suggestion_includes_context(self):
        """Suggestions include contextual information."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("edit_file", "confirmed"),
                AuditHistorySetup.make_entry("open_app", "confirmed"),
                AuditHistorySetup.make_entry("edit_file", "confirmed"),
                AuditHistorySetup.make_entry("save_file", "confirmed"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            suggestion = learner.suggest_next_action("open_app")

            self.assertIsNotNone(suggestion)
            self.assertIn("open_app", suggestion.reason)
            self.assertIn("edit_file", suggestion.reason)
            self.assertIn("previous_action", suggestion.context)
            self.assertIn("frequency", suggestion.context)


class LearningStatisticsTests(unittest.TestCase):
    """Tests for learning statistics reporting."""

    def test_statistics_empty_history(self):
        """Statistics with empty history are zeros."""
        with TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "action_audit.jsonl"
            learner = PreferenceLearner(audit_path)

            stats = learner.get_learning_statistics()

            self.assertEqual(stats["total_actions_analyzed"], 0)
            self.assertEqual(stats["unique_action_types"], 0)
            self.assertFalse(stats["has_sequence_data"])

    def test_statistics_with_data(self):
        """Statistics accurately report learning state."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_b", "confirmed"),
                AuditHistorySetup.make_entry("action_a", "confirmed"),
                AuditHistorySetup.make_entry("action_b", "cancelled"),
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            stats = learner.get_learning_statistics()

            self.assertEqual(stats["total_actions_analyzed"], 4)
            self.assertEqual(stats["unique_action_types"], 2)
            self.assertGreater(stats["overall_success_rate"], 0)
            self.assertTrue(stats["has_sequence_data"])


class CachingTests(unittest.TestCase):
    """Tests for caching behavior."""

    def test_pattern_cache_hit(self):
        """Multiple calls to analyze_audit_history use cache."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditHistorySetup.make_entry("action", "confirmed")]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            patterns1 = learner.analyze_audit_history()
            patterns2 = learner.analyze_audit_history()

            # Should be same object
            self.assertIs(patterns1, patterns2)

    def test_clear_cache_resets_patterns(self):
        """Clearing cache invalidates pattern cache."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditHistorySetup.make_entry("action", "confirmed")]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            patterns1 = learner.analyze_audit_history()
            learner.clear_cache()
            patterns2 = learner.analyze_audit_history()

            # Should be different objects
            self.assertIsNot(patterns1, patterns2)

    def test_clear_cache_resets_profile(self):
        """Clearing cache invalidates profile cache."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditHistorySetup.make_entry("action", "confirmed")]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            profile1 = learner.build_user_profile()
            learner.clear_cache()
            profile2 = learner.build_user_profile()

            # Should be different objects
            self.assertIsNot(profile1, profile2)


class EdgeCaseTests(unittest.TestCase):
    """Tests for edge cases and error conditions."""

    def test_malformed_json_entries_ignored(self):
        """Malformed JSON entries are safely skipped."""
        with TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "action_audit.jsonl"
            with audit_path.open("w", encoding="utf-8") as f:
                f.write('{"valid": "entry", "status": "confirmed", "action_kind": "test", "description": "x", "target": "y", "requested_by": "z", "result": "ok", "created_at": "2026-01-01T00:00:00Z"}\n')
                f.write("invalid json\n")
                f.write('{"valid": "entry", "status": "confirmed", "action_kind": "test", "description": "x", "target": "y", "requested_by": "z", "result": "ok", "created_at": "2026-01-01T00:00:00Z"}\n')

            learner = PreferenceLearner(audit_path)
            patterns = learner.analyze_audit_history()

            # Should have processed 2 valid entries
            self.assertIn("test", patterns)
            self.assertEqual(patterns["test"].frequency, 2)

    def test_incomplete_entries_ignored(self):
        """Entries missing required fields are skipped."""
        with TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "action_audit.jsonl"
            with audit_path.open("w", encoding="utf-8") as f:
                # Valid entry
                f.write('{"status": "confirmed", "action_kind": "good", "description": "x", "target": "y", "requested_by": "z", "result": "ok", "created_at": "2026-01-01T00:00:00Z"}\n')
                # Missing action_kind
                f.write('{"status": "confirmed", "description": "x", "target": "y", "requested_by": "z", "result": "ok", "created_at": "2026-01-01T00:00:00Z"}\n')

            learner = PreferenceLearner(audit_path)
            patterns = learner.analyze_audit_history()

            # Should have only "good" entry, not skipped one
            self.assertIn("good", patterns)
            self.assertEqual(patterns["good"].frequency, 1)

    def test_zero_frequency_success_rate(self):
        """Success rate calculation handles zero frequency."""
        with TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "action_audit.jsonl"
            learner = PreferenceLearner(audit_path)

            # With empty history
            patterns = learner.analyze_audit_history()
            self.assertEqual(patterns, {})

    def test_very_large_audit_log(self):
        """Learner handles large audit logs within memory."""
        with TemporaryDirectory() as temp_dir:
            # Create 1000 entries
            entries = [
                AuditHistorySetup.make_entry("action", "confirmed" if i % 2 == 0 else "cancelled", i % 100)
                for i in range(1000)
            ]
            audit_path = AuditHistorySetup.create_audit_file(Path(temp_dir), entries)
            learner = PreferenceLearner(audit_path)

            profile = learner.build_user_profile()

            self.assertEqual(profile.learning_data_points, 1000)
            self.assertIn("action", profile.action_patterns)


if __name__ == "__main__":
    unittest.main()
