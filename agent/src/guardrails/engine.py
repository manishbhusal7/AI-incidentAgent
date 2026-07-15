"""
Guardrail Engine — separates model suggestions from permission to act.

Interview talking point:
- The LLM can recommend anything.
- This module alone decides whether an action is allowed / auto-executed.
- Blocked classes (delete, IAM mutation, data wipe) never auto-run.
"""

from __future__ import annotations

from models import GuardrailDecision
from guardrails.actions import EXECUTORS
from guardrails.policies import ACTION_POLICIES, BLOCKED_ACTION_PATTERNS


def normalize_action(action: str) -> str:
    return (action or "").strip().lower().replace(" ", "_").replace("-", "_")


def is_blocked(action: str) -> bool:
    normalized = normalize_action(action)
    if not normalized:
        return True
    for pattern in BLOCKED_ACTION_PATTERNS:
        if pattern in normalized:
            return True
    # Unknown actions that aren't in the catalog are treated as blocked for autonomy
    if normalized not in ACTION_POLICIES:
        return True
    return False


def evaluate(action: str, confidence_score: float, *, execute: bool = False) -> GuardrailDecision:
    """
    Approve automatically only when:
      confidence >= policy threshold (default 90)
      AND action is allowlisted for autonomy
      AND action is not blocked

    Otherwise require human approval (and never execute destructive intent).
    """
    normalized = normalize_action(action)
    confidence = float(confidence_score)

    if is_blocked(normalized) and normalized not in ACTION_POLICIES:
        decision = GuardrailDecision(
            approved=False,
            requires_human_approval=True,
            action=normalized,
            reason=f"Blocked or unknown action '{normalized}' — human approval required",
            confidence_score=confidence,
            executed=False,
        )
        return decision

    # Known action but matches blocked pattern (e.g. delete_*)
    if any(p in normalized for p in BLOCKED_ACTION_PATTERNS):
        return GuardrailDecision(
            approved=False,
            requires_human_approval=True,
            action=normalized,
            reason=f"Action '{normalized}' matches blocked pattern — refused",
            confidence_score=confidence,
            executed=False,
        )

    policy = ACTION_POLICIES[normalized]

    if not policy.allowed_autonomous:
        return GuardrailDecision(
            approved=False,
            requires_human_approval=True,
            action=normalized,
            reason=f"Action '{normalized}' is not allowed for autonomous execution",
            confidence_score=confidence,
            executed=False,
        )

    if confidence < policy.requires_min_confidence:
        return GuardrailDecision(
            approved=False,
            requires_human_approval=True,
            action=normalized,
            reason=(
                f"Confidence {confidence} < required {policy.requires_min_confidence} "
                f"for '{normalized}'"
            ),
            confidence_score=confidence,
            executed=False,
        )

    # Approved for autonomy
    execution_result = None
    executed = False
    if execute and normalized in EXECUTORS:
        execution_result = EXECUTORS[normalized]()
        executed = bool(execution_result.get("ok"))

    return GuardrailDecision(
        approved=True,
        requires_human_approval=False,
        action=normalized,
        reason=f"Auto-approved '{normalized}' at confidence {confidence}",
        confidence_score=confidence,
        executed=executed,
        execution_result=execution_result,
    )
