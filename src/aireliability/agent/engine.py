"""Advanced Agent Reliability Engine for Phase 40.

Orchestrates the complete 15-stage agent reliability lifecycle:
TASK ANALYSIS -> DECOMPOSITION -> PLANNING -> TOOL SELECTION -> TOOL ARGUMENTS ->
TOOL EXECUTION -> OBSERVATION -> STATE UPDATE -> MEMORY UPDATE -> REASONING / REPLANNING ->
LOOPS & RETRIES -> RUNAWAY -> MULTI-AGENT -> GOAL VERIFICATION -> RELIABILITY SCORING.

Evaluates execution strictly as a trajectory, ensuring that successful final
answers never mask intermediate trajectory defects.
"""

from __future__ import annotations

import logging

from aireliability.agent.decomposition_analyzer import TaskDecompositionAnalyzer
from aireliability.agent.goal_verifier import GoalVerifier
from aireliability.agent.loop_detector import LoopDetector
from aireliability.agent.memory_analyzer import MemoryAnalyzer
from aireliability.agent.models import (
    AgentEvaluationResult,
    AgentFailure,
    AgentRun,
    AgentStage,
    AgentStageScore,
    Goal,
)
from aireliability.agent.multiagent_analyzer import MultiAgentAnalyzer
from aireliability.agent.observation_evaluator import ObservationEvaluator
from aireliability.agent.plan_evaluator import PlanEvaluator
from aireliability.agent.retry_analyzer import RetryAnalyzer
from aireliability.agent.runaway_detector import RunawayDetector
from aireliability.agent.state_tracker import StateTracker
from aireliability.agent.task_analyzer import TaskAnalyzer
from aireliability.agent.taxonomy import AgentReliabilityScorer
from aireliability.agent.tool_evaluator import ToolEvaluator
from aireliability.core.models import FailureSeverity

logger = logging.getLogger(__name__)


class AdvancedAgentReliabilityEngine:
    """Production-grade engine for evaluating, diagnosing, and auditing AI agent trajectories."""

    def __init__(
        self,
        task_analyzer: TaskAnalyzer | None = None,
        decomposition_analyzer: TaskDecompositionAnalyzer | None = None,
        plan_evaluator: PlanEvaluator | None = None,
        tool_evaluator: ToolEvaluator | None = None,
        observation_evaluator: ObservationEvaluator | None = None,
        state_tracker: StateTracker | None = None,
        memory_analyzer: MemoryAnalyzer | None = None,
        retry_analyzer: RetryAnalyzer | None = None,
        loop_detector: LoopDetector | None = None,
        runaway_detector: RunawayDetector | None = None,
        multiagent_analyzer: MultiAgentAnalyzer | None = None,
        goal_verifier: GoalVerifier | None = None,
        scorer: AgentReliabilityScorer | None = None,
    ) -> None:
        self.task_analyzer = task_analyzer or TaskAnalyzer()
        self.decomposition_analyzer = (
            decomposition_analyzer or TaskDecompositionAnalyzer()
        )
        self.plan_evaluator = plan_evaluator or PlanEvaluator()
        self.tool_evaluator = tool_evaluator or ToolEvaluator()
        self.observation_evaluator = observation_evaluator or ObservationEvaluator()
        self.state_tracker = state_tracker or StateTracker()
        self.memory_analyzer = memory_analyzer or MemoryAnalyzer()
        self.retry_analyzer = retry_analyzer or RetryAnalyzer()
        self.loop_detector = loop_detector or LoopDetector()
        self.runaway_detector = runaway_detector or RunawayDetector()
        self.multiagent_analyzer = multiagent_analyzer or MultiAgentAnalyzer()
        self.goal_verifier = goal_verifier or GoalVerifier()
        self.scorer = scorer or AgentReliabilityScorer()

    def evaluate_run(
        self,
        run: AgentRun,
        expected_tool_capabilities: dict[str, list[str]] | None = None,
        ground_truth_tools: dict[int, str] | None = None,
    ) -> AgentRun:
        """Execute comprehensive trajectory-aware audit on a single AgentRun."""
        all_failures: list[AgentFailure] = list(run.failures)
        stage_scores: dict[str, AgentStageScore] = {}

        # 1. TASK UNDERSTANDING & ANALYSIS
        task, task_fails, task_score = self.task_analyzer.analyze_task(
            request_text=run.task.request_text,
            expected_constraints=run.task.constraints,
            expected_goals=[g.description for g in run.task.goals],
        )
        all_failures.extend(task_fails)
        stage_scores[AgentStage.TASK_ANALYSIS.value] = task_score

        # 2. TASK DECOMPOSITION & PLANNING
        if run.plan is not None:
            _is_valid, decomp_fails, decomp_score = (
                self.decomposition_analyzer.analyze_decomposition(
                    subtasks=run.plan.steps,
                    dependencies=run.plan.dependencies,
                )
            )
            all_failures.extend(decomp_fails)
            stage_scores[AgentStage.DECOMPOSITION.value] = decomp_score

            _plan_obj, plan_fails, plan_score = self.plan_evaluator.evaluate_plan(
                plan=run.plan,
                available_tools=run.tools,
            )
            all_failures.extend(plan_fails)
            stage_scores[AgentStage.PLANNING.value] = plan_score

            # Compare intended plan vs actual trajectory
            dev_type, dev_fails, _dev_details = (
                self.plan_evaluator.compare_plan_vs_trajectory(
                    plan=run.plan,
                    trajectory=run.trajectory,
                )
            )
            all_failures.extend(dev_fails)

        # 3. TOOL SELECTION, ARGUMENTS, AND EXECUTION
        tool_fails, tsel_score, targ_score, texec_score = (
            self.tool_evaluator.evaluate_trajectory_tools(
                steps=run.trajectory.steps,
                available_tools=run.tools,
                expected_capabilities=expected_tool_capabilities,
                ground_truth_tools=ground_truth_tools,
            )
        )
        all_failures.extend(tool_fails)
        stage_scores[AgentStage.TOOL_SELECTION.value] = tsel_score
        stage_scores[AgentStage.TOOL_ARGUMENTS.value] = targ_score
        stage_scores[AgentStage.TOOL_EXECUTION.value] = texec_score

        # 4. OBSERVATION & TOOL RESULTS
        obs_failures: list[AgentFailure] = []
        for step in run.trajectory.steps:
            if step.observation is not None or step.tool_result is not None:
                step_obs = step.observation
                if step_obs is not None:
                    step_fails, _ = self.observation_evaluator.evaluate_observation(
                        observation=step_obs,
                        tool_result=step.tool_result,
                        step_index=step.sequence,
                    )
                    obs_failures.extend(step_fails)
                elif step.tool_result is not None:
                    res_fails = self.observation_evaluator.validate_tool_result(
                        result=step.tool_result,
                        step_index=step.sequence,
                    )
                    obs_failures.extend(res_fails)

        all_failures.extend(obs_failures)
        obs_score_val = max(0.0, 1.0 - (0.25 * len(obs_failures)))
        stage_scores[AgentStage.OBSERVATION.value] = AgentStageScore(
            stage=AgentStage.OBSERVATION,
            score=obs_score_val,
            confidence=0.92,
            metrics={"observation_failures": float(len(obs_failures))},
            failures=obs_failures,
            explanation=f"{len(obs_failures)} observation defects detected"
            if obs_failures
            else "Observations verified",
        )

        # 5. STATE TRANSITIONS
        state_fails, state_score = self.state_tracker.evaluate_trajectory_states(
            run.trajectory.steps
        )
        all_failures.extend(state_fails)
        stage_scores[AgentStage.STATE.value] = state_score

        # 6. MEMORY OPERATIONS
        if run.memory_events:
            mem_fails, mem_score = self.memory_analyzer.analyze_memory_events(
                run.memory_events
            )
            all_failures.extend(mem_fails)
            stage_scores[AgentStage.MEMORY.value] = mem_score

        # 7. LOOPS & RETRIES
        loop_class, loop_fails, loop_score = self.loop_detector.detect_loops(
            run.trajectory.steps
        )
        all_failures.extend(loop_fails)
        stage_scores[AgentStage.LOOP.value] = loop_score

        retry_fails, retry_score = self.retry_analyzer.analyze_retries(
            run.trajectory.steps
        )
        all_failures.extend(retry_fails)
        stage_scores[AgentStage.RETRY.value] = retry_score

        # 8. RUNAWAY & RESOURCE LIMITS
        runaway_fails, runaway_score = self.runaway_detector.evaluate_trajectory_limits(
            steps=run.trajectory.steps,
            total_cost=run.trajectory.total_cost,
            total_latency_seconds=run.trajectory.total_latency_seconds,
        )
        all_failures.extend(runaway_fails)
        stage_scores[AgentStage.RUNAWAY.value] = runaway_score

        # 9. MULTI-AGENT COORDINATION
        if run.handoffs:
            ma_fails, ma_score = self.multiagent_analyzer.evaluate_multiagent_system(
                run.handoffs
            )
            all_failures.extend(ma_fails)
            stage_scores[AgentStage.MULTI_AGENT.value] = ma_score

        # 10. GOAL VERIFICATION (Fundamental: Final Answer != Task Success)
        primary_goal = (
            run.task.goals[0]
            if run.task.goals
            else Goal(description=run.task.request_text)
        )
        goal_verification, goal_fails, goal_score = self.goal_verifier.verify_goal(
            goal=primary_goal,
            steps=run.trajectory.steps,
            final_response=run.final_response,
        )
        all_failures.extend(goal_fails)
        stage_scores[AgentStage.GOAL_VERIFICATION.value] = goal_score

        # 11. COMPOSITE RELIABILITY SCORING & RECOMMENDATIONS
        reliability_score = self.scorer.compute_composite_score(
            stage_scores, all_failures
        )
        recommendations = self.scorer.generate_recommendations(all_failures)

        # Build provenanced updated AgentRun
        provenance = dict(run.provenance)
        provenance["evaluated_by"] = "AdvancedAgentReliabilityEngine_v0.9.0"
        provenance["evaluation_stages"] = list(stage_scores.keys())

        return AgentRun(
            run_id=run.run_id,
            task=run.task,
            agent_id=run.agent_id,
            agent_version=run.agent_version,
            model=run.model,
            model_version=run.model_version,
            prompt_version=run.prompt_version,
            tools=run.tools,
            plan=run.plan,
            trajectory=run.trajectory,
            state=run.state,
            memory_events=run.memory_events,
            handoffs=run.handoffs,
            final_response=run.final_response,
            goal_verification=goal_verification,
            reliability_score=reliability_score,
            stage_scores=stage_scores,
            failures=all_failures,
            recommendations=recommendations,
            provenance=provenance,
            created_at=run.created_at,
            environment=run.environment,
            metadata=run.metadata,
        )

    def evaluate_runs(
        self,
        runs: list[AgentRun],
        min_release_score: float = 0.70,
    ) -> AgentEvaluationResult:
        """Batch evaluate multiple agent executions and compute aggregate metrics."""
        evaluated_runs: list[AgentRun] = []
        total_failures = 0
        critical_failures_count = 0
        stage_score_accum: dict[str, list[float]] = {}
        overall_scores: list[float] = []

        for r in runs:
            eval_run = self.evaluate_run(r)
            evaluated_runs.append(eval_run)
            total_failures += len(eval_run.failures)
            critical_failures_count += sum(
                1 for f in eval_run.failures if f.severity == FailureSeverity.CRITICAL
            )
            overall_scores.append(eval_run.reliability_score.overall_score)

            for st_name, st_score in eval_run.stage_scores.items():
                stage_score_accum.setdefault(st_name, []).append(st_score.score)

        mean_stage_scores = {
            k: round(sum(v) / len(v), 3) for k, v in stage_score_accum.items() if v
        }
        mean_overall = (
            round(sum(overall_scores) / len(overall_scores), 3)
            if overall_scores
            else 1.0
        )

        # Release gates pass only if mean score meets threshold and 0 critical failures
        passed_gates = (
            mean_overall >= min_release_score and critical_failures_count == 0
        )

        summary = (
            f"Evaluated {len(runs)} agent runs: Mean Score={mean_overall:.3f}, "
            f"Total Failures={total_failures}, Critical={critical_failures_count}, "
            f"Release Gates={'PASSED' if passed_gates else 'FAILED'}"
        )

        return AgentEvaluationResult(
            runs=evaluated_runs,
            mean_stage_scores=mean_stage_scores,
            overall_score=mean_overall,
            total_failures=total_failures,
            critical_failures_count=critical_failures_count,
            passed_release_gates=passed_gates,
            summary=summary,
        )
