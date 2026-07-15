"""Pydantic models for incident reports and agent I/O."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source: Literal["logs", "metrics", "deployments", "alarm", "other"]
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class IncidentReport(BaseModel):
    incident_summary: str
    root_cause: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence_score: float = Field(ge=0, le=100)
    recommended_action: str
    alarm_name: str | None = None
    service: str = "loan-processing"
    tool_calls_made: list[str] = Field(default_factory=list)
    raw_model_notes: str | None = None


class GuardrailDecision(BaseModel):
    approved: bool
    requires_human_approval: bool
    action: str
    reason: str
    confidence_score: float
    executed: bool = False
    execution_result: dict[str, Any] | None = None
