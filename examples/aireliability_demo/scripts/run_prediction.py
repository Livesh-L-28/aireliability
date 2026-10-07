#!/usr/bin/env python3
"""Run reliability prediction and risk forecasting."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aireliability_demo.app.reliability.integration import DemoReliabilityIntegrator


def main() -> None:
    print("=" * 60)
    print("AIRELIABILITY v1.4.0 — RELIABILITY PREDICTION & FORECASTING")
    print("=" * 60)

    integrator = DemoReliabilityIntegrator()

    # Scenario A: Stable History
    print("\n[1/2] Forecasting for Stable Historical Telemetry...")
    stable_history = [0.99, 0.98, 0.98, 0.99, 0.98]
    pred_stable = integrator.predict_reliability(
        stable_history, target_id="pipeline_stable"
    )
    print(f"  Historical Reliability: {stable_history}")
    print(
        f"  Forecasted Reliability: {pred_stable.reliability_forecast.forecasted_value:.4f}"
    )
    print(
        f"  Confidence Interval:    [{pred_stable.reliability_forecast.lower_bound:.4f}, {pred_stable.reliability_forecast.upper_bound:.4f}]"
    )
    print(f"  Trend Classification:   {pred_stable.risk_forecast.trend.value}")
    print(f"  Risk Score:             {pred_stable.risk_forecast.risk_score:.4f}")
    print(f"  Forecast Confidence:    {pred_stable.confidence.confidence:.4f}")

    # Scenario B: Degrading Trend
    print("\n[2/2] Forecasting for Degrading Historical Telemetry...")
    degrading_history = [0.96, 0.93, 0.89, 0.84, 0.79]
    pred_degrading = integrator.predict_reliability(
        degrading_history, target_id="pipeline_degrading"
    )
    print(f"  Historical Reliability: {degrading_history}")
    print(
        f"  Forecasted Reliability: {pred_degrading.reliability_forecast.forecasted_value:.4f}"
    )
    print(
        f"  Confidence Interval:    [{pred_degrading.reliability_forecast.lower_bound:.4f}, {pred_degrading.reliability_forecast.upper_bound:.4f}]"
    )
    print(f"  Trend Classification:   {pred_degrading.risk_forecast.trend.value}")
    print(f"  Risk Score:             {pred_degrading.risk_forecast.risk_score:.4f}")
    print(f"  Forecast Confidence:    {pred_degrading.confidence.confidence:.4f}")

    print("\n" + "=" * 60)
    print("PREDICTION & FORECASTING DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
