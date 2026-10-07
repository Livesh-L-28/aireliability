"""Benchmark suite for Agent evaluation lifecycle (Phase 40) across trajectory sizes and loop detection."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.agent.engine import AdvancedAgentReliabilityEngine
from aireliability.agent.goal_verifier import GoalVerifier
from aireliability.agent.loop_detector import LoopDetector
from aireliability.agent.memory_analyzer import MemoryAnalyzer
from aireliability.agent.models import (
    ActionType,
    AgentPlan,
    AgentRun,
    AgentStep,
    AgentTask,
    AgentTrajectory,
    Goal,
    GoalCriterion,
    GoalStatus,
    GoalVerification,
    Observation,
    ToolCall,
    ToolResult,
    ToolRiskLevel,
)
from aireliability.agent.observation_evaluator import ObservationEvaluator
from aireliability.agent.plan_evaluator import PlanEvaluator
from aireliability.agent.retry_analyzer import RetryAnalyzer
from aireliability.agent.state_tracker import StateTracker
from aireliability.agent.task_analyzer import TaskAnalyzer
from aireliability.agent.tool_evaluator import ToolEvaluator
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_agent_run(step_count: int = 5) -> AgentRun:
    """Construct an authentic synthetic AgentRun with specified step count."""
    tools = ["calculator", "knowledge_search", "document_lookup", "status_lookup"]
    steps: list[AgentStep] = []

    for i in range(step_count):
        tname = tools[i % len(tools)]
        tcall = ToolCall(
            tool_name=tname,
            arguments={"query": f"item_{i}", "val": i * 5},
            risk_level=ToolRiskLevel.LOW,
        )
        tresult = ToolResult(
            call_id=tcall.call_id,
            tool_name=tname,
            output={"result": f"Operation {i} verified."},
            success=True,
            latency_seconds=0.0015,
        )
        obs = Observation(
            source="tool",
            raw_data={"val": i * 5},
            interpreted_content=f"Observed success for {tname} with value {i * 5}.",
            is_safe=True,
        )
        steps.append(
            AgentStep(
                sequence=i + 1,
                action_type=ActionType.TOOL_CALL,
                action=f"Call {tname} for step {i + 1}",
                tool_call=tcall,
                tool_result=tresult,
                observation=obs,
            )
        )

    task = AgentTask(
        task_id=f"task_{step_count}_steps",
        request_text=f"Execute workflow with {step_count} verified actions.",
        constraints=["use_registered_tools_only"],
        goals=[
            Goal(
                goal_id="g_main",
                description="Complete required tool operations",
                criteria=[
                    GoalCriterion(
                        criterion_id="crit_1",
                        description="All tool calls return successful outcomes",
                        is_mandatory=True,
                    )
                ],
            )
        ],
    )
    plan = AgentPlan(
        plan_id=f"plan_{step_count}",
        task_id=task.task_id,
        steps=[f"Step {i + 1}" for i in range(step_count)],
        tools_required=tools,
    )
    traj = AgentTrajectory(
        trajectory_id=f"traj_{step_count}",
        task_id=task.task_id,
        steps=steps,
    )
    gver = GoalVerification(
        goal_id="g_main",
        overall_status=GoalStatus.COMPLETED,
        confidence=1.0,
    )

    return AgentRun(
        run_id=f"run_{step_count}",
        task=task,
        plan=plan,
        trajectory=traj,
        tools=tools,
        goal_verification=gver,
        final_response="All operations successfully completed.",
    )


def run_agent_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    engine = AdvancedAgentReliabilityEngine()

    run_5 = make_agent_run(5)
    run_10 = make_agent_run(10)
    run_50 = make_agent_run(50)
    run_100 = make_agent_run(100)

    # 1. Task Analysis
    ta = TaskAnalyzer()

    def bench_task_analysis() -> None:
        _ = ta.analyze_task(
            request_text=run_10.task.request_text,
            expected_constraints=run_10.task.constraints,
            expected_goals=[g.description for g in run_10.task.goals],
        )

    metrics.append(
        measure_benchmark(
            operation="agent_task_analysis",
            target_func=bench_task_analysis,
            input_size="1 task",
            iterations=config.iterations * 3,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 2. Plan Evaluation
    pe = PlanEvaluator()

    def bench_plan_eval() -> None:
        _ = pe.evaluate_plan(plan=run_10.plan, available_tools=run_10.tools)

    metrics.append(
        measure_benchmark(
            operation="agent_plan_evaluation",
            target_func=bench_plan_eval,
            input_size=f"{len(run_10.plan.steps)} steps",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 3. Tool Evaluation
    te = ToolEvaluator()

    def bench_tool_eval() -> None:
        _ = te.evaluate_trajectory_tools(
            steps=run_10.trajectory.steps,
            available_tools=run_10.tools,
        )

    metrics.append(
        measure_benchmark(
            operation="agent_tool_evaluation",
            target_func=bench_tool_eval,
            input_size=f"{len(run_10.trajectory.steps)} tool calls",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 4. Observation Evaluation
    oe = ObservationEvaluator()

    def bench_observation_eval() -> None:
        for s in run_10.trajectory.steps:
            if s.observation and s.tool_result:
                _ = oe.evaluate_observation(
                    observation=s.observation,
                    tool_result=s.tool_result,
                    step_index=s.sequence,
                )

    metrics.append(
        measure_benchmark(
            operation="agent_observation_evaluation",
            target_func=bench_observation_eval,
            input_size=f"{len(run_10.trajectory.steps)} observations",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 5. State Tracking
    st = StateTracker()

    def bench_state_tracking() -> None:
        for s in run_10.trajectory.steps:
            _ = st.evaluate_step_transition(step=s)

    metrics.append(
        measure_benchmark(
            operation="agent_state_tracking",
            target_func=bench_state_tracking,
            input_size=f"{len(run_10.trajectory.steps)} state transitions",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 6. Memory Analysis
    ma = MemoryAnalyzer()

    def bench_memory_analysis() -> None:
        _ = ma.analyze_memory_events(events=[])

    metrics.append(
        measure_benchmark(
            operation="agent_memory_analysis",
            target_func=bench_memory_analysis,
            input_size=f"{len(run_10.trajectory.steps)} memory steps",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 7. Loop Detection - 10 Steps
    ld = LoopDetector()

    def bench_loop_detection_10() -> None:
        _ = ld.detect_loops(steps=run_10.trajectory.steps)

    metrics.append(
        measure_benchmark(
            operation="agent_loop_detection_10_steps",
            target_func=bench_loop_detection_10,
            input_size="10 steps",
            iterations=config.iterations * 3,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 8. Loop Detection - 100 Steps (Complexity O(N) verification)
    def bench_loop_detection_100() -> None:
        _ = ld.detect_loops(steps=run_100.trajectory.steps)

    metrics.append(
        measure_benchmark(
            operation="agent_loop_detection_100_steps",
            target_func=bench_loop_detection_100,
            input_size="100 steps",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 9. Retry Analysis
    ra = RetryAnalyzer()

    def bench_retry_analysis() -> None:
        _ = ra.analyze_retries(steps=run_10.trajectory.steps)

    metrics.append(
        measure_benchmark(
            operation="agent_retry_analysis",
            target_func=bench_retry_analysis,
            input_size=f"{len(run_10.trajectory.steps)} steps",
            iterations=config.iterations * 3,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 10. Goal Verification
    gv = GoalVerifier()

    def bench_goal_verification() -> None:
        _ = gv.verify_goal(
            goal=run_10.task.goals[0],
            steps=run_10.trajectory.steps,
            final_response=run_10.final_response,
        )

    metrics.append(
        measure_benchmark(
            operation="agent_goal_verification",
            target_func=bench_goal_verification,
            input_size=f"{len(run_10.task.goals)} goals",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 11. Complete Trajectory Evaluation - 5 Steps
    def bench_eval_5() -> None:
        _ = engine.evaluate_run(run_5)

    metrics.append(
        measure_benchmark(
            operation="agent_complete_trajectory_5_steps",
            target_func=bench_eval_5,
            input_size="5 steps",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 12. Complete Trajectory Evaluation - 10 Steps
    def bench_eval_10() -> None:
        _ = engine.evaluate_run(run_10)

    metrics.append(
        measure_benchmark(
            operation="agent_complete_trajectory_10_steps",
            target_func=bench_eval_10,
            input_size="10 steps",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 13. Complete Trajectory Evaluation - 50 Steps
    def bench_eval_50() -> None:
        _ = engine.evaluate_run(run_50)

    metrics.append(
        measure_benchmark(
            operation="agent_complete_trajectory_50_steps",
            target_func=bench_eval_50,
            input_size="50 steps",
            iterations=max(3, config.iterations // 2),
            warmup_iterations=1,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    # 14. Complete Trajectory Evaluation - 100 Steps
    def bench_eval_100() -> None:
        _ = engine.evaluate_run(run_100)

    metrics.append(
        measure_benchmark(
            operation="agent_complete_trajectory_100_steps",
            target_func=bench_eval_100,
            input_size="100 steps",
            iterations=max(2, config.iterations // 3),
            warmup_iterations=1,
            budget=config.budgets.get("agent_evaluation"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_agent_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
