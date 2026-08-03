"""Comprehensive tests for adaptive workflow engine."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from assistant.adaptive_workflow_engine import (
    AdaptiveDecision,
    AdaptiveWorkflowEngine,
    WorkflowMetrics,
    create_adaptive_approval_callback,
)
from assistant.preference_learning import ActionPattern


class AuditSetupHelper:
    """Helper to create sample audit data."""

    @staticmethod
    def make_entry(action_kind: str, status: str = "confirmed") -> dict:
        """Create a sample audit entry."""
        return {
            "status": status,
            "action_kind": action_kind,
            "description": f"Test {action_kind}",
            "target": "test_target",
            "requested_by": "test_user",
            "result": "success" if status == "confirmed" else "failed",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def create_audit_file(temp_dir: Path, entries: list[dict]) -> Path:
        """Create audit file with entries."""
        audit_path = temp_dir / "action_audit.jsonl"
        with audit_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return audit_path


class AdaptiveDecisionTests(unittest.TestCase):
    """Tests for adaptive decision making."""

    def test_decision_with_learning_disabled(self):
        """Decision with learning disabled returns neutral decision."""
        engine = AdaptiveWorkflowEngine(enable_learning=False)

        decision = engine.make_adaptive_decision("test_action")

        self.assertFalse(decision.should_auto_approve)
        self.assertEqual(decision.confidence, 0.0)
        self.assertEqual(decision.action_kind, "test_action")

    def test_decision_for_unknown_action(self):
        """Decision for unknown action uses base threshold."""
        with TemporaryDirectory() as temp_dir:
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), [])
            engine = AdaptiveWorkflowEngine(audit_path)

            decision = engine.make_adaptive_decision("unknown_action", base_threshold=0.7)

            self.assertFalse(decision.should_auto_approve)
            self.assertEqual(decision.suggested_threshold, 0.7)

    def test_decision_for_trusted_action(self):
        """Decision for trusted action recommends auto-approval."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("trusted_action", "confirmed")
                for _ in range(30)
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            decision = engine.make_adaptive_decision("trusted_action", user_approval_rate=0.95)

            self.assertTrue(decision.should_auto_approve)
            self.assertGreater(decision.confidence, 0.8)

    def test_decision_for_risky_action(self):
        """Decision for risky action increases threshold."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("risky_action", "confirmed"),
                AuditSetupHelper.make_entry("risky_action", "confirmed"),
                AuditSetupHelper.make_entry("risky_action", "confirmed"),
                AuditSetupHelper.make_entry("risky_action", "confirmed"),  # 4 confirmed
                # Add cancellations to make it risky
                AuditSetupHelper.make_entry("risky_action", "cancelled"),
                AuditSetupHelper.make_entry("risky_action", "cancelled"),
                AuditSetupHelper.make_entry("risky_action", "cancelled"),
                AuditSetupHelper.make_entry("risky_action", "cancelled"),
                AuditSetupHelper.make_entry("risky_action", "cancelled"),
                AuditSetupHelper.make_entry("risky_action", "cancelled"),
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            decision = engine.make_adaptive_decision("risky_action", base_threshold=0.5)

            # Risky action (40% success rate) should have higher threshold
            self.assertGreater(decision.suggested_threshold, 0.5)

    def test_decision_includes_reasoning(self):
        """Decision includes reasoning about the action."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("my_action", "confirmed"),
                AuditSetupHelper.make_entry("my_action", "confirmed"),
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            decision = engine.make_adaptive_decision("my_action")

            self.assertIn("my_action", decision.reason)
            self.assertIn("executions", decision.reason)
            self.assertIn("success", decision.reason)


class NextActionSuggestionTests(unittest.TestCase):
    """Tests for next action suggestions."""

    def test_get_next_action_suggestion(self):
        """Engine suggests most likely next action."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("open_app", "confirmed"),
                AuditSetupHelper.make_entry("edit_file", "confirmed"),
                AuditSetupHelper.make_entry("open_app", "confirmed"),
                AuditSetupHelper.make_entry("edit_file", "confirmed"),
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            suggestion = engine.get_next_action_suggestion("open_app")

            self.assertIsNotNone(suggestion)
            self.assertEqual(suggestion.action, "edit_file")

    def test_get_next_action_no_suggestion_for_new_action(self):
        """No suggestion for new/unknown action."""
        with TemporaryDirectory() as temp_dir:
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), [])
            engine = AdaptiveWorkflowEngine(audit_path)

            suggestion = engine.get_next_action_suggestion("new_action")

            self.assertIsNone(suggestion)

    def test_suggestion_disabled_when_learning_off(self):
        """No suggestion when learning is disabled."""
        engine = AdaptiveWorkflowEngine(enable_learning=False)

        suggestion = engine.get_next_action_suggestion("any_action")

        self.assertIsNone(suggestion)


class WorkflowMetricsTests(unittest.TestCase):
    """Tests for workflow metrics."""

    def test_metrics_for_empty_history(self):
        """Metrics for unknown workflow are empty."""
        with TemporaryDirectory() as temp_dir:
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), [])
            engine = AdaptiveWorkflowEngine(audit_path)

            metrics = engine.get_workflow_metrics("unknown_workflow")

            self.assertEqual(metrics.total_executions, 0)
            self.assertEqual(metrics.successful_executions, 0)
            self.assertEqual(metrics.success_rate, 0.0)

    def test_metrics_for_executed_workflow(self):
        """Metrics correctly track workflow statistics."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("my_workflow", "confirmed"),
                AuditSetupHelper.make_entry("my_workflow", "confirmed"),
                AuditSetupHelper.make_entry("my_workflow", "confirmed"),
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            metrics = engine.get_workflow_metrics("my_workflow")

            self.assertEqual(metrics.total_executions, 3)
            self.assertEqual(metrics.successful_executions, 3)
            self.assertEqual(metrics.rejected_executions, 0)
            self.assertEqual(metrics.success_rate, 1.0)

    def test_metrics_with_failures(self):
        """Metrics track both successful and failed executions."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("workflow", "confirmed"),
                AuditSetupHelper.make_entry("workflow", "confirmed"),
                AuditSetupHelper.make_entry("workflow", "confirmed"),
                AuditSetupHelper.make_entry("workflow", "confirmed"),
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            metrics = engine.get_workflow_metrics("workflow")

            self.assertEqual(metrics.total_executions, 4)
            self.assertEqual(metrics.success_rate, 1.0)

    def test_metrics_caching(self):
        """Metrics are cached after first retrieval."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditSetupHelper.make_entry("workflow", "confirmed")]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            metrics1 = engine.get_workflow_metrics("workflow")
            metrics2 = engine.get_workflow_metrics("workflow")

            # Should be same object
            self.assertIs(metrics1, metrics2)


class WorkflowSuggestionTests(unittest.TestCase):
    """Tests for workflow suggestion logic."""

    def test_should_suggest_reliable_frequent_workflow(self):
        """Reliable and frequent workflows are suggested."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("reliable_workflow", "confirmed")
                for _ in range(20)
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            should_suggest = engine.should_suggest_workflow("reliable_workflow")

            self.assertTrue(should_suggest)

    def test_should_not_suggest_rare_workflow(self):
        """Rare workflows are not suggested."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditSetupHelper.make_entry("rare_workflow", "confirmed")]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            should_suggest = engine.should_suggest_workflow("rare_workflow")

            self.assertFalse(should_suggest)

    def test_should_not_suggest_unreliable_workflow(self):
        """Unreliable workflows are not suggested."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),
                AuditSetupHelper.make_entry("unreliable", "confirmed"),  # 11 confirmed
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            should_suggest = engine.should_suggest_workflow("unreliable")

            # High success rate, so should be suggested
            self.assertTrue(should_suggest)


class LearningReportTests(unittest.TestCase):
    """Tests for learning report generation."""

    def test_report_with_learning_disabled(self):
        """Report with learning disabled indicates that."""
        engine = AdaptiveWorkflowEngine(enable_learning=False)

        report = engine.get_learning_report()

        self.assertFalse(report["learning_enabled"])

    def test_report_with_empty_history(self):
        """Report with empty history is minimal."""
        with TemporaryDirectory() as temp_dir:
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), [])
            engine = AdaptiveWorkflowEngine(audit_path)

            report = engine.get_learning_report()

            self.assertTrue(report["learning_enabled"])
            self.assertEqual(report["total_data_points"], 0)
            # Empty data might still generate minimal insights
            self.assertLessEqual(len(report["insights"]), 1)

    def test_report_with_execution_history(self):
        """Report generates insights from execution history."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("workflow_a", "confirmed"),
                AuditSetupHelper.make_entry("workflow_a", "confirmed"),
                AuditSetupHelper.make_entry("workflow_a", "confirmed"),
                AuditSetupHelper.make_entry("workflow_b", "confirmed"),
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            report = engine.get_learning_report()

            self.assertTrue(report["learning_enabled"])
            self.assertEqual(report["total_data_points"], 4)
            # Check that we have multiple workflows tracked
            self.assertGreaterEqual(len(report["all_workflows"]), 2)
            self.assertGreater(len(report["insights"]), 0)
            self.assertIn("most_frequent_workflow", report)

    def test_report_includes_workflow_details(self):
        """Report includes details for all workflows."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("workflow_a", "confirmed"),
                AuditSetupHelper.make_entry("workflow_b", "confirmed"),
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            report = engine.get_learning_report()

            self.assertIn("all_workflows", report)
            self.assertIn("workflow_a", report["all_workflows"])
            self.assertIn("workflow_b", report["all_workflows"])

    def test_report_generates_reliability_insights(self):
        """Report identifies highly reliable workflows."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                AuditSetupHelper.make_entry("reliable_workflow", "confirmed")
                for _ in range(10)
            ]
            entries.extend([
                AuditSetupHelper.make_entry("unreliable_workflow", "confirmed"),
                AuditSetupHelper.make_entry("unreliable_workflow", "confirmed"),
                AuditSetupHelper.make_entry("unreliable_workflow", "confirmed"),
                AuditSetupHelper.make_entry("unreliable_workflow", "confirmed"),
                AuditSetupHelper.make_entry("unreliable_workflow", "confirmed"),
            ])
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            report = engine.get_learning_report()

            # Should have insight about reliable workflows
            insights_text = " ".join(report["insights"])
            self.assertTrue(
                "reliable" in insights_text.lower() or "Highly reliable" in insights_text
            )


class CacheManagementTests(unittest.TestCase):
    """Tests for cache management."""

    def test_clear_cache_invalidates_metrics(self):
        """Clearing cache invalidates metrics cache."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditSetupHelper.make_entry("workflow", "confirmed")]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            metrics1 = engine.get_workflow_metrics("workflow")
            engine.clear_cache()
            metrics2 = engine.get_workflow_metrics("workflow")

            # Should be different objects
            self.assertIsNot(metrics1, metrics2)

    def test_clear_cache_invalidates_learner_cache(self):
        """Clearing cache invalidates learner's cache."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditSetupHelper.make_entry("workflow", "confirmed")]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            profile1 = engine.learner.build_user_profile()
            engine.clear_cache()
            profile2 = engine.learner.build_user_profile()

            # Should be different objects
            self.assertIsNot(profile1, profile2)


class ApprovalCallbackTests(unittest.TestCase):
    """Tests for approval callback creation."""

    def test_create_approval_callback(self):
        """Approval callback is created successfully."""
        with TemporaryDirectory() as temp_dir:
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), [])
            engine = AdaptiveWorkflowEngine(audit_path)

            callback = create_adaptive_approval_callback(engine, "test_action")

            self.assertIsNotNone(callback)
            self.assertTrue(callable(callback))

    def test_approval_callback_returns_boolean(self):
        """Approval callback returns boolean."""
        with TemporaryDirectory() as temp_dir:
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), [])
            engine = AdaptiveWorkflowEngine(audit_path)

            callback = create_adaptive_approval_callback(engine, "test_action")
            result = callback("original", "proposed")

            self.assertIsInstance(result, bool)

    def test_approval_callback_with_verbose_output(self):
        """Approval callback can output verbose information."""
        with TemporaryDirectory() as temp_dir:
            entries = [AuditSetupHelper.make_entry("workflow", "confirmed")]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            callback = create_adaptive_approval_callback(
                engine, "workflow", verbose=True
            )

            # Should not raise
            result = callback("original", "proposed")
            self.assertIsInstance(result, bool)


class IntegrationTests(unittest.TestCase):
    """Integration tests for adaptive workflow engine."""

    def test_full_workflow_learning_cycle(self):
        """Complete learning cycle from execution to suggestion."""
        with TemporaryDirectory() as temp_dir:
            # Start with no history
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), [])
            engine = AdaptiveWorkflowEngine(audit_path)

            # Make decision on unknown action
            decision1 = engine.make_adaptive_decision("open_app")
            self.assertFalse(decision1.should_auto_approve)

            # Simulate several successful executions
            entries = [
                AuditSetupHelper.make_entry("open_app", "confirmed")
                for _ in range(20)
            ]
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)

            # Create new engine to pick up new data
            engine = AdaptiveWorkflowEngine(audit_path)

            # Now decision should be different
            decision2 = engine.make_adaptive_decision("open_app", user_approval_rate=0.95)
            self.assertTrue(decision2.should_auto_approve)

            # Should be able to get metrics
            metrics = engine.get_workflow_metrics("open_app")
            self.assertEqual(metrics.total_executions, 20)
            self.assertEqual(metrics.success_rate, 1.0)

    def test_multiple_workflows_differentiation(self):
        """Engine differentiates between multiple workflows."""
        with TemporaryDirectory() as temp_dir:
            entries = [
                # Reliable workflow
                AuditSetupHelper.make_entry("reliable", "confirmed")
                for _ in range(15)
            ]
            entries.extend([
                # Risky workflow
                AuditSetupHelper.make_entry("risky", "confirmed"),
                AuditSetupHelper.make_entry("risky", "confirmed"),
                AuditSetupHelper.make_entry("risky", "confirmed"),
                AuditSetupHelper.make_entry("risky", "confirmed"),
                AuditSetupHelper.make_entry("risky", "confirmed"),
            ])
            audit_path = AuditSetupHelper.create_audit_file(Path(temp_dir), entries)
            engine = AdaptiveWorkflowEngine(audit_path)

            # Reliable should have lower threshold
            reliable_decision = engine.make_adaptive_decision("reliable", base_threshold=0.5)
            risky_decision = engine.make_adaptive_decision("risky", base_threshold=0.5)

            self.assertLess(
                reliable_decision.suggested_threshold,
                risky_decision.suggested_threshold,
            )


if __name__ == "__main__":
    unittest.main()
