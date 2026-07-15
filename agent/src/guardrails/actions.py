"""Safe action executors with hard blast-radius limits."""

from __future__ import annotations

import os
from typing import Any

from aws_clients import client


def restart_service() -> dict[str, Any]:
    """
    Safe restart simulation: bump an env var on the loan Lambda to force
    a new execution environment on subsequent cold starts.
    """
    function_name = os.environ.get("LOAN_FUNCTION_NAME")
    if not function_name:
        return {"ok": False, "error": "LOAN_FUNCTION_NAME not set"}

    lam = client("lambda")
    cfg = lam.get_function_configuration(FunctionName=function_name)
    env = cfg.get("Environment", {}).get("Variables", {}) or {}
    # Touches RESTART_TOKEN only — never modifies IAM, VPC, or code
    current = int(env.get("RESTART_TOKEN", "0") or 0)
    env["RESTART_TOKEN"] = str(current + 1)

    lam.update_function_configuration(
        FunctionName=function_name,
        Environment={"Variables": env},
    )
    return {
        "ok": True,
        "action": "restart_service",
        "function_name": function_name,
        "restart_token": env["RESTART_TOKEN"],
    }


def scale_service() -> dict[str, Any]:
    """
    Adjust reserved concurrency within a hard ceiling.
    Default: set reserved concurrency to min(current+1, MAX_SCALE_CEILING).
    """
    function_name = os.environ.get("LOAN_FUNCTION_NAME")
    if not function_name:
        return {"ok": False, "error": "LOAN_FUNCTION_NAME not set"}

    ceiling = int(os.environ.get("MAX_SCALE_CEILING", "3"))
    floor = int(os.environ.get("MIN_SCALE_FLOOR", "1"))
    lam = client("lambda")

    try:
        current_resp = lam.get_function_concurrency(FunctionName=function_name)
        current = int(current_resp.get("ReservedConcurrentExecutions") or floor)
    except Exception:  # noqa: BLE001
        current = floor

    target = min(current + 1, ceiling)
    target = max(target, floor)

    lam.put_function_concurrency(
        FunctionName=function_name,
        ReservedConcurrentExecutions=target,
    )
    return {
        "ok": True,
        "action": "scale_service",
        "function_name": function_name,
        "previous": current,
        "target": target,
        "ceiling": ceiling,
    }


def page_human(subject: str, message: str) -> dict[str, Any]:
    topic_arn = os.environ.get("SNS_TOPIC_ARN")
    if not topic_arn:
        return {"ok": False, "error": "SNS_TOPIC_ARN not set", "skipped": True}

    sns = client("sns")
    resp = sns.publish(TopicArn=topic_arn, Subject=subject[:100], Message=message[:4000])
    return {"ok": True, "action": "page_human", "message_id": resp.get("MessageId")}


EXECUTORS = {
    "restart_service": lambda: restart_service(),
    "scale_service": lambda: scale_service(),
    "page_human": lambda: page_human(
        "AI Incident Triage — Human Attention Required",
        "An incident requires human follow-up. Check S3 incident reports.",
    ),
    "no_action": lambda: {"ok": True, "action": "no_action", "message": "No changes made"},
}
