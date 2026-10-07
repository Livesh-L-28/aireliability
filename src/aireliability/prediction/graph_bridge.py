"""Knowledge Graph synchronization bridge for Reliability Prediction (Phase 42 -> Phase 35)."""

from __future__ import annotations

from aireliability.graph.builder import KnowledgeGraphBuilder
from aireliability.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.prediction.models import ReliabilityPrediction


class PredictionGraphBridge:
    """Synchronizes prediction entities and forecasts into the Knowledge Graph."""

    def __init__(self, builder: KnowledgeGraphBuilder | None = None) -> None:
        self.builder = builder or KnowledgeGraphBuilder()

    def sync_prediction(self, prediction: ReliabilityPrediction) -> int:
        """Add prediction and forecast nodes with connecting edges."""
        nodes_added = 0

        # 1. Prediction Node
        pred_node = GraphNode.create(
            node_type=GraphNodeType.PREDICTION,
            source_id=prediction.prediction_id,
            name=f"Pred-{prediction.target_id}-{prediction.horizon.value}",
            metadata={
                "target_id": prediction.target_id,
                "horizon": prediction.horizon.value,
                "risk_score": prediction.risk_forecast.risk_score,
                "confidence": prediction.confidence.confidence,
            },
        )
        self.builder.graph.add_node(pred_node)
        nodes_added += 1

        # 2. Forecast Node
        forecast_node = GraphNode.create(
            node_type=GraphNodeType.FORECAST,
            source_id=f"fc_{prediction.prediction_id}",
            name=f"Forecast-{prediction.target_id}",
            metadata={
                "forecasted_reliability": prediction.reliability_forecast.forecasted_value,
                "lower_bound": prediction.reliability_forecast.lower_bound,
                "upper_bound": prediction.reliability_forecast.upper_bound,
            },
        )
        self.builder.graph.add_node(forecast_node)
        nodes_added += 1

        # Edge: PREDICTION -> PREDICTS -> FORECAST
        edge = GraphEdge(
            source_id=pred_node.node_id,
            target_id=forecast_node.node_id,
            relationship=GraphRelationship.PREDICTS,
        )
        self.builder.graph.add_edge(edge)

        return nodes_added
