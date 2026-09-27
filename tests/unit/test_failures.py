"""Unit tests for Phase 6 failure taxonomy and deterministic failure analyzer."""

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
)
from aireliability.evaluation import (
    MaxCost,
    MaxLatency,
    OutputContains,
    OutputEquals,
    SchemaMatch,
    ToolArguments,
    ToolCalled,
    ToolNotCalled,
    ToolOrder,
)
from aireliability.failures import (
    FailureAnalyzer,
    FailureCategory,
    FailureTaxonomy,
    FailureType,
)


def test_failure_taxonomy_registration_and_lookup() -> None:
    """Verify FailureTaxonomy registry, lookups, and extensibility."""
    # Standard categories exist
    assert "task" in FailureTaxonomy.all_categories()
    assert "tool" in FailureTaxonomy.all_categories()
    assert "retrieval" in FailureTaxonomy.all_categories()
    assert "output" in FailureTaxonomy.all_categories()
    assert "safety" in FailureTaxonomy.all_categories()
    assert "performance" in FailureTaxonomy.all_categories()

    # Look up parent category
    assert FailureTaxonomy.get_category_for_type(FailureType.WRONG_TOOL) == "tool"
    assert FailureTaxonomy.get_category_for_type(FailureType.SCHEMA_ERROR) == "output"
    assert FailureTaxonomy.get_category_for_type(FailureType.LATENCY) == "performance"
    assert (
        FailureTaxonomy.get_category_for_type(FailureType.SAFETY_VIOLATION) == "safety"
    )
    assert (
        FailureTaxonomy.get_category_for_type(FailureType.MISSING_CONTEXT)
        == "retrieval"
    )
    assert FailureTaxonomy.get_category_for_type(FailureType.TASK_INCOMPLETE) == "task"

    # Extensibility: Register a new custom type under existing or new category
    FailureTaxonomy.register_type(FailureCategory.SAFETY, "prompt_injection")
    assert FailureTaxonomy.is_valid_type("prompt_injection")
    assert FailureTaxonomy.get_category_for_type("prompt_injection") == "safety"

    FailureTaxonomy.register_type("compliance", "gdpr_violation")
    assert "compliance" in FailureTaxonomy.all_categories()
    assert FailureTaxonomy.get_category_for_type("gdpr_violation") == "compliance"


def test_analyzer_maps_tool_called_failure() -> None:
    """Verify ToolCalled failure maps to TOOL / WRONG_TOOL with confidence 1.0."""
    analyzer = FailureAnalyzer()
    trace = ExecutionTrace(trace_id="tr_1", test_id="tc_1", steps=[])
    eval_res = ToolCalled("required_api").evaluate(trace)

    report = analyzer.analyze(trace, eval_res)
    assert isinstance(report, FailureReport)
    assert report.category == FailureCategory.TOOL.value
    assert report.type == FailureType.WRONG_TOOL.value
    assert report.confidence == 1.0
    assert report.severity == FailureSeverity.HIGH
    assert report.evidence["expected_tool"] == "required_api"
    assert report.trace_id == "tr_1"
    assert report.test_id == "tc_1"


def test_analyzer_maps_tool_not_called_failure() -> None:
    """Verify ToolNotCalled maps to TOOL / UNNECESSARY_TOOL with confidence 1.0."""
    from aireliability.core.models import StepType, TraceStep

    analyzer = FailureAnalyzer()
    step = TraceStep(name="format_disk", type=StepType.TOOL)
    trace = ExecutionTrace(trace_id="tr_2", steps=[step])
    eval_res = ToolNotCalled("format_disk").evaluate(trace)

    report = analyzer.analyze(trace, eval_res)
    assert report.category == FailureCategory.TOOL.value
    assert report.type == FailureType.UNNECESSARY_TOOL.value
    assert report.confidence == 1.0
    assert report.evidence["forbidden_tool"] == "format_disk"


def test_analyzer_maps_tool_order_failure() -> None:
    """Verify ToolOrder failure maps to TOOL / WRONG_ORDER with confidence 1.0."""
    from aireliability.core.models import StepType, TraceStep

    analyzer = FailureAnalyzer()
    step1 = TraceStep(name="refund", type=StepType.TOOL)
    step2 = TraceStep(name="cancel", type=StepType.TOOL)
    trace = ExecutionTrace(steps=[step1, step2])
    eval_res = ToolOrder(["cancel", "refund"]).evaluate(trace)

    report = analyzer.analyze(trace, eval_res)
    assert report.category == FailureCategory.TOOL.value
    assert report.type == FailureType.WRONG_ORDER.value
    assert report.confidence == 1.0
    assert "Expected tool order" in report.evidence["formatted_comparison"]


def test_analyzer_maps_tool_arguments_failure() -> None:
    """Verify ToolArguments maps to TOOL / WRONG_ARGUMENT with confidence 1.0."""
    from aireliability.core.models import StepType, TraceStep

    analyzer = FailureAnalyzer()
    step = TraceStep(name="query_user", type=StepType.TOOL, input={"user_id": 999})
    trace = ExecutionTrace(steps=[step])
    eval_res = ToolArguments("query_user", {"user_id": 123}).evaluate(trace)

    report = analyzer.analyze(trace, eval_res)
    assert report.category == FailureCategory.TOOL.value
    assert report.type == FailureType.WRONG_ARGUMENT.value
    assert report.confidence == 1.0


def test_analyzer_maps_output_schema_failure() -> None:
    """Verify SchemaMatch failure maps to OUTPUT / SCHEMA_ERROR with confidence 1.0."""
    from pydantic import BaseModel

    class StrictSchema(BaseModel):
        count: int

    analyzer = FailureAnalyzer()
    trace = ExecutionTrace(output={"count": "not_an_int"})
    eval_res = SchemaMatch(StrictSchema).evaluate(trace)

    report = analyzer.analyze(trace, eval_res)
    assert report.category == FailureCategory.OUTPUT.value
    assert report.type == FailureType.SCHEMA_ERROR.value
    assert report.confidence == 1.0
    assert report.evidence["schema"] == "StrictSchema"


def test_analyzer_maps_task_output_failures() -> None:
    """Verify OutputEquals and OutputContains map to TASK / TASK_INCORRECT."""
    analyzer = FailureAnalyzer()
    trace = ExecutionTrace(output="Hello world")

    res_eq = OutputEquals("Goodbye").evaluate(trace)
    rep_eq = analyzer.analyze(trace, res_eq)
    assert rep_eq.category == FailureCategory.TASK.value
    assert rep_eq.type == FailureType.TASK_INCORRECT.value
    assert rep_eq.confidence == 1.0

    res_cnt = OutputContains("missing_phrase").evaluate(trace)
    rep_cnt = analyzer.analyze(trace, res_cnt)
    assert rep_cnt.category == FailureCategory.TASK.value
    assert rep_cnt.type == FailureType.TASK_INCORRECT.value
    assert rep_cnt.confidence == 1.0


def test_analyzer_maps_performance_failures() -> None:
    """Verify MaxLatency and MaxCost map to PERFORMANCE / LATENCY and COST."""
    analyzer = FailureAnalyzer()

    # Latency
    trace_lat = ExecutionTrace(latency_ms=500.0)
    res_lat = MaxLatency(max_latency_ms=200.0).evaluate(trace_lat)
    rep_lat = analyzer.analyze(trace_lat, res_lat)
    assert rep_lat.category == FailureCategory.PERFORMANCE.value
    assert rep_lat.type == FailureType.LATENCY.value
    assert rep_lat.confidence == 1.0

    # Cost
    trace_cost = ExecutionTrace(cost=0.05)
    res_cost = MaxCost(max_cost=0.01).evaluate(trace_cost)
    rep_cost = analyzer.analyze(trace_cost, res_cost)
    assert rep_cost.category == FailureCategory.PERFORMANCE.value
    assert rep_cost.type == FailureType.COST.value
    assert rep_cost.confidence == 1.0


def test_analyzer_maps_safety_and_retrieval_categories() -> None:
    """Verify safety and retrieval evaluation assertions are mapped accordingly."""
    analyzer = FailureAnalyzer()
    trace = ExecutionTrace()

    # Safety
    safety_res = EvaluationResult(
        evaluator="SafetyPolicyCheck",
        passed=False,
        message="PII detected in output",
        evidence={"violation": "pii_ssn"},
    )
    rep_safety = analyzer.analyze(trace, safety_res)
    assert rep_safety.category == FailureCategory.SAFETY.value
    assert rep_safety.type == FailureType.SAFETY_VIOLATION.value
    assert rep_safety.severity == FailureSeverity.CRITICAL

    # Retrieval
    retrieval_res = EvaluationResult(
        evaluator="RetrievalContextEvaluator",
        passed=False,
        message="Relevant documents not returned",
        evidence={"query": "test query"},
    )
    rep_retrieval = analyzer.analyze(trace, retrieval_res)
    assert rep_retrieval.category == FailureCategory.RETRIEVAL.value
    assert rep_retrieval.type == FailureType.MISSING_CONTEXT.value


def test_hallucination_confidence_handling() -> None:
    """Verify hallucination without deterministic proof uses confidence < 1.0."""
    analyzer = FailureAnalyzer()
    trace = ExecutionTrace()

    heuristic_eval = EvaluationResult(
        evaluator="HallucinationEvaluator",
        passed=False,
        message="Output appears ungrounded",
        evidence={"deterministic": False},
    )
    report = analyzer.analyze(trace, heuristic_eval)
    assert report.category == FailureCategory.OUTPUT.value
    assert report.type == FailureType.HALLUCINATION.value
    assert report.confidence < 1.0  # Heuristic, not claimed deterministic

    # Deterministic proof
    proven_eval = EvaluationResult(
        evaluator="HallucinationEvaluator",
        passed=False,
        message="Ground truth direct contradiction detected",
        evidence={"deterministic": True},
    )
    rep_proven = analyzer.analyze(trace, proven_eval)
    assert rep_proven.confidence == 1.0


def test_custom_mapper_registration() -> None:
    """Verify custom mapper hook on FailureAnalyzer."""
    analyzer = FailureAnalyzer()

    def custom_mapper(ev: EvaluationResult, tr: ExecutionTrace) -> FailureReport | None:
        if ev.evaluator == "SpecialCustomEvaluator":
            return FailureReport(
                trace_id=tr.trace_id,
                category="custom_category",
                type="custom_type",
                severity=FailureSeverity.LOW,
                message="Special handling",
                confidence=1.0,
            )
        return None

    analyzer.register_mapper(custom_mapper)

    trace = ExecutionTrace(trace_id="tr_custom")
    res = EvaluationResult(evaluator="SpecialCustomEvaluator", passed=False)
    report = analyzer.analyze(trace, res)

    assert report.category == "custom_category"
    assert report.type == "custom_type"
    assert report.severity == FailureSeverity.LOW


def test_analyze_trace_failures_aggregates_trace_and_evaluations() -> None:
    """Verify analyze_trace_failures aggregates trace crash and evaluation failures."""
    analyzer = FailureAnalyzer()
    trace = ExecutionTrace(
        trace_id="tr_multi",
        status=ExecutionStatus.FAILED,
        output={"error": "Agent timeout exception"},
    )
    eval1 = ToolCalled("tool1").evaluate(trace)
    eval2 = MaxLatency(max_latency_ms=10.0).evaluate(trace)

    reports = analyzer.analyze_trace_failures(
        trace=trace,
        evaluation_results=[eval1, eval2],
        test_id="tc_multi",
    )

    # 1 execution failure + 2 evaluation failures = 3 reports
    assert len(reports) == 3
    assert reports[0].category == FailureCategory.TASK.value
    assert reports[0].type == FailureType.TASK_INCOMPLETE.value
    assert reports[1].type == FailureType.WRONG_TOOL.value
    assert reports[2].type == FailureType.LATENCY.value
    assert all(r.confidence == 1.0 for r in reports)
