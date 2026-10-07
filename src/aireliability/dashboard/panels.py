"""Panel factory building all 21 specialized reliability intelligence panels (Phase 43)."""

from __future__ import annotations

from typing import Any

from aireliability.dashboard.models import (
    DashboardMetric,
    DashboardPanel,
    DashboardWidget,
)


class DashboardPanelBuilder:
    """Builds standard reliability panels consuming multi-phase telemetry."""

    def build_all_panels(
        self, metrics_data: dict[str, Any] | None = None
    ) -> list[DashboardPanel]:
        """Generate all 21 standard dashboard panels."""
        m = metrics_data or {}
        panels: list[DashboardPanel] = [
            self._panel_health(m),
            self._panel_reliability_overview(m),
            self._panel_failures(m),
            self._panel_root_causes(m),
            self._panel_incidents(m),
            self._panel_trends(m),
            self._panel_slos(m),
            self._panel_error_budgets(m),
            self._panel_rag(m),
            self._panel_agent(m),
            self._panel_safety(m),
            self._panel_validation_campaigns(m),
            self._panel_predictions(m),
            self._panel_optimization(m),
            self._panel_healing(m),
            self._panel_regression(m),
            self._panel_knowledge_graph(m),
            self._panel_cost(m),
            self._panel_latency(m),
            self._panel_throughput(m),
            self._panel_drift(m),
        ]
        return panels

    def _panel_health(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="System Health Overview",
            widget_type="stat_card",
            metrics=[
                DashboardMetric(
                    key="health",
                    label="Overall Health",
                    value=m.get("health", 0.95),
                    unit="ratio",
                ),
                DashboardMetric(
                    key="uptime",
                    label="Uptime SLA",
                    value=m.get("uptime", 0.999),
                    unit="ratio",
                ),
            ],
        )
        return DashboardPanel(title="System Health", category="health", widgets=[w])

    def _panel_reliability_overview(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Reliability Metrics",
            metrics=[
                DashboardMetric(
                    key="reliability",
                    label="Mean Reliability",
                    value=m.get("reliability", 0.94),
                    unit="ratio",
                ),
                DashboardMetric(
                    key="error_rate",
                    label="Error Rate",
                    value=m.get("error_rate", 0.03),
                    unit="ratio",
                ),
            ],
        )
        return DashboardPanel(
            title="Reliability Overview", category="reliability", widgets=[w]
        )

    def _panel_failures(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Failure Distribution",
            widget_type="table",
            metrics=[
                DashboardMetric(
                    key="total_failures",
                    label="Diagnosed Failures",
                    value=float(m.get("total_failures", 12)),
                    unit="count",
                ),
            ],
        )
        return DashboardPanel(title="Failures", category="failures", widgets=[w])

    def _panel_root_causes(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Top Root Causes",
            widget_type="bar_chart",
            metrics=[
                DashboardMetric(
                    key="rc_count",
                    label="Identified Root Causes",
                    value=float(m.get("root_causes", 4)),
                    unit="count",
                ),
            ],
        )
        return DashboardPanel(title="Root Causes", category="intelligence", widgets=[w])

    def _panel_incidents(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Active Incidents",
            metrics=[
                DashboardMetric(
                    key="incidents",
                    label="Active Incidents",
                    value=float(m.get("incidents", 0)),
                    unit="count",
                )
            ],
        )
        return DashboardPanel(title="Incidents", category="incidents", widgets=[w])

    def _panel_trends(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Reliability Trends",
            metrics=[
                DashboardMetric(
                    key="trend_slope",
                    label="Trend Slope",
                    value=m.get("trend_slope", 0.01),
                    unit="slope",
                )
            ],
        )
        return DashboardPanel(title="Trends", category="trends", widgets=[w])

    def _panel_slos(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="SLO Conformance",
            metrics=[
                DashboardMetric(
                    key="slo_compliance",
                    label="SLO Compliance",
                    value=m.get("slo_compliance", 0.99),
                    unit="ratio",
                )
            ],
        )
        return DashboardPanel(title="SLOs", category="governance", widgets=[w])

    def _panel_error_budgets(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Error Budget Burn",
            metrics=[
                DashboardMetric(
                    key="error_budget_left",
                    label="Remaining Budget",
                    value=m.get("error_budget", 0.85),
                    unit="ratio",
                )
            ],
        )
        return DashboardPanel(title="Error Budgets", category="governance", widgets=[w])

    def _panel_rag(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="RAG Reliability",
            metrics=[
                DashboardMetric(
                    key="retrieval_prec",
                    label="Retrieval Precision",
                    value=m.get("retrieval_prec", 0.92),
                    unit="ratio",
                ),
                DashboardMetric(
                    key="grounding",
                    label="Grounding Faithfulness",
                    value=m.get("grounding", 0.94),
                    unit="ratio",
                ),
            ],
        )
        return DashboardPanel(title="RAG Reliability", category="rag", widgets=[w])

    def _panel_agent(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Agent Reliability",
            metrics=[
                DashboardMetric(
                    key="goal_completion",
                    label="Goal Success",
                    value=m.get("goal_completion", 0.88),
                    unit="ratio",
                ),
                DashboardMetric(
                    key="tool_accuracy",
                    label="Tool Selection",
                    value=m.get("tool_accuracy", 0.95),
                    unit="ratio",
                ),
            ],
        )
        return DashboardPanel(title="Agent Reliability", category="agent", widgets=[w])

    def _panel_safety(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Safety Validation",
            metrics=[
                DashboardMetric(
                    key="safety_score",
                    label="Safety Score",
                    value=m.get("safety_score", 1.0),
                    unit="ratio",
                ),
                DashboardMetric(
                    key="risk_score",
                    label="Risk Score",
                    value=m.get("risk_score", 0.0),
                    unit="ratio",
                ),
            ],
        )
        return DashboardPanel(title="Safety", category="safety", widgets=[w])

    def _panel_validation_campaigns(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Campaign Results",
            metrics=[
                DashboardMetric(
                    key="campaigns",
                    label="Campaigns Completed",
                    value=float(m.get("campaigns", 3)),
                    unit="count",
                )
            ],
        )
        return DashboardPanel(
            title="Validation Campaigns", category="safety", widgets=[w]
        )

    def _panel_predictions(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Reliability Forecast",
            metrics=[
                DashboardMetric(
                    key="pred_rel",
                    label="Forecasted Reliability",
                    value=m.get("pred_rel", 0.93),
                    unit="ratio",
                ),
                DashboardMetric(
                    key="pred_conf",
                    label="Prediction Confidence",
                    value=m.get("pred_conf", 0.85),
                    unit="ratio",
                ),
            ],
        )
        return DashboardPanel(title="Predictions", category="prediction", widgets=[w])

    def _panel_optimization(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Pareto Optimization",
            metrics=[
                DashboardMetric(
                    key="pareto_eff",
                    label="Pareto Efficiency",
                    value=m.get("pareto_eff", 0.91),
                    unit="ratio",
                )
            ],
        )
        return DashboardPanel(
            title="Optimization", category="optimization", widgets=[w]
        )

    def _panel_healing(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Self-Healing Actions",
            metrics=[
                DashboardMetric(
                    key="healed",
                    label="Remediations Applied",
                    value=float(m.get("healed", 5)),
                    unit="count",
                )
            ],
        )
        return DashboardPanel(title="Healing", category="healing", widgets=[w])

    def _panel_regression(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Regression Tests",
            metrics=[
                DashboardMetric(
                    key="reg_passed",
                    label="Regression Pass Rate",
                    value=m.get("reg_passed", 0.98),
                    unit="ratio",
                )
            ],
        )
        return DashboardPanel(title="Regression", category="testing", widgets=[w])

    def _panel_knowledge_graph(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Knowledge Graph Status",
            metrics=[
                DashboardMetric(
                    key="nodes",
                    label="Total Nodes",
                    value=float(m.get("graph_nodes", 140)),
                    unit="count",
                ),
                DashboardMetric(
                    key="edges",
                    label="Total Edges",
                    value=float(m.get("graph_edges", 320)),
                    unit="count",
                ),
            ],
        )
        return DashboardPanel(title="Knowledge Graph", category="graph", widgets=[w])

    def _panel_cost(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Cost Analysis",
            metrics=[
                DashboardMetric(
                    key="cost",
                    label="Mean Run Cost (USD)",
                    value=m.get("cost", 0.045),
                    unit="usd",
                )
            ],
        )
        return DashboardPanel(title="Cost", category="performance", widgets=[w])

    def _panel_latency(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Latency Percentiles",
            metrics=[
                DashboardMetric(
                    key="p95_latency",
                    label="P95 Latency (s)",
                    value=m.get("latency_p95", 1.25),
                    unit="s",
                )
            ],
        )
        return DashboardPanel(title="Latency", category="performance", widgets=[w])

    def _panel_throughput(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Throughput & Concurrency",
            metrics=[
                DashboardMetric(
                    key="qps",
                    label="Requests Per Second",
                    value=m.get("qps", 42.0),
                    unit="qps",
                )
            ],
        )
        return DashboardPanel(title="Throughput", category="performance", widgets=[w])

    def _panel_drift(self, m: dict[str, Any]) -> DashboardPanel:
        w = DashboardWidget(
            title="Telemetry Drift",
            metrics=[
                DashboardMetric(
                    key="drift_score",
                    label="Feature Drift Score",
                    value=m.get("drift_score", 0.05),
                    unit="ratio",
                )
            ],
        )
        return DashboardPanel(title="Drift", category="performance", widgets=[w])
