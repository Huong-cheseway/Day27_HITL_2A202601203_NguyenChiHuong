"""Shared state and audit schemas for the HITL workflow."""

from typing import TypedDict

from pydantic import BaseModel, Field


class GraphState(TypedDict):
    """Persistent data passed between nodes in the LangGraph workflow."""

    customer_id: str
    proposed_action: str
    confidence_score: float
    reasoning: str
    human_decision: str | None


class AuditEntry(BaseModel):
    """One traceable agent or human decision in the audit trail."""

    timestamp: str
    agent_id: str
    action: str
    confidence: float = Field(ge=0.0, le=1.0)
    reviewer_id: str
    decision: str

