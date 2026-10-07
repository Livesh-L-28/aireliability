"""CLI command handler for Phase 40 Advanced Agent Reliability Engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aireliability.agent.drift_detector import AgentDriftDetector
from aireliability.agent.engine import AdvancedAgentReliabilityEngine
from aireliability.agent.goal_verifier import GoalVerifier
from aireliability.agent.healing_bridge import AgentHealingBridge
from aireliability.agent.intelligence_bridge import AgentIntelligenceBridge
from aireliability.agent.loop_detector import LoopDetector
from aireliability.agent.memory_analyzer import MemoryAnalyzer
from aireliability.agent.models import (
    ActionType,
    AgentPlan,
    AgentRun,
    AgentStage,
    AgentStep,
    AgentTask,
    AgentTrajectory,
    Goal,
    GoalCriterion,
    Observation,
    ToolCall,
    ToolResult,
)
from aireliability.agent.multiagent_analyzer import MultiAgentAnalyzer
from aireliability.agent.optimization_bridge import AgentOptimizationBridge
from aireliability.agent.plan_evaluator import PlanEvaluator
from aireliability.agent.retry_analyzer import RetryAnalyzer
from aireliability.agent.serialization import AgentSerializer
from aireliability.agent.state_tracker import StateTracker
from aireliability.agent.task_analyzer import TaskAnalyzer
from aireliability.agent.test_bridge import AgentTestBridge
from aireliability.agent.tool_evaluator import ToolEvaluator


def build_sample_agent_run(args: argparse.Namespace) -> AgentRun:
    """Build a deterministic baseline AgentRun for CLI demonstrations."""
    req_text = (
        getattr(args, "task", None)
        or "Retrieve customer account balance and verify transaction history"
    )
    goal = Goal(
        goal_id="g1",
        description="Verify customer balance and transactions",
        criteria=[
            GoalCriterion(description="account balance retrieved", is_mandatory=True),
            GoalCriterion(description="transaction list confirmed", is_mandatory=False),
        ],
    )
    task = AgentTask(
        task_id="task_sample",
        request_text=req_text,
        goals=[goal],
        constraints=["read-only"],
        expected_outputs=["account_balance", "transactions"],
    )
    plan = AgentPlan(
        plan_id="plan_sample",
        steps=["lookup_account", "fetch_transactions", "verify_balance"],
        dependencies={
            "fetch_transactions": ["lookup_account"],
            "verify_balance": ["fetch_transactions"],
        },
    )
    step1 = AgentStep(
        sequence=1,
        stage=AgentStage.TOOL_EXECUTION,
        action="lookup_account",
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(
            tool_name="account_api",
            arguments={"account_id": "acc_123"},
        ),
        tool_result=ToolResult(
            call_id="c1",
            tool_name="account_api",
            output={"balance": 500.0, "status": "active"},
            success=True,
            latency_seconds=0.25,
            cost=0.002,
        ),
        observation=Observation(
            interpreted_content="Account acc_123 is active with balance 500.0",
        ),
        latency_seconds=0.25,
        cost=0.002,
    )
    step2 = AgentStep(
        sequence=2,
        stage=AgentStage.TOOL_EXECUTION,
        action="fetch_transactions",
        action_type=ActionType.TOOL_CALL,
        tool_call=ToolCall(
            tool_name="transaction_api",
            arguments={"account_id": "acc_123"},
        ),
        tool_result=ToolResult(
            call_id="c2",
            tool_name="transaction_api",
            output={"transactions": [{"id": "tx_1", "amount": 100.0}]},
            success=True,
            latency_seconds=0.30,
            cost=0.003,
        ),
        observation=Observation(
            interpreted_content="Retrieved 1 transaction totaling $100.0",
        ),
        latency_seconds=0.30,
        cost=0.003,
    )
    trajectory = AgentTrajectory(
        steps=[step1, step2],
        total_steps=2,
        total_cost=0.005,
        total_latency_seconds=0.55,
    )
    return AgentRun(
        run_id="run_sample_cli",
        task=task,
        agent_id=getattr(args, "agent", "finance_agent") or "finance_agent",
        agent_version=getattr(args, "agent_version", "1.0.0") or "1.0.0",
        model=getattr(args, "model", "agent-llm") or "agent-llm",
        tools=["account_api", "transaction_api"],
        plan=plan,
        trajectory=trajectory,
        final_response="Customer account balance is $500.0 with 1 confirmed transaction.",
    )


def resolve_agent_run(file_path_str: str | None, args: argparse.Namespace) -> AgentRun:
    """Resolve an AgentRun from a file path or synthesize a sample run."""
    if not file_path_str:
        run_arg = getattr(args, "run", None)
        if run_arg:
            file_path_str = run_arg

    if not file_path_str:
        return build_sample_agent_run(args)

    p = Path(file_path_str)
    if not p.exists():
        raise FileNotFoundError(f"Agent run file '{file_path_str}' not found.")
    content = p.read_text(encoding="utf-8")
    try:
        return AgentSerializer.from_json(content, AgentRun)
    except Exception:
        data = json.loads(content)
        return AgentRun.model_validate(data)


def handle_agent_cli(args: argparse.Namespace) -> int:
    """Execute AI agent reliability workflows for the airel CLI."""
    action = getattr(args, "agent_action", "evaluate") or "evaluate"
    engine = AdvancedAgentReliabilityEngine()
    is_json = getattr(args, "json", False)

    try:
        run_file = getattr(args, "file", None) or getattr(args, "run", None)
        run = resolve_agent_run(run_file, args)
    except Exception as e:
        if is_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error loading agent run: {e}", file=sys.stderr)
        return 1

    # 1. EVALUATE
    if action == "evaluate":
        eval_run = engine.evaluate_run(run)
        if is_json:
            print(eval_run.model_dump_json(indent=2))
        else:
            rel = eval_run.reliability_score
            print("\n=======================================================")
            print("  ADVANCED AGENT RELIABILITY EVALUATION (PHASE 40)")
            print("=======================================================")
            print(f"Run ID:            {eval_run.run_id}")
            print(f"Agent ID:          {eval_run.agent_id} (v{eval_run.agent_version})")
            print(f"Overall Score:     {rel.overall_score:.3f}")
            print(
                f"Safety Passed:     {'YES' if rel.safety_passed else 'NO (HARD VETO)'}"
            )
            print(
                f"Security Passed:   {'YES' if rel.security_passed else 'NO (HARD VETO)'}"
            )
            print(f"Efficiency Score:  {rel.efficiency_score:.3f}")
            print(
                f"Goal Status:       {eval_run.goal_verification.overall_status.value}"
            )
            print(f"Total Failures:    {len(eval_run.failures)}")
            print("\nStage Scores:")
            for st, sc in eval_run.stage_scores.items():
                print(f"  - {st:<20} {sc.score:.2f} (failures: {len(sc.failures)})")
            if eval_run.failures:
                print("\nTop Failures:")
                for f in eval_run.failures[:3]:
                    print(f"  ! [{f.severity.value}] {f.stage.value}: {f.message}")
            if eval_run.recommendations:
                print("\nRecommendations:")
                for r in eval_run.recommendations[:2]:
                    print(f"  * {r.title}: {r.action}")
            print("=======================================================\n")
        return 0

    # 2. ANALYZE
    elif action == "analyze":
        task_analyzer = TaskAnalyzer()
        task, fails, score = task_analyzer.analyze_task(
            run.task.request_text,
            expected_constraints=run.task.constraints,
        )
        if is_json:
            print(
                json.dumps(
                    {
                        "request_text": task.request_text,
                        "extracted_objectives": task.extracted_objectives,
                        "constraints": task.constraints,
                        "ambiguity_score": task.ambiguity_score,
                        "completeness_score": task.completeness_score,
                        "failures_count": len(fails),
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- AGENT TASK UNDERSTANDING & AMBIGUITY ---")
            print(f"Request:           {task.request_text}")
            print(f"Ambiguity Score:   {task.ambiguity_score:.2f}")
            print(f"Completeness:      {task.completeness_score:.2f}")
            print(
                f"Objectives:        {', '.join(task.extracted_objectives) or 'None'}"
            )
            print(f"Constraints:       {', '.join(task.constraints) or 'None'}")
            print(f"Defects Detected:  {len(fails)}\n")
        return 0

    # 3. TRAJECTORY
    elif action == "trajectory":
        traj = run.trajectory
        if is_json:
            print(traj.model_dump_json(indent=2))
        else:
            print("\n--- AGENT EXECUTION TRAJECTORY ---")
            print(f"Total Steps:   {traj.total_steps}")
            print(f"Total Cost:    ${traj.total_cost:.4f}")
            print(f"Total Latency: {traj.total_latency_seconds:.2f}s")
            print("\nStep Sequence:")
            for s in traj.steps:
                tool_info = f" -> tool: {s.tool_call.tool_name}" if s.tool_call else ""
                print(
                    f"  Step {s.sequence}: [{s.action_type.value}] {s.action}{tool_info} ({s.latency_seconds:.2f}s)"
                )
            print()
        return 0

    # 4. PLAN
    elif action == "plan":
        plan_eval = PlanEvaluator()
        _p, fails, score = (
            plan_eval.evaluate_plan(run.plan, available_tools=run.tools)
            if run.plan
            else (None, [], None)
        )
        if is_json:
            print(
                json.dumps(
                    {
                        "plan": run.plan.model_dump(mode="json") if run.plan else None,
                        "score": score.score if score else 1.0,
                        "failures": [f.model_dump(mode="json") for f in fails],
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- AGENT PLANNING & DECOMPOSITION ---")
            if run.plan:
                print(f"Steps:             {', '.join(run.plan.steps)}")
                print(f"Dependencies:      {run.plan.dependencies}")
                print(f"Plan Feasibility:  {score.score if score else 1.0:.2f}")
                print(f"Plan Defects:      {len(fails)}\n")
            else:
                print("No formal plan declared in agent run.\n")
        return 0

    # 5. TOOLS
    elif action == "tools":
        tool_eval = ToolEvaluator()
        fails, tsel, targ, texec = tool_eval.evaluate_trajectory_tools(
            run.trajectory.steps, available_tools=run.tools
        )
        if is_json:
            print(
                json.dumps(
                    {
                        "tool_selection_score": tsel.score,
                        "tool_arguments_score": targ.score,
                        "tool_execution_score": texec.score,
                        "failures": [f.model_dump(mode="json") for f in fails],
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- TOOL RELIABILITY AUDIT ---")
            print(f"Tool Selection:    {tsel.score:.2f}")
            print(f"Tool Arguments:    {targ.score:.2f}")
            print(f"Tool Execution:    {texec.score:.2f}")
            print(f"Total Tool Defect: {len(fails)}\n")
        return 0

    # 6. LOOPS
    elif action == "loops":
        detector = LoopDetector()
        l_class, fails, score = detector.detect_loops(run.trajectory.steps)
        if is_json:
            print(
                json.dumps(
                    {
                        "classification": l_class.value,
                        "score": score.score,
                        "failures": [f.model_dump(mode="json") for f in fails],
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- TRAJECTORY LOOP & OSCILLATION DETECTION ---")
            print(f"Loop Classification: {l_class.value}")
            print(f"Loop Score:          {score.score:.2f}")
            print(f"Loop Failures:       {len(fails)}\n")
        return 0

    # 7. RETRIES
    elif action == "retries":
        retry_analyzer = RetryAnalyzer()
        fails, score = retry_analyzer.analyze_retries(run.trajectory.steps)
        if is_json:
            print(
                json.dumps(
                    {
                        "metrics": score.metrics,
                        "score": score.score,
                        "failures": [f.model_dump(mode="json") for f in fails],
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- RETRY EFFICACY & STORM AUDIT ---")
            print(f"Retry Score:         {score.score:.2f}")
            print(f"Metrics:             {score.metrics}")
            print(f"Retry Anomalies:     {len(fails)}\n")
        return 0

    # 8. MEMORY
    elif action == "memory":
        mem_analyzer = MemoryAnalyzer()
        fails, score = mem_analyzer.analyze_memory_events(run.memory_events)
        if is_json:
            print(
                json.dumps(
                    {
                        "memory_score": score.score,
                        "events_count": len(run.memory_events),
                        "failures": [f.model_dump(mode="json") for f in fails],
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- AGENT MEMORY AUDIT ---")
            print(f"Memory Events:       {len(run.memory_events)}")
            print(f"Memory Reliability:  {score.score:.2f}")
            print(f"Memory Defects:      {len(fails)}\n")
        return 0

    # 9. STATE
    elif action == "state":
        state_tracker = StateTracker()
        fails, score = state_tracker.evaluate_trajectory_states(run.trajectory.steps)
        if is_json:
            print(
                json.dumps(
                    {
                        "state_score": score.score,
                        "failures": [f.model_dump(mode="json") for f in fails],
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- AGENT STATE TRANSITIONS AUDIT ---")
            print(f"State Consistency:   {score.score:.2f}")
            print(f"State Anomalies:     {len(fails)}\n")
        return 0

    # 10. GOALS
    elif action == "goals":
        goal_verifier = GoalVerifier()
        primary_goal = (
            run.task.goals[0]
            if run.task.goals
            else Goal(description=run.task.request_text)
        )
        verif, fails, score = goal_verifier.verify_goal(
            primary_goal, run.trajectory.steps, run.final_response
        )
        if is_json:
            print(verif.model_dump_json(indent=2))
        else:
            print("\n--- INDEPENDENT GOAL VERIFICATION ---")
            print(f"Goal Status:         {verif.overall_status.value}")
            print(f"Completion Ratio:    {verif.completion_ratio:.1%}")
            print("Criteria Results:")
            for c in verif.criteria_results:
                print(f"  [{c.status.value}] {c.description} (evidence: {c.evidence})")
            print()
        return 0

    # 11. HANDOFFS
    elif action == "handoffs":
        ma_analyzer = MultiAgentAnalyzer()
        fails, score = ma_analyzer.evaluate_multiagent_system(run.handoffs)
        if is_json:
            print(
                json.dumps(
                    {
                        "handoff_count": len(run.handoffs),
                        "coordination_score": score.score,
                        "failures": [f.model_dump(mode="json") for f in fails],
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- MULTI-AGENT COORDINATION & HANDOFFS ---")
            print(f"Total Handoffs:      {len(run.handoffs)}")
            print(f"Coordination Score:  {score.score:.2f}")
            print(f"Handoff Failures:    {len(fails)}\n")
        return 0

    # 12. FAILURES
    elif action == "failures":
        eval_run = engine.evaluate_run(run)
        if is_json:
            print(
                json.dumps(
                    [f.model_dump(mode="json") for f in eval_run.failures], indent=2
                )
            )
        else:
            print(f"\n--- DIAGNOSED AGENT FAILURES ({len(eval_run.failures)}) ---")
            for f in eval_run.failures:
                print(
                    f"[{f.severity.value}] {f.stage.value} / {f.category.value}: {f.message}"
                )
            print()
        return 0

    # 13. DRIFT
    elif action == "drift":
        drift_detector = AgentDriftDetector()
        drift_results = drift_detector.evaluate_runs_drift([run], [run])
        if is_json:
            print(
                json.dumps([d.model_dump(mode="json") for d in drift_results], indent=2)
            )
        else:
            print("\n--- AGENT BEHAVIORAL DRIFT AUDIT ---")
            for d in drift_results:
                print(
                    f"  {d.drift_type:<25} shift={d.distance:.1%} detected={d.drift_detected} ({d.message})"
                )
            print()
        return 0

    # 14. SECURITY
    elif action == "security":
        eval_run = engine.evaluate_run(run)
        sec_fails = [f for f in eval_run.failures if f.stage == AgentStage.SECURITY]
        if is_json:
            print(
                json.dumps(
                    {
                        "security_passed": eval_run.reliability_score.security_passed,
                        "violations": [f.model_dump(mode="json") for f in sec_fails],
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- AGENT SECURITY AUDIT ---")
            print(
                f"Security Policy:     {'PASSED' if eval_run.reliability_score.security_passed else 'VIOLATED (HARD VETO)'}"
            )
            print(f"Violations:          {len(sec_fails)}")
            for f in sec_fails:
                print(f"  ! {f.category.value}: {f.message}")
            print()
        return 0

    # 15. REGRESSION
    elif action == "regression":
        eval_run = engine.evaluate_run(run)
        passed = (
            eval_run.reliability_score.safety_passed
            and eval_run.reliability_score.security_passed
            and eval_run.goal_verification.overall_status.value
            in ("completed", "partially_completed")
        )
        if is_json:
            print(
                json.dumps(
                    {
                        "regression_passed": passed,
                        "overall_score": eval_run.reliability_score.overall_score,
                        "failures": len(eval_run.failures),
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- AGENT TRAJECTORY REGRESSION CHECK ---")
            print(f"Status:              {'PASSED' if passed else 'FAILED'}")
            print(
                f"Overall Score:       {eval_run.reliability_score.overall_score:.3f}"
            )
            print(
                f"Critical Failures:   {sum(1 for f in eval_run.failures if f.severity.value == 'CRITICAL')}\n"
            )
        return 0

    # 16. DIAGNOSE
    elif action == "diagnose":
        eval_run = engine.evaluate_run(run)
        intel_bridge = AgentIntelligenceBridge()
        intel = intel_bridge.analyze_run_intelligence(eval_run)
        if is_json:
            print(
                json.dumps(
                    {
                        "clusters": len(intel.get("clusters", [])),
                        "patterns": len(intel.get("patterns", [])),
                        "recommendations": len(intel.get("recommendations", [])),
                        "summary": intel.get("summary", ""),
                    },
                    indent=2,
                )
            )
        else:
            print("\n--- AGENT ROOT CAUSE DIAGNOSIS (PHASE 34) ---")
            print(f"Summary:             {intel.get('summary')}")
            for c in intel.get("clusters", []):
                print(f"  Cluster: {c.name} (dominant cause: {c.dominant_root_cause})")
            print()
        return 0

    # 17. TESTS
    elif action == "tests":
        test_bridge = AgentTestBridge()
        test_result = test_bridge.generate_agent_tests(run, max_tests=3)
        if is_json:
            print(test_result.model_dump_json(indent=2))
        else:
            print("\n--- SYNTHESIZED AGENT TESTS (PHASE 36) ---")
            print(f"Generated Tests:     {len(test_result.test_cases)}")
            for tc in test_result.test_cases:
                print(f"  * {tc.test_id}: {tc.name} (strategy={tc.strategy.value})")
            print()
        return 0

    # 18. HEAL
    elif action == "heal":
        eval_run = engine.evaluate_run(run)
        healing_bridge = AgentHealingBridge()
        proposals = healing_bridge.propose_agent_remediations(
            eval_run.failures, eval_run
        )
        if is_json:
            print(json.dumps([p.model_dump(mode="json") for p in proposals], indent=2))
        else:
            print("\n--- AGENT SELF-HEALING PROPOSALS (PHASE 37) ---")
            print(f"Proposals Generated: {len(proposals)}")
            for p in proposals:
                print(f"  * [{p.risk_tier.value}] {p.proposal_id}: {p.description}")
            print()
        return 0

    # 19. OPTIMIZE
    elif action == "optimize":
        opt_bridge = AgentOptimizationBridge()
        problem = opt_bridge.create_agent_optimization_problem(agent_id=run.agent_id)
        if is_json:
            print(problem.model_dump_json(indent=2))
        else:
            print("\n--- AGENT PARETO OPTIMIZATION PROBLEM (PHASE 38) ---")
            print(f"Problem:             {problem.name}")
            print(f"Description:         {problem.description}")
            print(
                f"Objectives:          {', '.join(o.objective_id for o in problem.objectives)}"
            )
            print(
                f"Variables:           {', '.join(v.variable_id for v in problem.variables)}\n"
            )
        return 0

    # 20. REPORT
    elif action == "report":
        eval_run = engine.evaluate_run(run)
        fmt = getattr(args, "format", "terminal")
        out_arg = getattr(args, "output", None) or ""
        if fmt == "markdown" or out_arg.endswith(".md"):
            md = [
                f"# Agent Reliability Report: {eval_run.run_id}",
                f"- **Agent ID**: `{eval_run.agent_id}`",
                f"- **Overall Reliability**: **{eval_run.reliability_score.overall_score:.3f}**",
                f"- **Goal Status**: `{eval_run.goal_verification.overall_status.value}`",
                f"- **Safety/Security**: `{'PASS' if eval_run.reliability_score.safety_passed and eval_run.reliability_score.security_passed else 'FAIL'}`",
                "\n## Stage Scores",
            ]
            for st, sc in eval_run.stage_scores.items():
                md.append(f"- **{st}**: {sc.score:.2f}")
            out_str = "\n".join(md)
            if getattr(args, "output", None):
                Path(args.output).write_text(out_str, encoding="utf-8")
                print(f"Saved report to {args.output}")
            else:
                print(out_str)
        elif fmt == "json" or is_json:
            print(eval_run.model_dump_json(indent=2))
        else:
            # Terminal summary
            print(
                f"\nReport for Agent Run {eval_run.run_id}: Score={eval_run.reliability_score.overall_score:.3f}\n"
            )
        return 0

    # 21. INSPECT
    elif action == "inspect":
        if is_json:
            print(run.model_dump_json(indent=2))
        else:
            print("\n=======================================================")
            print(f"  AGENT RUN INSPECTOR: {run.run_id}")
            print("=======================================================")
            print(f"Task:              {run.task.request_text}")
            print(f"Agent / Model:     {run.agent_id} / {run.model}")
            print(f"Tools Registered:  {', '.join(run.tools)}")
            print(f"Trajectory Steps:  {run.trajectory.total_steps}")
            print(f"Final Response:    {run.final_response[:80]}...")
            print("=======================================================\n")
        return 0

    return 0
