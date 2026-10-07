"""Human-readable and structured explainability engine answering the 10 core intelligence questions."""

from __future__ import annotations

import json
from typing import Any

from aireliability.intelligence.models import (
    IntelligenceAnalysis,
    PatternType,
    RecommendationPriority,
)


class IntelligenceExplainer:
    """Explains intelligence findings and answers the 10 core AI reliability intelligence questions."""

    def explain_ten_questions(self, analysis: IntelligenceAnalysis) -> dict[str, Any]:
        """Produce structured answers to the 10 core intelligence questions."""
        # 1. What failed?
        failures_summary = {
            "total_failures": analysis.summary.total_failures_analyzed,
            "dominant_categories": analysis.summary.dominant_failure_categories,
            "clusters": [
                {
                    "name": c.name,
                    "frequency": c.frequency,
                    "dominant_category": c.dominant_category,
                    "representative_failure_id": c.representative_failure_id,
                }
                for c in analysis.clusters
            ],
        }

        # 2. Why did it fail?
        why_failed = {
            "dominant_root_causes": analysis.summary.dominant_root_causes,
            "cluster_root_causes": [
                {
                    "cluster_id": c.cluster_id,
                    "name": c.name,
                    "dominant_root_cause": c.dominant_root_cause,
                }
                for c in analysis.clusters
            ],
        }

        # 3. Has this failure happened before?
        recurring_patterns = [
            p
            for p in analysis.patterns
            if p.pattern_type in (PatternType.RECURRING, PatternType.PERSISTENT)
        ]
        history_summary = {
            "has_occurred_before": len(recurring_patterns) > 0,
            "recurring_patterns_count": len(recurring_patterns),
            "patterns": [
                {
                    "pattern_id": p.pattern_id,
                    "pattern_type": p.pattern_type.value,
                    "title": p.title,
                    "frequency": p.frequency,
                    "first_seen": p.first_seen.isoformat(),
                    "last_seen": p.last_seen.isoformat(),
                }
                for p in recurring_patterns
            ],
        }

        # 4. Are multiple failures related?
        relatedness_summary = {
            "total_clusters": len(analysis.clusters),
            "cluster_relationships": [
                {
                    "cluster_id": c.cluster_id,
                    "name": c.name,
                    "size": c.frequency,
                    "fingerprint": c.fingerprint,
                    "affected_components": c.affected_components,
                }
                for c in analysis.clusters
            ],
            "correlations": [
                {
                    "change": c.source_change_value,
                    "effect": c.observed_effect,
                    "strength": c.strength,
                    "type": c.relationship_type.value,
                    "is_causal": c.is_causal,
                }
                for c in analysis.correlations
            ],
        }

        # 5. Is this failure getting worse?
        trends_summary = {
            "evaluated_trends_count": len(analysis.trends),
            "trends": [
                {
                    "metric_or_dimension": t.metric_or_dimension,
                    "direction": t.direction.value,
                    "rate_of_change": t.rate_of_change,
                    "relative_change": f"{t.relative_change:+.1%}",
                    "volatility": t.volatility,
                    "description": t.description,
                }
                for t in analysis.trends
            ],
        }

        # 6. What components are associated with the failures?
        components = sorted(
            list(
                {comp for c in analysis.clusters for comp in c.affected_components}
                | {comp for p in analysis.patterns for comp in p.affected_components}
            )
        )
        components_summary = {
            "total_components": len(components),
            "affected_components": components,
        }

        # 7. What is the impact?
        impact_summary = {
            "critical_issues_count": analysis.summary.critical_issues_count,
            "assessments": [
                {
                    "target_id": imp.target_id,
                    "observed_impact": imp.observed_impact.value,
                    "estimated_impact": imp.estimated_impact.value,
                    "impact_score": imp.impact_score,
                    "safety_critical": imp.safety_critical,
                    "security_critical": imp.security_critical,
                    "explanation": imp.explanation,
                }
                for imp in analysis.impacts
            ],
        }

        # 8. How confident are we?
        confidence_summary = {
            "score": analysis.confidence.score,
            "level": analysis.confidence.level.value,
            "evidence_count": analysis.confidence.evidence_count,
            "sample_size": analysis.confidence.sample_size,
            "rationale": analysis.confidence.rationale,
            "factors": analysis.confidence.factors,
        }

        # 9. What evidence supports the conclusion?
        evidence_summary = {
            "total_evidence_references": len(analysis.evidence),
            "evidence": [
                {
                    "source_type": ev.source_type,
                    "source_id": ev.source_id,
                    "description": ev.description,
                    "metadata": ev.metadata,
                }
                for ev in analysis.evidence[:25]
            ],
        }

        # 10. What should an engineer investigate or fix first?
        # Sort recommendations: CRITICAL first, then HIGH, MEDIUM, LOW
        order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
        }
        sorted_recs = sorted(
            analysis.recommendations, key=lambda r: order.get(r.priority, 4)
        )
        remediation_summary = {
            "total_recommendations": len(sorted_recs),
            "action_items": [
                {
                    "priority": rec.priority.value,
                    "title": rec.title,
                    "suggested_action": rec.suggested_action,
                    "rationale": rec.rationale,
                    "affected_components": rec.affected_components,
                    "remediation_links": rec.remediation_links,
                }
                for rec in sorted_recs
            ],
        }

        return {
            "target_name": analysis.target_name,
            "analysis_id": analysis.analysis_id,
            "created_at": analysis.created_at.isoformat(),
            "questions": {
                "1_what_failed": failures_summary,
                "2_why_did_it_fail": why_failed,
                "3_has_this_happened_before": history_summary,
                "4_are_multiple_failures_related": relatedness_summary,
                "5_is_this_failure_getting_worse": trends_summary,
                "6_associated_components": components_summary,
                "7_impact": impact_summary,
                "8_confidence": confidence_summary,
                "9_evidence": evidence_summary,
                "10_investigate_first": remediation_summary,
            },
        }

    def format_text(self, analysis: IntelligenceAnalysis) -> str:
        """Format a comprehensive, human-readable terminal report answering the 10 questions."""
        q = self.explain_ten_questions(analysis)["questions"]
        lines: list[str] = []

        lines.append("=" * 70)
        lines.append("  AI RELIABILITY INTELLIGENCE REPORT")
        lines.append(f"  Target: {analysis.target_name} | ID: {analysis.analysis_id}")
        lines.append("=" * 70)
        lines.append("")

        # 1. What failed?
        q1 = q["1_what_failed"]
        lines.append(
            f"1. WHAT FAILED? ({q1['total_failures']} total failures analyzed)"
        )
        if q1["clusters"]:
            for c in q1["clusters"][:5]:
                lines.append(
                    f"   * [{c['dominant_category'].upper()}] {c['name']} (x{c['frequency']})"
                )
        else:
            lines.append("   * No failures detected in this evaluation.")
        lines.append("")

        # 2. Why did it fail?
        q2 = q["2_why_did_it_fail"]
        lines.append("2. WHY DID IT FAIL? (Root Cause Intelligence)")
        if q2["dominant_root_causes"]:
            for rc, count in q2["dominant_root_causes"].items():
                lines.append(f"   * {rc}: {count} occurrences")
        else:
            lines.append("   * No root causes identified.")
        lines.append("")

        # 3. Has this happened before?
        q3 = q["3_has_this_happened_before"]
        lines.append("3. HAS THIS HAPPENED BEFORE? (Pattern Recurrence)")
        if q3["has_occurred_before"]:
            for p in q3["patterns"][:5]:
                lines.append(
                    f"   * [RECURRING] {p['title']} (seen {p['frequency']} times)"
                )
        else:
            lines.append("   * No recurring patterns detected across historical runs.")
        lines.append("")

        # 4. Are multiple failures related?
        q4 = q["4_are_multiple_failures_related"]
        lines.append(
            f"4. ARE MULTIPLE FAILURES RELATED? ({q4['total_clusters']} structural clusters)"
        )
        for c in q4["cluster_relationships"][:4]:
            lines.append(
                f"   * Cluster {c['cluster_id']}: {c['name']} (grouped {c['size']} failures)"
            )
        for corr in q4["correlations"][:3]:
            lines.append(
                f"   * Correlation: {corr['change']} -> {corr['effect']} (strength: {corr['strength']:.2f})"
            )
        lines.append("")

        # 5. Is this failure getting worse?
        q5 = q["5_is_this_failure_getting_worse"]
        lines.append("5. IS THIS FAILURE GETTING WORSE? (Reliability Trends)")
        if q5["trends"]:
            for t in q5["trends"]:
                lines.append(
                    f"   * {t['metric_or_dimension']}: {t['direction'].upper()} ({t['description']})"
                )
        else:
            lines.append(
                "   * Insufficient historical data to compute longitudinal trends."
            )
        lines.append("")

        # 6. What components are associated?
        q6 = q["6_associated_components"]
        lines.append("6. WHAT COMPONENTS ARE ASSOCIATED WITH THE FAILURES?")
        if q6["affected_components"]:
            for comp in q6["affected_components"]:
                lines.append(f"   * {comp}")
        else:
            lines.append("   * No specific components flagged.")
        lines.append("")

        # 7. What is the impact?
        q7 = q["7_impact"]
        lines.append(
            f"7. WHAT IS THE IMPACT? ({q7['critical_issues_count']} critical issues)"
        )
        for imp in q7["assessments"][:4]:
            badge = (
                "CRITICAL"
                if (imp["safety_critical"] or imp["security_critical"])
                else imp["observed_impact"]
            )
            lines.append(f"   * [{badge}] {imp['target_id']}: {imp['explanation']}")
        lines.append("")

        # 8. How confident are we?
        q8 = q["8_confidence"]
        lines.append(
            f"8. HOW CONFIDENT ARE WE? (Level: {q8['level']} | Score: {q8['score']:.2f})"
        )
        lines.append(f"   * Rationale: {q8['rationale']}")
        lines.append("")

        # 9. What evidence supports the conclusion?
        q9 = q["9_evidence"]
        lines.append(
            f"9. WHAT EVIDENCE SUPPORTS THE CONCLUSION? ({q9['total_evidence_references']} citations)"
        )
        for ev in q9["evidence"][:4]:
            lines.append(
                f"   * [{ev['source_type']}:{ev['source_id']}] {ev['description']}"
            )
        lines.append("")

        # 10. What should an engineer investigate or fix first?
        q10 = q["10_investigate_first"]
        lines.append("10. WHAT SHOULD AN ENGINEER INVESTIGATE OR FIX FIRST?")
        if q10["action_items"]:
            for idx, rec in enumerate(q10["action_items"][:5], 1):
                lines.append(f"   Priority #{idx} [{rec['priority']}]: {rec['title']}")
                lines.append(f"      Action: {rec['suggested_action']}")
                lines.append(f"      Rationale: {rec['rationale']}")
        else:
            lines.append("   * All checks passed. No remediation actions required.")

        lines.append("=" * 70)
        return "\n".join(lines)

    def format_json(self, analysis: IntelligenceAnalysis, indent: int = 2) -> str:
        """Format the 10 questions and intelligence results as JSON."""
        data = self.explain_ten_questions(analysis)
        return json.dumps(data, indent=indent, default=str)
