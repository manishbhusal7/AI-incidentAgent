"""Guardrail policy definitions — allow / deny action catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionPolicy:
    name: str
    allowed_autonomous: bool
    description: str
    requires_min_confidence: float = 90.0


# Actions the SRE agent may propose
ACTION_POLICIES: dict[str, ActionPolicy] = {
    "restart_service": ActionPolicy(
        name="restart_service",
        allowed_autonomous=True,
        description="Force a safe service restart (cold-start recycle of Lambda).",
        requires_min_confidence=90.0,
    ),
    "scale_service": ActionPolicy(
        name="scale_service",
        allowed_autonomous=True,
        description="Scale concurrency within hard-coded safe bounds.",
        requires_min_confidence=90.0,
    ),
    "rollback_deploy": ActionPolicy(
        name="rollback_deploy",
        allowed_autonomous=False,
        description="Rollback to previous deployment — requires human approval.",
        requires_min_confidence=90.0,
    ),
    "investigate_database": ActionPolicy(
        name="investigate_database",
        allowed_autonomous=False,
        description="Deeper DB investigation — notify humans; no auto change.",
        requires_min_confidence=90.0,
    ),
    "page_human": ActionPolicy(
        name="page_human",
        allowed_autonomous=True,
        description="Send SNS notification for human follow-up.",
        requires_min_confidence=0.0,
    ),
    "no_action": ActionPolicy(
        name="no_action",
        allowed_autonomous=True,
        description="Record findings only; take no remediation action.",
        requires_min_confidence=0.0,
    ),
}


# Explicitly blocked action patterns (substring match on normalized action name)
BLOCKED_ACTION_PATTERNS = (
    "delete",
    "destroy",
    "terminate",
    "remove_bucket",
    "drop_",
    "modify_iam",
    "iam_",
    "put_user_policy",
    "attach_role",
    "detach_role",
    "create_access_key",
    "wipe",
    "purge",
    "format_",
)
