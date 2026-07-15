"""Usage protection — limit Claude API calls via SSM counter."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from aws_clients import client


def _param_name() -> str:
    return os.environ.get(
        "USAGE_COUNTER_PARAM",
        "/ai-incident-triage-agent/dev/claude_usage",
    )


def check_budget() -> dict[str, Any]:
    """
    Returns {allowed: bool, count: int, limit: int, reason?: str}.
    If SSM is unavailable, fail open for local unit tests / fail closed in prod
    based on USAGE_FAIL_CLOSED.
    """
    limit = int(os.environ.get("MAX_CLAUDE_CALLS_PER_MONTH", "50"))
    fail_closed = os.environ.get("USAGE_FAIL_CLOSED", "false").lower() == "true"
    ssm = client("ssm")
    name = _param_name()
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        resp = ssm.get_parameter(Name=name)
        raw = resp["Parameter"]["Value"]
        # format: YYYY-MM:count
        if ":" in raw:
            stored_month, count_s = raw.split(":", 1)
            count = int(count_s)
            if stored_month != month:
                count = 0
        else:
            count = int(raw)
    except ssm.exceptions.ParameterNotFound:
        count = 0
    except Exception as exc:  # noqa: BLE001
        if fail_closed:
            return {"allowed": False, "count": -1, "limit": limit, "reason": str(exc)}
        return {"allowed": True, "count": 0, "limit": limit, "reason": f"ssm_error:{exc}"}

    if count >= limit:
        return {
            "allowed": False,
            "count": count,
            "limit": limit,
            "reason": f"Monthly Claude call budget exhausted ({count}/{limit})",
        }
    return {"allowed": True, "count": count, "limit": limit}


def increment_usage() -> None:
    limit_ignored = check_budget()  # noqa: F841 — refresh aware of month
    ssm = client("ssm")
    name = _param_name()
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    current = 0
    try:
        resp = ssm.get_parameter(Name=name)
        raw = resp["Parameter"]["Value"]
        if ":" in raw:
            stored_month, count_s = raw.split(":", 1)
            current = int(count_s) if stored_month == month else 0
        else:
            current = int(raw)
    except Exception:  # noqa: BLE001
        current = 0

    ssm.put_parameter(
        Name=name,
        Value=f"{month}:{current + 1}",
        Type="String",
        Overwrite=True,
    )
