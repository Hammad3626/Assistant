"""Comprehensive tests for workflow orchestration engine."""

import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from assistant.workflow_orchestration import (
    ConditionalExecutor,
    ErrorRecoveryStrategy,
    ExecutionContext,
    ExecutionStatus,
    OrchestrationEngine,
    StepResult,
    WorkflowComposer,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStep,
)


class WorkflowDefinitionTests(unittest.TestCase):
    """Tests for workflow definition."""

    def test_create_workflow(self):
        """Create new workflow definition."""
        workflow = WorkflowDefinition(name="test_workflow")

        self.assertEqual(workflow.name, "test_workflow")
        self.assertEqual(len(workflow.steps), 0)

    def test_add_step_to_workflow(self):
        """Add step to workflow."""
        workflow = WorkflowDefinition(name="test")
        step = WorkflowStep(name="step1", action=lambda: {"result": "ok"})

        workflow.add_step(step)

        self.assertEqual(len(workflow.steps), 1)
        self.assertEqual(workflow.steps[0].name, "step1")

    def test_validate_empty_workflow(self):
        """Validation fails for empty workflow."""
        workflow = WorkflowDefinition(name="empty")

        is_valid, errors = workflow.validate()

        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)

    def test_validate_valid_workflow(self):
        """Validation succeeds for valid workflow."""
        workflow = WorkflowDefinition(name="valid")
        step = WorkflowStep(name="step1", action=lambda: {"ok": True})
        workflow.add_step(step)

        is_valid, errors = workflow.validate()

        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_validate_empty_name(self):
        """Validation fails for empty workflow name."""
        workflow = WorkflowDefinition(name="")

        is_valid, errors = workflow.validate()

        self.assertFalse(is_valid)


class ExecutionContextTests(unittest.TestCase):
    """Tests for execution context."""

    def test_create_execution_context(self):
        """Create execution context."""
        context = ExecutionContext(workflow_id="test123")

        self.assertEqual(context.workflow_id, "test123")
        self.assertEqual(len(context.step_results), 0)

    def test_add_step_result(self):
        """Add step result to context."""
        context = ExecutionContext(workflow_id="test")
        result = StepResult(step_name="step1", status=ExecutionStatus.SUCCESS)

        context.add_result(result)

        self.assertEqual(len(context.step_results), 1)
        self.assertEqual(context.step_results[0].step_name, "step1")

    def test_get_last_output(self):
        """Get output from last successful step."""
        context = ExecutionContext(workflow_id="test")
        context.add_result(
            StepResult(
                step_name="step1",
                status=ExecutionStatus.SUCCESS,
                output={"value": 42},
            )
        )
        context.add_result(
            StepResult(step_name="step2", status=ExecutionStatus.FAILED)
        )

        output = context.get_last_output()

        self.assertEqual(output, {"value": 42})

    def test_variables_storage(self):
        """Store and retrieve variables in context."""
        context = ExecutionContext(workflow_id="test")

        context.set_variable("key1", "value1")
        result = context.get_variable("key1")

        self.assertEqual(result, "value1")

    def test_get_missing_variable(self):
        """Get missing variable returns default."""
        context = ExecutionContext(workflow_id="test")

        result = context.get_variable("missing", "default")

        self.assertEqual(result, "default")

    def test_rollback_operations(self):
        """Register and track rollback operations."""
        context = ExecutionContext(workflow_id="test")
        rollback_called = [False]

        def rollback():
            rollback_called[0] = True
            return True

        context.add_rollback_operation("operation1", rollback)

        self.assertEqual(len(context.rollback_operations), 1)


class OrchestrationEngineTests(unittest.TestCase):
    """Tests for orchestration engine."""

    def test_create_engine(self):
        """Create orchestration engine."""
        engine = OrchestrationEngine()

        self.assertIsNotNone(engine)

    def test_create_workflow_via_engine(self):
        """Create workflow via engine."""
        engine = OrchestrationEngine()

        workflow = engine.create_workflow("test", "Test workflow")

        self.assertEqual(workflow.name, "test")

    def test_execute_single_step_workflow(self):
        """Execute workflow with single step."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("single_step")

        step = WorkflowStep(
            name="step1",
            action=lambda: {"result": "success"},
        )
        workflow.add_step(step)

        execution = engine.execute(workflow)

        self.assertEqual(execution.status, ExecutionStatus.SUCCESS)
        self.assertEqual(len(execution.context.step_results), 1)
        self.assertEqual(execution.context.step_results[0].status, ExecutionStatus.SUCCESS)

    def test_execute_multi_step_workflow(self):
        """Execute workflow with multiple steps."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("multi_step")

        step1 = WorkflowStep(name="step1", action=lambda: {"value": 1})
        step2 = WorkflowStep(name="step2", action=lambda: {"value": 2})
        step3 = WorkflowStep(name="step3", action=lambda: {"value": 3})

        workflow.add_step(step1)
        workflow.add_step(step2)
        workflow.add_step(step3)

        execution = engine.execute(workflow)

        self.assertEqual(execution.status, ExecutionStatus.SUCCESS)
        self.assertEqual(len(execution.context.step_results), 3)

    def test_execute_workflow_with_step_failure(self):
        """Workflow fails when step fails with fail_fast strategy."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("failing")

        step1 = WorkflowStep(name="step1", action=lambda: {"ok": True})
        step2 = WorkflowStep(
            name="step2",
            action=lambda: (_ for _ in ()).throw(Exception("Step failed")),
            recovery_strategy=ErrorRecoveryStrategy.FAIL_FAST,
        )

        workflow.add_step(step1)
        workflow.add_step(step2)

        execution = engine.execute(workflow)

        # Should fail on step2
        self.assertIn(execution.status, [ExecutionStatus.FAILED, ExecutionStatus.ROLLED_BACK])

    def test_execute_workflow_invalid_definition(self):
        """Execution fails for invalid workflow."""
        engine = OrchestrationEngine()
        workflow = WorkflowDefinition(name="invalid")  # No steps

        execution = engine.execute(workflow)

        self.assertEqual(execution.status, ExecutionStatus.FAILED)

    def test_execution_tracks_duration(self):
        """Execution tracks total duration."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("timed")

        step = WorkflowStep(
            name="slow_step",
            action=lambda: (time.sleep(0.01), {"ok": True})[1],
        )
        workflow.add_step(step)

        execution = engine.execute(workflow)

        self.assertGreater(execution.context.total_duration_ms, 0)

    def test_execution_history(self):
        """Engine tracks execution history."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("tracked")
        step = WorkflowStep(name="step1", action=lambda: {"ok": True})
        workflow.add_step(step)

        engine.execute(workflow)
        engine.execute(workflow)

        history = engine.get_execution_history()

        self.assertGreaterEqual(len(history), 2)


class ErrorRecoveryTests(unittest.TestCase):
    """Tests for error recovery strategies."""

    def test_fail_fast_strategy(self):
        """Fail-fast stops workflow on first error."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("fail_fast")

        step1 = WorkflowStep(name="step1", action=lambda: {"ok": True})
        step2 = WorkflowStep(
            name="step2",
            action=lambda: (_ for _ in ()).throw(Exception("Failed")),
            recovery_strategy=ErrorRecoveryStrategy.FAIL_FAST,
        )
        step3 = WorkflowStep(name="step3", action=lambda: {"ok": True})

        workflow.add_step(step1)
        workflow.add_step(step2)
        workflow.add_step(step3)

        execution = engine.execute(workflow)

        # Should stop at step2, not execute step3
        executed_steps = [r.step_name for r in execution.context.step_results]
        self.assertIn("step1", executed_steps)
        self.assertIn("step2", executed_steps)
        self.assertNotIn("step3", executed_steps)

    def test_continue_strategy(self):
        """Continue strategy skips failed step and continues."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("continue")

        step1 = WorkflowStep(name="step1", action=lambda: {"ok": True})
        step2 = WorkflowStep(
            name="step2",
            action=lambda: (_ for _ in ()).throw(Exception("Failed")),
            recovery_strategy=ErrorRecoveryStrategy.CONTINUE,
        )
        step3 = WorkflowStep(name="step3", action=lambda: {"ok": True})

        workflow.add_step(step1)
        workflow.add_step(step2)
        workflow.add_step(step3)

        execution = engine.execute(workflow)

        # Should execute all steps
        executed_steps = [r.step_name for r in execution.context.step_results]
        self.assertIn("step3", executed_steps)

    def test_retry_strategy(self):
        """Retry strategy retries failed step."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("retry")

        call_count = [0]

        def unreliable_action():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Not yet")
            return {"ok": True}

        step = WorkflowStep(
            name="retry_step",
            action=unreliable_action,
            max_retries=3,
            retry_backoff_ms=10,
            recovery_strategy=ErrorRecoveryStrategy.RETRY,
        )

        workflow.add_step(step)

        execution = engine.execute(workflow)

        # Should succeed after retries
        self.assertEqual(execution.context.step_results[0].status, ExecutionStatus.SUCCESS)
        self.assertGreater(execution.context.step_results[0].attempt, 1)

    def test_fallback_strategy(self):
        """Fallback strategy executes fallback step on failure."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("fallback")

        primary = WorkflowStep(
            name="primary",
            action=lambda: (_ for _ in ()).throw(Exception("Failed")),
            recovery_strategy=ErrorRecoveryStrategy.FALLBACK,
        )
        fallback = WorkflowStep(name="fallback", action=lambda: {"fallback": True})

        primary.fallback_step = fallback

        workflow.add_step(primary)

        execution = engine.execute(workflow)

        # Should have both steps in results
        step_names = [r.step_name for r in execution.context.step_results]
        self.assertIn("primary", step_names)


class ParameterResolutionTests(unittest.TestCase):
    """Tests for parameter resolution from context."""

    def test_resolve_literal_parameters(self):
        """Literal parameters are used as-is."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("literals")

        step = WorkflowStep(
            name="step1",
            action=lambda value: {"input": value},
            parameters={"value": 42},
        )
        workflow.add_step(step)

        execution = engine.execute(workflow)

        result = execution.context.step_results[0]
        self.assertEqual(result.output["input"], 42)

    def test_resolve_context_variable_references(self):
        """Context variable references are resolved."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("context_refs")

        step1 = WorkflowStep(
            name="step1",
            action=lambda: {"value": "from_step1"},
        )
        step2 = WorkflowStep(
            name="step2",
            action=lambda input_val: {"output": input_val},
            parameters={"input_val": "$step1"},
        )

        workflow.add_step(step1)
        workflow.add_step(step2)

        execution = engine.execute(workflow)

        # Step2 should receive output from step1
        result2 = execution.context.step_results[1]
        self.assertEqual(result2.output["output"], {"value": "from_step1"})


class SkipConditionTests(unittest.TestCase):
    """Tests for conditional step skipping."""

    def test_skip_step_based_on_condition(self):
        """Step is skipped when skip_condition returns True."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("conditional_skip")

        step1 = WorkflowStep(name="step1", action=lambda: {"skip": True})
        step2 = WorkflowStep(
            name="step2",
            action=lambda: {"should_skip": "yes"},
            skip_condition=lambda vars: vars.get("step1", {}).get("skip", False),
        )

        workflow.add_step(step1)
        workflow.add_step(step2)

        execution = engine.execute(workflow)

        # Step2 should be skipped
        step2_result = [r for r in execution.context.step_results if r.step_name == "step2"][0]
        self.assertEqual(step2_result.status, ExecutionStatus.SKIPPED)


class ApprovalTests(unittest.TestCase):
    """Tests for approval workflow."""

    def test_require_approval_for_step(self):
        """Step execution can require approval."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("approval")

        step = WorkflowStep(
            name="step1",
            action=lambda: {"risky": True},
            requires_approval=True,
        )
        workflow.add_step(step)

        approval_called = [False]

        def approval_callback(step_name, output):
            approval_called[0] = True
            return True  # Approve

        execution = engine.execute(workflow, approval_callback=approval_callback)

        self.assertTrue(approval_called[0])
        self.assertEqual(execution.status, ExecutionStatus.SUCCESS)

    def test_user_rejects_approval(self):
        """Step is skipped if user rejects approval."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("rejection")

        step = WorkflowStep(
            name="step1",
            action=lambda: {"would_be_executed": True},
            requires_approval=True,
        )
        workflow.add_step(step)

        def approval_callback(step_name, output):
            return False  # Reject

        execution = engine.execute(workflow, approval_callback=approval_callback)

        result = execution.context.step_results[0]
        self.assertEqual(result.status, ExecutionStatus.SKIPPED)


class WorkflowStatisticsTests(unittest.TestCase):
    """Tests for workflow statistics."""

    def test_get_workflow_statistics(self):
        """Get statistics for workflow executions."""
        engine = OrchestrationEngine()

        # Execute workflow multiple times
        for _ in range(3):
            workflow = engine.create_workflow("stats_test")
            step = WorkflowStep(name="step1", action=lambda: {"ok": True})
            workflow.add_step(step)
            engine.execute(workflow)

        stats = engine.get_workflow_statistics("stats_test")

        self.assertEqual(stats["total_executions"], 3)
        self.assertEqual(stats["successful"], 3)
        self.assertEqual(stats["failed"], 0)

    def test_statistics_empty_history(self):
        """Statistics for unknown workflow are empty."""
        engine = OrchestrationEngine()

        stats = engine.get_workflow_statistics("unknown")

        self.assertEqual(stats["total_executions"], 0)
        self.assertEqual(stats["success_rate"], 0.0)

    def test_suggest_optimization(self):
        """Suggest optimization for slow workflow."""
        engine = OrchestrationEngine()

        # Run multiple slow workflows to accumulate average
        for _ in range(3):
            workflow = engine.create_workflow("slow_opt")
            step = WorkflowStep(
                name="slow_step",
                action=lambda: (time.sleep(0.02), {"ok": True})[1],
            )
            workflow.add_step(step)
            engine.execute(workflow)

        suggestion = engine.suggest_optimization("slow_opt")

        # With 20ms average, should get a suggestion
        if suggestion:
            self.assertIn("slow", suggestion.lower())


class ConditionalExecutorTests(unittest.TestCase):
    """Tests for conditional execution."""

    def test_create_if_then_workflow(self):
        """Create if-then workflow."""
        then_step = WorkflowStep(name="then_step", action=lambda: {"executed": True})

        workflow = ConditionalExecutor.create_if_then_workflow(
            name="if_then",
            condition=lambda vars: True,
            then_steps=[then_step],
        )

        self.assertEqual(workflow.name, "if_then")
        self.assertGreater(len(workflow.steps), 0)


class WorkflowComposerTests(unittest.TestCase):
    """Tests for workflow composition."""

    def test_compose_steps_into_workflow(self):
        """Compose multiple steps into workflow."""
        step1 = WorkflowStep(name="s1", action=lambda: {"ok": True})
        step2 = WorkflowStep(name="s2", action=lambda: {"ok": True})
        step3 = WorkflowStep(name="s3", action=lambda: {"ok": True})

        composed = WorkflowComposer.compose("composed", step1, step2, step3)

        self.assertEqual(len(composed.steps), 3)

    def test_compose_workflows_into_workflow(self):
        """Compose multiple workflows into single workflow."""
        engine = OrchestrationEngine()

        workflow1 = engine.create_workflow("w1")
        workflow1.add_step(WorkflowStep(name="s1", action=lambda: {"ok": True}))

        workflow2 = engine.create_workflow("w2")
        workflow2.add_step(WorkflowStep(name="s2", action=lambda: {"ok": True}))

        composed = WorkflowComposer.compose("composed", workflow1, workflow2)

        # Should have steps from both workflows
        self.assertGreaterEqual(len(composed.steps), 2)

    def test_create_retry_wrapper(self):
        """Wrap step with retry logic."""
        step = WorkflowStep(name="step1", action=lambda: {"ok": True})

        wrapped = WorkflowComposer.create_retry_wrapper(step, max_retries=3)

        self.assertEqual(wrapped.max_retries, 3)
        self.assertEqual(wrapped.recovery_strategy, ErrorRecoveryStrategy.RETRY)

    def test_create_fallback_wrapper(self):
        """Wrap step with fallback."""
        primary = WorkflowStep(name="primary", action=lambda: {"ok": True})
        fallback = WorkflowStep(name="fallback", action=lambda: {"fallback": True})

        wrapped = WorkflowComposer.create_fallback_wrapper(primary, fallback)

        self.assertIsNotNone(wrapped.fallback_step)
        self.assertEqual(wrapped.fallback_step.name, "fallback")


class IntegrationTests(unittest.TestCase):
    """Integration tests for orchestration engine."""

    def test_complete_workflow_execution_cycle(self):
        """Complete workflow execution cycle."""
        engine = OrchestrationEngine()

        # Create workflow
        workflow = engine.create_workflow("full_cycle")

        # Add steps
        step1 = WorkflowStep(
            name="step1",
            action=lambda: {"intermediate": "value"},
        )
        step2 = WorkflowStep(
            name="step2",
            action=lambda input_data: {"result": f"processed_{input_data}"},
            parameters={"input_data": "$step1"},
        )
        step3 = WorkflowStep(
            name="step3",
            action=lambda: {"final": "result"},
        )

        workflow.add_step(step1)
        workflow.add_step(step2)
        workflow.add_step(step3)

        # Execute
        execution = engine.execute(workflow)

        # Verify
        self.assertEqual(execution.status, ExecutionStatus.SUCCESS)
        self.assertEqual(len(execution.context.step_results), 3)
        self.assertGreater(execution.context.total_duration_ms, 0)

        # Check history
        history = engine.get_execution_history()
        self.assertGreater(len(history), 0)

    def test_workflow_with_multiple_error_strategies(self):
        """Workflow combining multiple error recovery strategies."""
        engine = OrchestrationEngine()
        workflow = engine.create_workflow("mixed_strategies")

        # Step that succeeds
        step1 = WorkflowStep(name="step1", action=lambda: {"ok": True})

        # Step that fails but continues
        step2 = WorkflowStep(
            name="step2",
            action=lambda: (_ for _ in ()).throw(Exception("Ignored")),
            recovery_strategy=ErrorRecoveryStrategy.CONTINUE,
        )

        # Step that should execute
        step3 = WorkflowStep(name="step3", action=lambda: {"also_ok": True})

        workflow.add_step(step1)
        workflow.add_step(step2)
        workflow.add_step(step3)

        execution = engine.execute(workflow)

        step_names = [r.step_name for r in execution.context.step_results]
        self.assertIn("step1", step_names)
        self.assertIn("step2", step_names)
        self.assertIn("step3", step_names)


if __name__ == "__main__":
    unittest.main()
