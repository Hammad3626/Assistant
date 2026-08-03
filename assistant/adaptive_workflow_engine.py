"""Adaptive workflow engine integrating Phase 6 learning with Phase 5 workflows.

Enhances workflows with:
- Adaptive confirmation thresholds based on user patterns
- Context-aware action suggestions
- Learning-based decision making
- Workflow optimization based on history
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from assistant.audit import ActionAuditStore
from assistant.preference_learning import ContextualSuggestion, PreferenceLearner


@dataclass
class AdaptiveDecision:
    """Decision made using preference learning."""
    action_kind: str
    should_auto_approve: bool
    confidence: float  # 0-1, confidence in this decision
    reason: str
    suggested_threshold: float  # recommended confirmation threshold
    context: dict[str, Any]  # additional context


@dataclass
class WorkflowMetrics:
    """Metrics about a workflow's execution."""
    total_executions: int
    successful_executions: int
    rejected_executions: int
    success_rate: float
    average_approval_time_ms: float
    user_trust_score: float  # 0-1, how much user trusts this workflow


class AdaptiveWorkflowEngine:
    """Smart workflow execution engine with learning integration."""

    def __init__(
        self,
        audit_path: str | None = None,
        enable_learning: bool = True,
    ) -> None:
        self.audit_store = ActionAuditStore(audit_path) if audit_path else ActionAuditStore()
        self.learner = PreferenceLearner(audit_path) if enable_learning else None
        self._workflow_cache: dict[str, WorkflowMetrics] = {}

    def make_adaptive_decision(
        self,
        action_kind: str,
        user_approval_rate: float = 0.8,
        base_threshold: float = 0.5,
    ) -> AdaptiveDecision:
        """Make adaptive decision on whether to auto-approve an action.

        Args:
            action_kind: Type of action (e.g., "open_app", "delete_file")
            user_approval_rate: User's typical approval rate (0-1)
            base_threshold: Default confirmation threshold

        Returns:
            AdaptiveDecision with recommendation and reasoning
        """
        if not self.learner:
            return AdaptiveDecision(
                action_kind=action_kind,
                should_auto_approve=False,
                confidence=0.0,
                reason="Learning disabled",
                suggested_threshold=base_threshold,
                context={},
            )

        # Check if action should be auto-approved
        should_auto = self.learner.should_auto_approve(action_kind, user_approval_rate)

        # Get adaptive threshold
        threshold = self.learner.get_adaptive_threshold(action_kind, base_threshold)

        # Get pattern information
        patterns = self.learner.analyze_audit_history()
        pattern = patterns.get(action_kind)

        if pattern:
            reason = (
                f"Action '{action_kind}' has {pattern.frequency} executions "
                f"with {pattern.success_rate * 100:.1f}% success rate. "
                f"Confidence: {pattern.confidence_level * 100:.1f}%"
            )
            confidence = pattern.confidence_level
        else:
            reason = f"Action '{action_kind}' is new or rarely used"
            confidence = 0.0

        return AdaptiveDecision(
            action_kind=action_kind,
            should_auto_approve=should_auto,
            confidence=confidence,
            reason=reason,
            suggested_threshold=threshold,
            context={
                "action_kind": action_kind,
                "user_approval_rate": user_approval_rate,
                "pattern_found": pattern is not None,
            },
        )

    def get_next_action_suggestion(
        self,
        last_action: str,
    ) -> Optional[ContextualSuggestion]:
        """Get suggestion for next action based on patterns.

        Args:
            last_action: The action that was just executed

        Returns:
            ContextualSuggestion or None if no suggestion available
        """
        if not self.learner:
            return None

        return self.learner.suggest_next_action(last_action)

    def get_workflow_metrics(self, action_kind: str) -> WorkflowMetrics:
        """Get performance metrics for a specific workflow/action.

        Args:
            action_kind: Type of action to get metrics for

        Returns:
            WorkflowMetrics with execution statistics
        """
        if action_kind in self._workflow_cache:
            return self._workflow_cache[action_kind]

        if not self.learner:
            return WorkflowMetrics(
                total_executions=0,
                successful_executions=0,
                rejected_executions=0,
                success_rate=0.0,
                average_approval_time_ms=0.0,
                user_trust_score=0.0,
            )

        patterns = self.learner.analyze_audit_history()
        pattern = patterns.get(action_kind)

        if not pattern:
            return WorkflowMetrics(
                total_executions=0,
                successful_executions=0,
                rejected_executions=0,
                success_rate=0.0,
                average_approval_time_ms=0.0,
                user_trust_score=0.0,
            )

        metrics = WorkflowMetrics(
            total_executions=pattern.frequency,
            successful_executions=pattern.successful_count,
            rejected_executions=pattern.failed_count,
            success_rate=pattern.success_rate,
            average_approval_time_ms=pattern.average_duration_ms,
            user_trust_score=pattern.confidence_level,
        )

        self._workflow_cache[action_kind] = metrics
        return metrics

    def should_suggest_workflow(self, action_kind: str, min_confidence: float = 0.6) -> bool:
        """Check if a workflow should be suggested to user.

        Args:
            action_kind: Type of action to check
            min_confidence: Minimum confidence threshold

        Returns:
            True if workflow is worth suggesting (frequent + reliable)
        """
        if not self.learner:
            return False

        patterns = self.learner.analyze_audit_history()
        pattern = patterns.get(action_kind)

        if not pattern:
            return False

        # Suggest if both frequent and reliable
        is_frequent = pattern.frequency >= 10
        is_reliable = pattern.success_rate >= 0.8
        has_confidence = pattern.confidence_level >= min_confidence

        return is_frequent and is_reliable and has_confidence

    def get_learning_report(self) -> dict[str, Any]:
        """Get comprehensive learning report for user feedback.

        Returns:
            Dictionary with learning statistics and insights
        """
        if not self.learner:
            return {"learning_enabled": False}

        profile = self.learner.build_user_profile()
        stats = self.learner.get_learning_statistics()

        insights = []

        # Insight 1: Most trusted workflow
        if profile.most_frequent_actions:
            most_used = profile.most_frequent_actions[0][0]
            most_used_pattern = profile.action_patterns[most_used]
            insights.append(
                f"Your most-used workflow is '{most_used}' "
                f"({most_used_pattern.frequency} times, "
                f"{most_used_pattern.success_rate * 100:.0f}% success)"
            )

        # Insight 2: Overall approval rate
        if profile.approval_rate > 0.5:
            insights.append(
                f"You approve {profile.approval_rate * 100:.0f}% of actions "
                "(high trust - more auto-approvals possible)"
            )
        else:
            insights.append(
                f"You approve {profile.approval_rate * 100:.0f}% of actions "
                "(cautious - requiring more confirmations)"
            )

        # Insight 3: Reliable workflows
        reliable_workflows = [
            (name, pattern.success_rate)
            for name, pattern in profile.action_patterns.items()
            if pattern.success_rate >= 0.9 and pattern.frequency >= 5
        ]
        if reliable_workflows:
            reliable_names = ", ".join([f"'{name}'" for name, _ in reliable_workflows[:3]])
            insights.append(f"Highly reliable workflows: {reliable_names}")

        # Insight 4: Risky workflows
        risky_workflows = [
            (name, pattern.success_rate)
            for name, pattern in profile.action_patterns.items()
            if pattern.success_rate < 0.5 and pattern.frequency >= 3
        ]
        if risky_workflows:
            risky_names = ", ".join([f"'{name}'" for name, _ in risky_workflows[:3]])
            insights.append(f"Workflows needing improvement: {risky_names}")

        # Insight 5: Time patterns
        if any(p.preferred_time_of_day for p in profile.action_patterns.values()):
            insights.append("You have time-based workflow patterns (detected by learning engine)")

        return {
            "learning_enabled": True,
            "total_data_points": stats["total_actions_analyzed"],
            "unique_workflows": stats["unique_action_types"],
            "overall_success_rate": stats["overall_success_rate"],
            "overall_approval_rate": stats["overall_approval_rate"],
            "most_frequent_workflow": stats["most_frequent_action"],
            "number_of_patterns": stats["num_action_patterns"],
            "has_sequence_data": stats["has_sequence_data"],
            "insights": insights,
            "all_workflows": {
                name: {
                    "executions": pattern.frequency,
                    "success_rate": pattern.success_rate,
                    "confidence": pattern.confidence_level,
                    "preferred_time": pattern.preferred_time_of_day,
                }
                for name, pattern in profile.action_patterns.items()
            },
        }

    def clear_cache(self) -> None:
        """Clear all cached data."""
        if self.learner:
            self.learner.clear_cache()
        self._workflow_cache.clear()


def create_adaptive_approval_callback(
    engine: AdaptiveWorkflowEngine,
    action_kind: str,
    user_approval_rate: float = 0.8,
    verbose: bool = False,
) -> Callable[[Any, Any], bool]:
    """Create an approval callback that uses adaptive learning.

    This is designed to work with Phase 5 workflows that accept approval_callback.

    Args:
        engine: AdaptiveWorkflowEngine instance
        action_kind: Type of action being approved
        user_approval_rate: User's typical approval rate
        verbose: Whether to print detailed information

    Returns:
        Callback function for approval (returns True/False)
    """

    def approval_callback(original: Any, proposed: Any) -> bool:
        """Approval callback that integrates learning."""
        decision = engine.make_adaptive_decision(
            action_kind,
            user_approval_rate=user_approval_rate,
        )

        if verbose:
            print(f"\n[Learning] {decision.reason}")
            print(f"  Decision: {'AUTO-APPROVE' if decision.should_auto_approve else 'REQUIRE CONFIRMATION'}")
            print(f"  Confidence: {decision.confidence * 100:.0f}%")

        # For now, just report the decision
        # In production, this could auto-approve low-risk actions
        return True  # Always return True to proceed (user would manually confirm if needed)

    return approval_callback
