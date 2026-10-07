"""Idempotent builder constructing the AI Reliability Knowledge Graph from platform artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aireliability.core.models import (
    ExecutionTrace,
    FailureReport,
    RegressionTest,
    StepType,
)
from aireliability.diagnosis.models import RootCause, RootCauseReport
from aireliability.evaluation.governance.baselines import EvaluationBaseline
from aireliability.evaluation.models import EvaluationReport
from aireliability.graph.edges import (
    edge_affects,
    edge_caused_regression,
    edge_contains,
    edge_correlated_with,
    edge_evaluated,
    edge_executed,
    edge_failed,
    edge_has_root_cause,
    edge_linked_to,
    edge_measured_by,
    edge_supported_by,
    edge_triggered,
    edge_used_model,
    edge_used_prompt,
    edge_used_retriever,
    edge_used_tool,
)
from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import (
    GraphNode,
    GraphNodeType,
)
from aireliability.graph.nodes import (
    node_from_cluster,
    node_from_dataset,
    node_from_evaluation,
    node_from_execution,
    node_from_failure,
    node_from_incident,
    node_from_metric,
    node_from_model,
    node_from_pattern,
    node_from_prompt,
    node_from_recommendation,
    node_from_regression,
    node_from_retriever,
    node_from_root_cause,
    node_from_test_case,
    node_from_tool,
    node_from_trace,
    node_from_trace_step,
    node_from_trend,
)

if TYPE_CHECKING:
    from aireliability.evaluation.datasets.models import EvaluationDataset
    from aireliability.evaluation.experiments.models import ABComparisonResult
    from aireliability.evaluation.governance.baselines import EvaluationComparisonResult
    from aireliability.graph.integrations import GraphTelemetry
    from aireliability.intelligence.models import IntelligenceAnalysis
    from aireliability.observability.incidents import IncidentRecord


class KnowledgeGraphBuilder:
    """Constructs, updates, and links entities within a KnowledgeGraph."""

    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        telemetry: GraphTelemetry | None = None,
    ) -> None:
        self.graph: KnowledgeGraph = graph if graph is not None else KnowledgeGraph()
        self.telemetry = telemetry

    def from_evaluation(
        self,
        report: EvaluationReport,
        model_name: str | None = None,
        prompt_name: str | None = None,
        retriever_name: str | None = None,
        tool_name: str | None = None,
    ) -> KnowledgeGraphBuilder:
        """Extract and link evaluation run, dataset, test cases, metrics, failures, and components."""
        # 1. Dataset Node
        ds_node = node_from_dataset(report.dataset_id)
        self.graph.add_node(ds_node)

        # 2. Evaluation Node
        eval_node = node_from_evaluation(
            report.report_id,
            target_name=report.target_name,
            metadata=report.metadata,
        )
        self.graph.add_node(eval_node)
        self.graph.add_edge(edge_evaluated(ds_node.node_id, eval_node.node_id))

        # 3. Connect Model / Prompt / Retriever / Tool metadata
        meta = report.metadata or {}
        effective_model = model_name or meta.get("model") or meta.get("model_version")
        if effective_model:
            m_ver = str(meta.get("model_version")) if "model_version" in meta else None
            m_node = node_from_model(str(effective_model), version=m_ver)
            self.graph.add_node(m_node)
            self.graph.add_edge(edge_used_model(eval_node.node_id, m_node.node_id))
            self.graph.add_edge(edge_affects(m_node.node_id, eval_node.node_id))

        effective_prompt = (
            prompt_name or meta.get("prompt") or meta.get("prompt_version")
        )
        if effective_prompt:
            p_ver = (
                str(meta.get("prompt_version")) if "prompt_version" in meta else None
            )
            p_node = node_from_prompt(str(effective_prompt), version=p_ver)
            self.graph.add_node(p_node)
            self.graph.add_edge(edge_used_prompt(eval_node.node_id, p_node.node_id))
            self.graph.add_edge(edge_affects(p_node.node_id, eval_node.node_id))

        effective_retriever = (
            retriever_name or meta.get("retriever") or meta.get("retriever_version")
        )
        if effective_retriever:
            r_node = node_from_retriever(str(effective_retriever))
            self.graph.add_node(r_node)
            self.graph.add_edge(edge_used_retriever(eval_node.node_id, r_node.node_id))
            self.graph.add_edge(edge_affects(r_node.node_id, eval_node.node_id))

        effective_tool = tool_name or meta.get("tool") or meta.get("tool_version")
        if effective_tool:
            t_node = node_from_tool(str(effective_tool))
            self.graph.add_node(t_node)
            self.graph.add_edge(edge_used_tool(eval_node.node_id, t_node.node_id))
            self.graph.add_edge(edge_affects(t_node.node_id, eval_node.node_id))

        # 4. Metrics Nodes
        for m_name, m_res in report.metrics.items():
            metric_node = node_from_metric(
                metric_name=m_name,
                value=m_res.value,
                evaluation_id=report.report_id,
                metadata=m_res.metadata,
            )
            self.graph.add_node(metric_node)
            self.graph.add_edge(
                edge_measured_by(eval_node.node_id, metric_node.node_id)
            )

        # 5. Evaluation Results & Test Cases
        for res in report.evaluations:
            tc_id = res.test_case or res.metadata.get("test_id")
            if tc_id:
                tc_node = node_from_test_case(str(tc_id))
                self.graph.add_node(tc_node)
                self.graph.add_edge(edge_contains(ds_node.node_id, tc_node.node_id))
                self.graph.add_edge(edge_evaluated(tc_node.node_id, eval_node.node_id))

            if res.execution_id:
                exec_node = node_from_execution(res.execution_id)
                self.graph.add_node(exec_node)
                if tc_id:
                    self.graph.add_edge(
                        edge_executed(f"test_case:{tc_id}", exec_node.node_id)
                    )

        # 6. Failures & Root Causes
        for f in report.failures:
            self.from_failure(f, evaluation_id=eval_node.node_id)

        # 7. Root Causes
        for rc_item in report.root_causes:
            if isinstance(rc_item, RootCauseReport):
                if (
                    hasattr(rc_item, "primary_root_cause")
                    and rc_item.primary_root_cause
                ):
                    self._add_root_cause(rc_item.primary_root_cause)
                if hasattr(rc_item, "secondary_root_causes"):
                    for sec in rc_item.secondary_root_causes:
                        self._add_root_cause(sec)
            elif isinstance(rc_item, RootCause):
                self._add_root_cause(rc_item)

        return self

    def from_trace(self, trace: ExecutionTrace) -> KnowledgeGraphBuilder:
        """Extract and link execution trace, trace steps, and called tools."""
        tr_node = node_from_trace(trace.trace_id, metadata=trace.metadata)
        self.graph.add_node(tr_node)

        if trace.test_id:
            tc_id = f"test_case:{trace.test_id}"
            if not self.graph.has_node(tc_id):
                self.graph.add_node(node_from_test_case(trace.test_id))
            self.graph.add_edge(edge_contains(tc_id, tr_node.node_id))

        meta = trace.metadata or {}
        if "execution_id" in meta:
            eid = meta["execution_id"]
            ex_node_id = f"execution:{eid}"
            if not self.graph.has_node(ex_node_id):
                self.graph.add_node(node_from_execution(eid))
            self.graph.add_edge(edge_executed(ex_node_id, tr_node.node_id))

        # Steps
        for idx, step in enumerate(trace.steps):
            step_id = (
                getattr(step, "id", None)
                or getattr(step, "step_id", None)
                or f"{trace.trace_id}_step_{idx}"
            )
            s_node = node_from_trace_step(
                step_id, name=step.name, metadata=step.metadata
            )
            self.graph.add_node(s_node)
            self.graph.add_edge(edge_contains(tr_node.node_id, s_node.node_id))

            # Connect tools
            if step.type == StepType.TOOL or (
                step.metadata
                and ("tool_name" in step.metadata or "tool" in step.metadata)
            ):
                tool_name = (
                    getattr(step, "tool", None)
                    or (step.metadata.get("tool_name") if step.metadata else None)
                    or (step.metadata.get("tool") if step.metadata else None)
                    or step.name
                )
                t_node = node_from_tool(str(tool_name))
                self.graph.add_node(t_node)
                self.graph.add_edge(edge_used_tool(s_node.node_id, t_node.node_id))

        return self

    def from_failure(
        self,
        failure: FailureReport,
        root_cause: RootCause | None = None,
        evaluation_id: str | None = None,
    ) -> KnowledgeGraphBuilder:
        """Extract and link a FailureReport, affected components, and root causes."""
        meta = failure.metadata or {}
        raw_sev = getattr(failure, "severity", None)
        sev_str = (
            str(getattr(raw_sev, "value", raw_sev)) if raw_sev is not None else None
        )
        if (not sev_str or sev_str.upper() == "MEDIUM") and "severity" in meta:
            sev_str = str(meta["severity"])
        sev_final = sev_str or "MEDIUM"

        f_node = node_from_failure(
            failure_id=failure.failure_id,
            category=getattr(failure.category, "value", str(failure.category)),
            failure_type=getattr(failure.type, "value", str(failure.type)),
            message=failure.message,
            severity=sev_final,
            metadata=failure.metadata,
        )
        self.graph.add_node(f_node)

        if evaluation_id:
            self.graph.add_edge(edge_failed(evaluation_id, f_node.node_id))

        if failure.trace_id:
            tr_id = f"trace:{failure.trace_id}"
            if not self.graph.has_node(tr_id):
                self.graph.add_node(node_from_trace(failure.trace_id))
            self.graph.add_edge(edge_failed(tr_id, f_node.node_id))

        if failure.test_id:
            tc_id = f"test_case:{failure.test_id}"
            if not self.graph.has_node(tc_id):
                self.graph.add_node(node_from_test_case(failure.test_id))
            self.graph.add_edge(edge_failed(tc_id, f_node.node_id))

        # Check for affected component
        meta = failure.metadata or {}
        comp = meta.get("component")
        if comp:
            comp_str = str(comp)
            if comp_str.startswith("tool:"):
                tool_n = node_from_tool(comp_str.replace("tool:", ""))
                self.graph.add_node(tool_n)
                self.graph.add_edge(edge_affects(f_node.node_id, tool_n.node_id))
            elif comp_str.startswith("retriever:"):
                ret_n = node_from_retriever(comp_str.replace("retriever:", ""))
                self.graph.add_node(ret_n)
                self.graph.add_edge(edge_affects(f_node.node_id, ret_n.node_id))

        if root_cause:
            self._add_root_cause(root_cause, failure_node_id=f_node.node_id)

        return self

    def _add_root_cause(
        self,
        rc: RootCause,
        failure_node_id: str | None = None,
    ) -> None:
        """Internal helper to add a ROOT_CAUSE node and connect to failure."""
        rc_cat = getattr(rc.category, "value", str(rc.category))
        rc_type = getattr(rc.type, "value", str(rc.type))
        rc_id = (
            getattr(rc, "id", None)
            or getattr(rc, "root_cause_id", None)
            or (rc.metadata.get("root_cause_id") if rc.metadata else None)
            or "unknown_rc"
        )
        rc_node = node_from_root_cause(
            root_cause_id=rc_id,
            category=rc_cat,
            root_cause_type=rc_type,
            description=rc.description,
            confidence=rc.confidence,
            metadata=rc.metadata,
        )
        self.graph.add_node(rc_node)

        if failure_node_id:
            self.graph.add_edge(
                edge_has_root_cause(
                    failure_node_id, rc_node.node_id, confidence=rc.confidence
                )
            )
        elif hasattr(rc, "trace_id") and rc.trace_id:
            tr_id = f"trace:{rc.trace_id}"
            if self.graph.has_node(tr_id):
                self.graph.add_edge(
                    edge_has_root_cause(
                        tr_id, rc_node.node_id, confidence=rc.confidence
                    )
                )

    def from_incident(self, incident: IncidentRecord) -> KnowledgeGraphBuilder:
        """Extract and link an operational IncidentRecord."""
        inc_node = node_from_incident(
            incident_id=incident.incident_id,
            title=incident.title,
            severity=getattr(incident.severity, "value", str(incident.severity)),
            metadata=incident.metadata,
        )
        self.graph.add_node(inc_node)

        for tid in incident.trace_ids:
            tr_id = f"trace:{tid}"
            if not self.graph.has_node(tr_id):
                self.graph.add_node(node_from_trace(tid))
            self.graph.add_edge(edge_triggered(tr_id, inc_node.node_id))

        for eid in incident.execution_ids:
            ex_id = f"execution:{eid}"
            if not self.graph.has_node(ex_id):
                self.graph.add_node(node_from_execution(eid))
            self.graph.add_edge(edge_triggered(ex_id, inc_node.node_id))

        meta = incident.metadata or {}
        fid = getattr(incident, "failure_id", None) or meta.get("failure_id")
        if fid:
            f_node_id = f"failure:{fid}"
            if not self.graph.has_node(f_node_id):
                self.graph.add_node(node_from_failure(fid, category="incident"))
            self.graph.add_edge(edge_triggered(f_node_id, inc_node.node_id))

        rcid = getattr(incident, "root_cause_id", None) or meta.get("root_cause_id")
        if rcid:
            rc_node_id = f"root_cause:{rcid}"
            if not self.graph.has_node(rc_node_id):
                self.graph.add_node(node_from_root_cause(rcid, category="incident"))
            self.graph.add_edge(edge_triggered(rc_node_id, inc_node.node_id))

        return self

    def from_regression(
        self,
        regression: RegressionTest,
        baseline: EvaluationBaseline | None = None,
    ) -> KnowledgeGraphBuilder:
        """Extract and link a synthesized regression test."""
        reg_id = getattr(regression, "id", None) or getattr(
            regression, "test_id", "reg"
        )
        reg_node = node_from_regression(
            regression_id=reg_id,
            name=regression.name,
            metadata=regression.metadata,
        )
        self.graph.add_node(reg_node)

        if regression.source_failure_id:
            f_id = f"failure:{regression.source_failure_id}"
            if not self.graph.has_node(f_id):
                self.graph.add_node(
                    node_from_failure(regression.source_failure_id, category="unknown")
                )
            self.graph.add_edge(edge_caused_regression(f_id, reg_node.node_id))

        if baseline:
            base_id = f"baseline:{baseline.name}"
            if not self.graph.has_node(base_id):
                self.from_baseline(baseline)
            self.graph.add_edge(edge_caused_regression(base_id, reg_node.node_id))

        return self

    def from_baseline(self, baseline: EvaluationBaseline) -> KnowledgeGraphBuilder:
        """Extract and link reference baseline snapshot."""
        base_node = GraphNode.create(
            node_type=GraphNodeType.BASELINE,
            source_id=baseline.name,
            name=f"Baseline: {baseline.name}",
            metadata=baseline.metadata,
        )
        self.graph.add_node(base_node)

        ds_id = f"dataset:{baseline.dataset_id}"
        if not self.graph.has_node(ds_id):
            self.graph.add_node(node_from_dataset(baseline.dataset_id))
        self.graph.add_edge(edge_contains(base_node.node_id, ds_id))

        return self

    def from_intelligence(
        self, analysis: IntelligenceAnalysis
    ) -> KnowledgeGraphBuilder:
        """Extract and link Phase 34 Intelligence clusters, patterns, trends, and recommendations."""
        # 1. Clusters
        for c in analysis.clusters:
            c_node = node_from_cluster(
                cluster_id=c.cluster_id,
                name=c.name,
                fingerprint=c.fingerprint,
                metadata=c.metadata,
            )
            self.graph.add_node(c_node)

            for fid in c.failure_ids:
                f_id = f"failure:{fid}"
                if not self.graph.has_node(f_id):
                    self.graph.add_node(
                        node_from_failure(fid, category=c.dominant_category)
                    )
                self.graph.add_edge(edge_contains(c_node.node_id, f_id))

            for comp in c.affected_components:
                if comp.startswith("tool:"):
                    tn = node_from_tool(comp.replace("tool:", ""))
                    self.graph.add_node(tn)
                    self.graph.add_edge(edge_affects(c_node.node_id, tn.node_id))
                elif comp.startswith("retriever:"):
                    rn = node_from_retriever(comp.replace("retriever:", ""))
                    self.graph.add_node(rn)
                    self.graph.add_edge(edge_affects(c_node.node_id, rn.node_id))

        # 2. Patterns
        for p in analysis.patterns:
            p_node = node_from_pattern(
                pattern_id=p.pattern_id,
                pattern_type=p.pattern_type.value,
                title=p.title,
                metadata=p.metadata,
            )
            self.graph.add_node(p_node)

        # 3. Correlations (Explicitly non-causal by default)
        for corr in analysis.correlations:
            src_node = None
            if "model" in corr.source_change_type:
                src_node = node_from_model(corr.source_change_value)
            elif "prompt" in corr.source_change_type:
                src_node = node_from_prompt(corr.source_change_value)
            elif "retriever" in corr.source_change_type:
                src_node = node_from_retriever(corr.source_change_value)

            if src_node:
                self.graph.add_node(src_node)
                # Link to metric or cluster
                target_node_id = f"metric:{corr.affected_metric_or_failure}"
                if not self.graph.has_node(target_node_id):
                    self.graph.add_node(
                        node_from_metric(corr.affected_metric_or_failure, value=0.0)
                    )
                self.graph.add_edge(
                    edge_correlated_with(
                        src_node.node_id,
                        target_node_id,
                        strength=corr.strength,
                        is_causal=corr.is_causal,
                        metadata={"effect": corr.observed_effect},
                    )
                )

        # 4. Trends
        for tr in analysis.trends:
            tr_node = node_from_trend(
                trend_id=tr.trend_id,
                metric=tr.metric_or_dimension,
                direction=tr.direction.value,
                metadata=tr.metadata,
            )
            self.graph.add_node(tr_node)

        # 5. Recommendations
        for r in analysis.recommendations:
            r_node = node_from_recommendation(
                rec_id=r.recommendation_id,
                title=r.title,
                priority=r.priority.value,
                metadata=r.metadata,
            )
            self.graph.add_node(r_node)

            for cid in r.related_clusters:
                c_id = f"failure_cluster:{cid}"
                if self.graph.has_node(c_id):
                    self.graph.add_edge(edge_supported_by(r_node.node_id, c_id))

        return self

    def from_root_cause(
        self,
        root_cause: RootCause,
        failure_id: str | None = None,
    ) -> KnowledgeGraphBuilder:
        """Add a standalone RootCause and optionally connect to an associated failure."""
        effective_fid = (
            failure_id
            or getattr(root_cause, "failure_id", None)
            or (root_cause.metadata.get("failure_id") if root_cause.metadata else None)
        )
        f_node_id = f"failure:{effective_fid}" if effective_fid else None
        self._add_root_cause(root_cause, failure_node_id=f_node_id)
        return self

    def from_comparison(
        self,
        comparison: EvaluationComparisonResult,
    ) -> KnowledgeGraphBuilder:
        """Ingest baseline comparison results and link regression events."""
        base_id = f"baseline:{comparison.baseline_name}:{comparison.baseline_version}"
        if not self.graph.has_node(base_id):
            base_node = GraphNode.create(
                GraphNodeType.BASELINE,
                source_id=f"{comparison.baseline_name}:{comparison.baseline_version}",
                name=comparison.baseline_name,
                version=comparison.baseline_version,
            )
            self.graph.add_node(base_node)

        eval_id = f"evaluation:{comparison.current_report_id}"
        if self.graph.has_node(eval_id):
            self.graph.add_edge(edge_linked_to(base_id, eval_id))

        for reg_name in comparison.regressions:
            reg_node = node_from_regression(
                regression_id=f"{comparison.current_report_id}_{reg_name}",
                test_id=reg_name,
                metadata={
                    "baseline": comparison.baseline_name,
                    "version": comparison.baseline_version,
                },
            )
            self.graph.add_node(reg_node)
            self.graph.add_edge(edge_caused_regression(eval_id, reg_node.node_id))

        return self

    def from_dataset(
        self,
        dataset: EvaluationDataset | str,
        version: str = "1.0.0",
    ) -> KnowledgeGraphBuilder:
        """Ingest an evaluation dataset and its constituent test cases."""
        if isinstance(dataset, str):
            ds_node = node_from_dataset(dataset, version=version)
            self.graph.add_node(ds_node)
            return self

        ds_node = node_from_dataset(
            dataset.id, version=dataset.version, metadata=dataset.metadata
        )
        self.graph.add_node(ds_node)

        for tc in dataset.test_cases:
            tc_node = node_from_test_case(
                tc.id, dataset_id=dataset.id, metadata=tc.metadata
            )
            self.graph.add_node(tc_node)
            self.graph.add_edge(edge_contains(ds_node.node_id, tc_node.node_id))

        return self

    def from_experiment(
        self,
        experiment: ABComparisonResult,
    ) -> KnowledgeGraphBuilder:
        """Ingest an A/B experimentation result comparing variants."""
        exp_node = GraphNode.create(
            GraphNodeType.EXPERIMENT,
            source_id=experiment.experiment_id,
            name=f"Experiment {experiment.experiment_id}",
            metadata={
                "winner": experiment.overall_winner,
                "summary": experiment.summary,
                "metric_deltas": experiment.metric_deltas,
            },
        )
        self.graph.add_node(exp_node)

        # Variant A
        va = experiment.variant_a
        if va.model_version:
            ma = node_from_model(va.name, version=va.model_version)
            self.graph.add_node(ma)
            self.graph.add_edge(edge_linked_to(exp_node.node_id, ma.node_id))

        # Variant B
        vb = experiment.variant_b
        if vb.model_version:
            mb = node_from_model(vb.name, version=vb.model_version)
            self.graph.add_node(mb)
            self.graph.add_edge(edge_linked_to(exp_node.node_id, mb.node_id))

        return self
