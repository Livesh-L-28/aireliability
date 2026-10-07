"""Unified system health calculator with hard non-compensatory safety vetoes (Phase 43)."""

from __future__ import annotations

from aireliability.dashboard.models import DashboardHealthSummary


class ReliabilityHealthCalculator:
    """Calculates enterprise unified health scores aggregating multi-subsystem intelligence."""

    def calculate_health(
        self,
        reliability_score: float = 0.95,
        safety_score: float = 1.0,
        security_score: float = 1.0,
        rag_score: float = 0.90,
        agent_score: float = 0.92,
        quality_score: float = 0.94,
        active_incidents: int = 0,
        active_alerts: int = 0,
        hard_veto_flag: bool = False,
    ) -> DashboardHealthSummary:
        """Compute holistic system health enforcing hard safety constraints."""
        # Baseline weighted average across functional domains
        weights = {
            "reliability": 0.25,
            "quality": 0.20,
            "agent": 0.20,
            "rag": 0.15,
            "safety": 0.10,
            "security": 0.10,
        }

        base_health = (
            reliability_score * weights["reliability"]
            + quality_score * weights["quality"]
            + agent_score * weights["agent"]
            + rag_score * weights["rag"]
            + safety_score * weights["safety"]
            + security_score * weights["security"]
        )

        # Incident penalty
        incident_penalty = min(0.30, active_incidents * 0.10)
        adjusted_health = max(0.0, base_health - incident_penalty)

        # HARD VETO RULE:
        # If safety or security breaches occur, overall health cannot exceed 0.30
        is_hard_vetoed = (
            hard_veto_flag or safety_score <= 0.30 or security_score <= 0.30
        )
        if is_hard_vetoed:
            overall_health = min(0.30, adjusted_health)
            status = "COMPROMISED"
        elif active_incidents > 0 or adjusted_health < 0.70:
            overall_health = adjusted_health
            status = "DEGRADED"
        elif adjusted_health < 0.50:
            overall_health = adjusted_health
            status = "CRITICAL"
        else:
            overall_health = adjusted_health
            status = "HEALTHY"

        return DashboardHealthSummary(
            overall_health=round(overall_health, 4),
            health_status=status,
            quality_score=round(quality_score, 4),
            reliability_score=round(reliability_score, 4),
            safety_score=round(safety_score, 4),
            security_score=round(security_score, 4),
            rag_score=round(rag_score, 4),
            agent_score=round(agent_score, 4),
            active_incidents_count=active_incidents,
            active_alerts_count=active_alerts,
            hard_veto_applied=is_hard_vetoed,
        )
