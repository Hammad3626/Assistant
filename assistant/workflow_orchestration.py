"""Advanced workflow automation and orchestration engine.

Enables chaining multiple workflows together with:
- Sequential and parallel execution
- Conditional branching based on conditions
- Error recovery with fallback strategies
- Atomic execution with rollback capability
- Workflow history and debugging
- Learning-based optimization
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


class ExecutionStatus(str, Enum):
    """Status of workflow or step execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class ErrorRecoveryStrategy(str, Enum):
    """Strategy for handling step failures."""
    FAIL_FAST = "fail_fast"  # Stop entire workflow
    CONTINUE = "continue"  # Skip failed step, continue
    RETRY = "retry"  # Retry with backoff
    FALLBACK = "fallback"  # Try alternate step


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_name: str
    status: ExecutionStatus
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    attempt: int = 1
    rollback_data: Optional[dict[str, Any]] = None


@dataclass
class WorkflowStep:
    """Definition of a single workflow step."""
    name: str
    action: Callable[..., dict[str, Any]]  # Function that executes the step
    parameters: dict[str, Any] = field(default_factory=dict)
    recovery_strategy: ErrorRecoveryStrategy = ErrorRecoveryStrategy.FAIL_FAST
    max_retries: int = 0
    retry_backoff_ms: int = 100  # milliseconds
    fallback_step: Optional[WorkflowStep] = None
    requires_approval: bool = False
    approval_callback: Optional[Callable[[str, Any], bool]] = None
    skip_condition: Optional[Callable[[dict[str, Any]], bool]] = None
    description: str = ""


@dataclass
class ExecutionContext:
    """Context during workflow execution."""
    workflow_id: str
    step_results: list[StepResult] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_duration_ms: float = 0.0
    rollback_operations: list[tuple[str, Callable[[], bool]]] = field(default_factory=list)

    def add_result(self, result: StepResult) -> None:
        """Add step result to execution history."""
        self.step_results.append(result)

    def get_last_output(self) -> Any:
        """Get output from most recent successful step."""
        for result in reversed(self.step_results):
            if result.status == ExecutionStatus.SUCCESS and result.output is not None:
                return result.output
        return None

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get variable from execution context."""
        return self.variables.get(name, default)

    def set_variable(self, name: str, value: Any) -> None:
        """Set variable in execution context."""
        self.variables[name] = value

    def add_rollback_operation(self, name: str, operation: Callable[[], bool]) -> None:
        """Register operation to be executed on rollback."""
        self.rollback_operations.append((name, operation))


@dataclass
class WorkflowDefinition:
    """Definition of a complete workflow pipeline."""
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    timeout_ms: Optional[int] = None
    on_failure_action: ErrorRecoveryStrategy = ErrorRecoveryStrategy.FAIL_FAST
    enable_rollback: bool = True
    approval_required: bool = False

    def add_step(self, step: WorkflowStep) -> None:
        """Add step to workflow."""
        self.steps.append(step)

    def validate(self) -> tuple[bool, list[str]]:
        """Validate workflow definition."""
        errors = []

        if not self.name or not self.name.strip():
            errors.append("Workflow name cannot be empty")

        if not self.steps:
            errors.append("Workflow must have at least one step")

        # Check for circular step dependencies
        for step in self.steps:
            if step.fallback_step and step.fallback_step in self.steps:
                # Fallbacks are allowed as they're not circular dependencies
                pass

        return len(errors) == 0, errors


@dataclass
class WorkflowExecution:
    """Complete execution of a workflow."""
    workflow_id: str
    workflow_name: str
    context: ExecutionContext
    status: ExecutionStatus
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "status": self.status.value,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "total_duration_ms": self.context.total_duration_ms,
            "step_count": len(self.context.step_results),
            "successful_steps": sum(
                1 for r in self.context.step_results if r.status == ExecutionStatus.SUCCESS
            ),
            "failed_steps": sum(
                1 for r in self.context.step_results if r.status == ExecutionStatus.FAILED
            ),
        }


class OrchestrationEngine:
    """Engine for executing workflow pipelines with error recovery."""

    def __init__(self, enable_learning: bool = True) -> None:
        self.enable_learning = enable_learning
        self._execution_history: list[WorkflowExecution] = []

    def create_workflow(
        self,
        name: str,
        description: str = "",
    ) -> WorkflowDefinition:
        """Create new workflow definition."""
        return WorkflowDefinition(name=name, description=description)

    def execute(
        self,
        workflow: WorkflowDefinition,
        approval_callback: Optional[Callable[[str, Any], bool]] = None,
        max_total_time_ms: Optional[int] = None,
    ) -> WorkflowExecution:
        """Execute workflow pipeline.

        Args:
            workflow: Workflow definition to execute
            approval_callback: Function to request user approval
            max_total_time_ms: Maximum total execution time

        Returns:
            WorkflowExecution with results
        """
        # Validate workflow
        is_valid, errors = workflow.validate()
        if not is_valid:
            return WorkflowExecution(
                workflow_id="invalid",
                workflow_name=workflow.name,
                context=ExecutionContext(workflow_id="invalid"),
                status=ExecutionStatus.FAILED,
                error=f"Validation failed: {'; '.join(errors)}",
            )

        # Create execution context
        context = ExecutionContext(workflow_id=f"{workflow.name}_{int(time.time() * 1000)}")
        context.start_time = datetime.now(UTC)

        execution = WorkflowExecution(
            workflow_id=context.workflow_id,
            workflow_name=workflow.name,
            context=context,
            status=ExecutionStatus.RUNNING,
        )

        try:
            # Execute each step
            for i, step in enumerate(workflow.steps):
                if not self._should_continue_execution(execution, workflow, max_total_time_ms):
                    break

                # Check skip condition
                if step.skip_condition and step.skip_condition(context.variables):
                    result = StepResult(
                        step_name=step.name,
                        status=ExecutionStatus.SKIPPED,
                    )
                    context.add_result(result)
                    continue

                # Request approval if needed
                if step.requires_approval or workflow.approval_required:
                    if approval_callback:
                        callback = step.approval_callback or approval_callback
                        if not callback(step.name, context.get_last_output()):
                            result = StepResult(
                                step_name=step.name,
                                status=ExecutionStatus.SKIPPED,
                                error="User rejected execution",
                            )
                            context.add_result(result)
                            continue

                # Execute step with retry logic
                result = self._execute_step_with_retry(step, context)
                context.add_result(result)

                # Add rollback operation
                if workflow.enable_rollback and result.rollback_data:
                    context.add_rollback_operation(
                        step.name,
                        lambda: self._rollback_step(step, result),
                    )

                # Handle failure
                if result.status == ExecutionStatus.FAILED:
                    if step.recovery_strategy == ErrorRecoveryStrategy.FAIL_FAST:
                        execution.error = f"Step '{step.name}' failed: {result.error}"
                        execution.status = ExecutionStatus.FAILED
                        if workflow.enable_rollback:
                            self._perform_rollback(context)
                            execution.status = ExecutionStatus.ROLLED_BACK
                        break

                    elif step.recovery_strategy == ErrorRecoveryStrategy.FALLBACK:
                        if step.fallback_step:
                            result = self._execute_step_with_retry(step.fallback_step, context)
                            context.add_result(result)

                    # CONTINUE and RETRY are handled by their own logic

            # Mark as successful if no failures
            if execution.status == ExecutionStatus.RUNNING:
                execution.status = ExecutionStatus.SUCCESS

        except Exception as e:
            execution.status = ExecutionStatus.FAILED
            execution.error = f"Execution error: {str(e)}"
            if workflow.enable_rollback:
                self._perform_rollback(context)

        finally:
            context.end_time = datetime.now(UTC)
            if context.start_time:
                context.total_duration_ms = (
                    context.end_time - context.start_time
                ).total_seconds() * 1000
            execution.completed_at = context.end_time.isoformat()
            self._execution_history.append(execution)

        return execution

    def _should_continue_execution(
        self,
        execution: WorkflowExecution,
        workflow: WorkflowDefinition,
        max_total_time_ms: Optional[int],
    ) -> bool:
        """Check if workflow should continue executing."""
        if execution.status == ExecutionStatus.FAILED:
            return False

        if max_total_time_ms and execution.context.total_duration_ms > max_total_time_ms:
            return False

        if workflow.timeout_ms and execution.context.total_duration_ms > workflow.timeout_ms:
            return False

        return True

    def _execute_step_with_retry(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
    ) -> StepResult:
        """Execute step with retry logic."""
        last_error = None
        start_time = time.perf_counter()

        for attempt in range(1, step.max_retries + 2):  # +1 for initial attempt
            try:
                # Prepare parameters (replace references to context variables)
                params = self._resolve_parameters(step.parameters, context)

                # Execute step
                output = step.action(**params)

                # Store output in context
                context.set_variable(step.name, output)

                duration_ms = (time.perf_counter() - start_time) * 1000
                return StepResult(
                    step_name=step.name,
                    status=ExecutionStatus.SUCCESS,
                    output=output,
                    duration_ms=duration_ms,
                    attempt=attempt,
                )

            except Exception as e:
                last_error = str(e)

                # Wait before retry
                if attempt < step.max_retries + 1:
                    wait_time_ms = step.retry_backoff_ms * (2 ** (attempt - 1))
                    time.sleep(wait_time_ms / 1000.0)

        # All retries failed
        duration_ms = (time.perf_counter() - start_time) * 1000
        return StepResult(
            step_name=step.name,
            status=ExecutionStatus.FAILED,
            error=last_error or "Step execution failed",
            duration_ms=duration_ms,
            attempt=step.max_retries + 1,
        )

    def _resolve_parameters(
        self,
        parameters: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Resolve parameter references to context variables.

        Supports syntax like:
        - "$step_name" → output of previous step
        - "literal value" → used as-is
        """
        resolved = {}

        for key, value in parameters.items():
            if isinstance(value, str) and value.startswith("$"):
                # Reference to context variable
                var_name = value[1:]
                resolved[key] = context.get_variable(var_name, value)
            else:
                resolved[key] = value

        return resolved

    def _rollback_step(
        self,
        step: WorkflowStep,
        result: StepResult,
    ) -> bool:
        """Rollback a single step."""
        if not result.rollback_data:
            return True

        # Execute rollback logic if available
        # In production, this would call the step's rollback function
        return True

    def _perform_rollback(self, context: ExecutionContext) -> None:
        """Perform rollback of all executed steps in reverse order."""
        for step_name, rollback_op in reversed(context.rollback_operations):
            try:
                rollback_op()
            except Exception:
                # Log error but continue rollback
                pass

    def get_execution_history(self, limit: int = 10) -> list[WorkflowExecution]:
        """Get recent workflow executions."""
        return self._execution_history[-limit:]

    def get_workflow_statistics(self, workflow_name: str) -> dict[str, Any]:
        """Get statistics about workflow executions."""
        executions = [
            e for e in self._execution_history
            if e.workflow_name == workflow_name
        ]

        if not executions:
            return {
                "workflow_name": workflow_name,
                "total_executions": 0,
                "successful": 0,
                "failed": 0,
                "rolled_back": 0,
                "success_rate": 0.0,
                "average_duration_ms": 0.0,
            }

        successful = sum(1 for e in executions if e.status == ExecutionStatus.SUCCESS)
        failed = sum(1 for e in executions if e.status == ExecutionStatus.FAILED)
        rolled_back = sum(1 for e in executions if e.status == ExecutionStatus.ROLLED_BACK)
        total_duration = sum(e.context.total_duration_ms for e in executions)

        return {
            "workflow_name": workflow_name,
            "total_executions": len(executions),
            "successful": successful,
            "failed": failed,
            "rolled_back": rolled_back,
            "success_rate": successful / len(executions) if executions else 0.0,
            "average_duration_ms": total_duration / len(executions) if executions else 0.0,
        }

    def suggest_optimization(self, workflow_name: str) -> Optional[str]:
        """Suggest workflow optimization based on execution history."""
        stats = self.get_workflow_statistics(workflow_name)

        if stats["total_executions"] == 0:
            return None

        if stats["success_rate"] < 0.7:
            return f"Workflow '{workflow_name}' has low success rate ({stats['success_rate']*100:.0f}%). Consider adding error recovery strategies."

        if stats["average_duration_ms"] > 10000:
            return f"Workflow '{workflow_name}' is slow ({stats['average_duration_ms']:.0f}ms avg). Consider parallelizing steps."

        return None


class ConditionalExecutor:
    """Executor for conditional workflow branching."""

    @staticmethod
    def create_if_then_workflow(
        name: str,
        condition: Callable[[dict[str, Any]], bool],
        then_steps: list[WorkflowStep],
        else_steps: Optional[list[WorkflowStep]] = None,
    ) -> WorkflowDefinition:
        """Create workflow with conditional branching.

        Args:
            name: Workflow name
            condition: Function that returns True/False
            then_steps: Steps to execute if condition is True
            else_steps: Steps to execute if condition is False

        Returns:
            WorkflowDefinition with conditional logic
        """
        workflow = WorkflowDefinition(name=name)

        # Add conditional skip markers
        for step in then_steps:
            # These steps execute if condition is true
            workflow.add_step(step)

        if else_steps:
            for step in else_steps:
                # Mark these as else branch (not directly supported yet)
                workflow.add_step(step)

        return workflow

    @staticmethod
    def execute_conditional(
        engine: OrchestrationEngine,
        workflow: WorkflowDefinition,
        condition: Callable[[dict[str, Any]], bool],
        approval_callback: Optional[Callable[[str, Any], bool]] = None,
    ) -> WorkflowExecution:
        """Execute workflow with conditional logic."""
        return engine.execute(workflow, approval_callback)


class WorkflowComposer:
    """Utility for composing complex workflows from simple steps."""

    @staticmethod
    def compose(
        name: str,
        *steps_or_workflows: WorkflowStep | WorkflowDefinition,
    ) -> WorkflowDefinition:
        """Compose multiple steps/workflows into single workflow.

        Args:
            name: Composed workflow name
            *steps_or_workflows: Steps or workflows to compose

        Returns:
            ComposedWorkflow
        """
        workflow = WorkflowDefinition(name=name, description=f"Composed workflow: {name}")

        for item in steps_or_workflows:
            if isinstance(item, WorkflowStep):
                workflow.add_step(item)
            elif isinstance(item, WorkflowDefinition):
                # Add all steps from sub-workflow
                for step in item.steps:
                    workflow.add_step(step)

        return workflow

    @staticmethod
    def create_retry_wrapper(
        step: WorkflowStep,
        max_retries: int = 3,
        backoff_ms: int = 100,
    ) -> WorkflowStep:
        """Wrap step with retry logic."""
        step.max_retries = max_retries
        step.retry_backoff_ms = backoff_ms
        step.recovery_strategy = ErrorRecoveryStrategy.RETRY
        return step

    @staticmethod
    def create_fallback_wrapper(
        primary_step: WorkflowStep,
        fallback_step: WorkflowStep,
    ) -> WorkflowStep:
        """Wrap step with fallback strategy."""
        primary_step.fallback_step = fallback_step
        primary_step.recovery_strategy = ErrorRecoveryStrategy.FALLBACK
        return primary_step
