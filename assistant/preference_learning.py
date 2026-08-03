"""Smart context and preference learning from action history.

Analyzes command execution patterns to:
- Build user execution profiles
- Predict user preferences
- Adapt confirmation thresholds dynamically
- Generate context-aware suggestions
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class ActionPattern:
    """Statistics about a specific action type."""
    action_kind: str
    frequency: int
    successful_count: int
    failed_count: int
    success_rate: float  # 0-1
    last_executed: Optional[str]  # ISO datetime
    average_duration_ms: float  # milliseconds
    confidence_level: float  # 0-1, based on success rate
    preferred_time_of_day: Optional[str]  # "morning", "afternoon", "evening"


@dataclass(frozen=True)
class UserExecutionProfile:
    """Aggregated profile of user behavior patterns."""
    total_actions: int
    action_patterns: dict[str, ActionPattern]
    most_frequent_actions: list[tuple[str, int]]
    action_sequences: dict[str, list[tuple[str, int]]]  # what follows what action
    approval_rate: float  # 0-1, how often user approves actions
    rejection_rate: float  # 0-1, how often user rejects actions
    success_rate: float  # overall success rate
    preferred_workflow: Optional[str]  # most-used workflow type
    learning_data_points: int  # number of audit entries analyzed


@dataclass
class ContextualSuggestion:
    """Suggestion based on learned patterns."""
    action: str
    action_kind: str
    confidence: float  # 0-1, probability user wants this
    reason: str  # why we're suggesting this
    auto_approve_threshold: float  # approval rate to auto-approve this action
    context: dict[str, Any] = field(default_factory=dict)  # additional context


class PreferenceLearner:
    """Learn and predict user preferences from action history."""

    def __init__(self, audit_path: str | Path = Path("data/action_audit.jsonl")) -> None:
        self.audit_path = Path(audit_path)
        self._cache_profile: Optional[UserExecutionProfile] = None
        self._cache_patterns: Optional[dict[str, ActionPattern]] = None

    def analyze_audit_history(self, limit: int = 1000) -> dict[str, ActionPattern]:
        """Analyze action audit log and build patterns for each action type."""
        # Only use cache for default limit to avoid stale data
        if self._cache_patterns is not None and limit == 1000:
            return self._cache_patterns

        if not self.audit_path.exists():
            return {}

        patterns: dict[str, list[dict[str, Any]]] = defaultdict(list)
        try:
            lines = self.audit_path.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            return {}

        # Parse audit entries
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(raw, dict):
                continue

            action_kind = raw.get("action_kind", "unknown")
            patterns[action_kind].append(raw)

        # Build patterns for each action type
        result: dict[str, ActionPattern] = {}
        for action_kind, entries in patterns.items():
            if not entries:
                continue

            successful = sum(1 for e in entries if e.get("status") == "confirmed")
            failed = sum(1 for e in entries if e.get("status") == "cancelled")
            total = len(entries)

            success_rate = successful / total if total > 0 else 0.0
            confidence = min(success_rate * (total / max(total, 10)), 1.0)  # confidence increases with data

            # Extract time patterns
            times_of_day = _extract_times_of_day([e.get("created_at", "") for e in entries])
            preferred_time = max(times_of_day.items(), key=lambda x: x[1])[0] if times_of_day else None

            # Calculate average duration (estimate from description length as proxy)
            avg_duration = sum(
                len(e.get("description", "")) * 10 for e in entries  # rough estimate: chars * 10ms
            ) / total if total > 0 else 0.0

            result[action_kind] = ActionPattern(
                action_kind=action_kind,
                frequency=total,
                successful_count=successful,
                failed_count=failed,
                success_rate=success_rate,
                last_executed=entries[-1].get("created_at") if entries else None,
                average_duration_ms=avg_duration,
                confidence_level=confidence,
                preferred_time_of_day=preferred_time,
            )

        # Only cache if using default limit
        if limit == 1000:
            self._cache_patterns = result
        return result

    def build_user_profile(self, limit: int = 1000) -> UserExecutionProfile:
        """Build comprehensive user execution profile."""
        if self._cache_profile is not None:
            return self._cache_profile

        patterns = self.analyze_audit_history(limit)

        if not self.audit_path.exists():
            return UserExecutionProfile(
                total_actions=0,
                action_patterns={},
                most_frequent_actions=[],
                action_sequences={},
                approval_rate=0.0,
                rejection_rate=0.0,
                success_rate=0.0,
                preferred_workflow=None,
                learning_data_points=0,
            )

        try:
            lines = self.audit_path.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            return UserExecutionProfile(
                total_actions=0,
                action_patterns={},
                most_frequent_actions=[],
                action_sequences={},
                approval_rate=0.0,
                rejection_rate=0.0,
                success_rate=0.0,
                preferred_workflow=None,
                learning_data_points=0,
            )

        # Parse entries and build sequences
        entries: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if isinstance(raw, dict):
                    entries.append(raw)
            except json.JSONDecodeError:
                continue

        # Build sequences (what action follows another)
        action_sequences: dict[str, list[tuple[str, int]]] = defaultdict(lambda: Counter())
        for i in range(len(entries) - 1):
            current = entries[i].get("action_kind", "unknown")
            next_action = entries[i + 1].get("action_kind", "unknown")
            action_sequences[current][next_action] += 1

        # Convert Counter to list of tuples
        sequences_list = {
            action: sorted(counts.items(), key=lambda x: x[1], reverse=True)
            for action, counts in action_sequences.items()
        }

        # Calculate approval/rejection rates
        total_entries = len(entries)
        confirmations = sum(1 for e in entries if e.get("status") == "confirmed")
        rejections = sum(1 for e in entries if e.get("status") == "cancelled")
        approval_rate = confirmations / total_entries if total_entries > 0 else 0.0
        rejection_rate = rejections / total_entries if total_entries > 0 else 0.0

        # Overall success rate
        success_rate = sum(p.success_rate for p in patterns.values()) / len(patterns) if patterns else 0.0

        # Find most frequent actions
        most_frequent = sorted(
            [(k, v.frequency) for k, v in patterns.items()],
            key=lambda x: x[1],
            reverse=True,
        )

        # Identify preferred workflow (most frequent action kind)
        preferred_workflow = most_frequent[0][0] if most_frequent else None

        profile = UserExecutionProfile(
            total_actions=total_entries,
            action_patterns=patterns,
            most_frequent_actions=most_frequent,
            action_sequences=sequences_list,
            approval_rate=approval_rate,
            rejection_rate=rejection_rate,
            success_rate=success_rate,
            preferred_workflow=preferred_workflow,
            learning_data_points=total_entries,
        )

        self._cache_profile = profile
        return profile

    def get_adaptive_threshold(self, action_kind: str, base_threshold: float = 0.5) -> float:
        """Get adaptive confirmation threshold for an action type.

        Higher threshold = harder to auto-approve (more user confirmations needed).
        Lower threshold = easier to auto-approve (trusted action).

        Args:
            action_kind: Type of action to get threshold for
            base_threshold: Default threshold (0-1)

        Returns:
            Adaptive threshold (0-1) based on:
            - Success rate (high success = lower threshold)
            - Frequency (common actions = lower threshold)
            - Confidence (high confidence = lower threshold)
        """
        patterns = self.analyze_audit_history()

        if action_kind not in patterns:
            return base_threshold

        pattern = patterns[action_kind]

        # Factors that reduce threshold (make action easier to approve):
        # 1. High success rate (user's actions usually work)
        # 2. Frequent action (user does this often)
        # 3. High confidence from data points

        success_factor = pattern.success_rate  # 0-1
        frequency_factor = min(pattern.frequency / 50.0, 1.0)  # normalize by typical frequency
        confidence_factor = pattern.confidence_level  # 0-1

        # Combined factor: 0-1, higher = more trustworthy
        trust_factor = (success_factor + frequency_factor + confidence_factor) / 3.0

        # Adjust threshold: reduce for trusted actions, increase for risky ones
        # Formula: base * (1.5 - trust_factor)
        # - High trust (1.0) -> 0.5 * base (easy to approve)
        # - Low trust (0.0) -> 1.5 * base (hard to approve)
        adjusted_threshold = base_threshold * (1.5 - trust_factor)

        return max(0.1, min(adjusted_threshold, 0.9))  # clamp to 0.1-0.9

    def should_auto_approve(self, action_kind: str, user_approval_rate: float = 0.9) -> bool:
        """Determine if action should be auto-approved based on trust.

        Auto-approve if:
        - User approval rate is very high (>= threshold)
        - Action success rate is very high (>= 0.95)
        - User has done this action many times (>= 20)

        Args:
            action_kind: Type of action to check
            user_approval_rate: User's typical approval rate (0-1)

        Returns:
            True if action is trusted enough to auto-approve
        """
        patterns = self.analyze_audit_history()

        if action_kind not in patterns:
            return False

        pattern = patterns[action_kind]

        # Conditions for auto-approval
        has_high_success_rate = pattern.success_rate >= 0.95
        has_high_frequency = pattern.frequency >= 20
        user_very_trusting = user_approval_rate >= 0.95

        return has_high_success_rate and has_high_frequency and user_very_trusting

    def suggest_next_action(self, last_action: str) -> Optional[ContextualSuggestion]:
        """Suggest next action based on typical sequences.

        Args:
            last_action: The action that was just executed

        Returns:
            Suggestion for next action, or None if no pattern found
        """
        profile = self.build_user_profile()

        if last_action not in profile.action_sequences:
            return None

        # Get most common next action
        next_actions = profile.action_sequences[last_action]
        if not next_actions:
            return None

        most_common_action, count = next_actions[0]
        total_after_last = sum(c for _, c in next_actions)

        # Confidence is how consistently user does this action after the last one
        confidence = count / total_after_last if total_after_last > 0 else 0.0

        if confidence < 0.3:  # Only suggest if > 30% probability
            return None

        # Get pattern for suggested action to determine auto-approve threshold
        pattern = profile.action_patterns.get(most_common_action)
        auto_approve_threshold = pattern.success_rate if pattern else 0.8

        return ContextualSuggestion(
            action=most_common_action,
            action_kind=most_common_action,
            confidence=confidence,
            reason=f"You usually do '{most_common_action}' after '{last_action}' ({int(count)}/{total_after_last} times)",
            auto_approve_threshold=auto_approve_threshold,
            context={
                "previous_action": last_action,
                "frequency": count,
                "total_sequences": total_after_last,
            },
        )

    def get_learning_statistics(self) -> dict[str, Any]:
        """Get summary statistics about learning state."""
        profile = self.build_user_profile()

        return {
            "total_actions_analyzed": profile.learning_data_points,
            "unique_action_types": len(profile.action_patterns),
            "overall_success_rate": profile.success_rate,
            "overall_approval_rate": profile.approval_rate,
            "most_frequent_action": profile.preferred_workflow,
            "num_action_patterns": len(profile.action_patterns),
            "has_sequence_data": len(profile.action_sequences) > 0,
        }

    def clear_cache(self) -> None:
        """Clear cached profile and patterns."""
        self._cache_profile = None
        self._cache_patterns = None


def _extract_times_of_day(timestamps: list[str]) -> dict[str, int]:
    """Extract time-of-day preferences from timestamps.

    Returns:
        Counter of time-of-day preferences (morning, afternoon, evening)
    """
    times = Counter()

    for ts_str in timestamps:
        if not ts_str or not isinstance(ts_str, str):
            continue

        try:
            # Parse ISO format: "2026-08-03T14:30:00Z"
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            hour = dt.hour

            if 5 <= hour < 12:
                times["morning"] += 1
            elif 12 <= hour < 17:
                times["afternoon"] += 1
            elif 17 <= hour < 21:
                times["evening"] += 1
            else:
                times["night"] += 1
        except (ValueError, AttributeError):
            continue

    return dict(times)
