"""Retrieve recent application logs from CloudWatch Logs."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from aws_clients import client


def get_logs(minutes: int = 15, filter_pattern: str | None = None) -> dict[str, Any]:
    minutes = max(1, min(int(minutes or 15), 60))
    max_events = int(os.environ.get("MAX_LOG_EVENTS", "50"))
    log_group = os.environ.get(
        "LOAN_LOG_GROUP",
        "/aws/lambda/ai-incident-triage-agent-loan-processing",
    )

    logs = client("logs")
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    kwargs: dict[str, Any] = {
        "logGroupName": log_group,
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000),
        "limit": max_events,
        "interleaved": True,
    }
    if filter_pattern:
        kwargs["filterPattern"] = filter_pattern
    else:
        kwargs["filterPattern"] = (
            "?ERROR ?Exception ?CHAOS ?timeout ?FATAL ?BAD_DEPLOY "
            "?POOL ?TRANSIENT ?database_error ?DB_CONNECTION"
        )

    try:
        resp = logs.filter_log_events(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "log_group": log_group,
            "events": [],
        }

    events = []
    total_bytes = 0
    max_bytes = int(os.environ.get("MAX_LOG_BYTES", "40000"))
    for event in resp.get("events", []):
        msg = event.get("message", "")
        total_bytes += len(msg.encode("utf-8"))
        if total_bytes > max_bytes:
            break
        events.append(
            {
                "timestamp": event.get("timestamp"),
                "message": msg[:2000],
                "logStreamName": event.get("logStreamName"),
            }
        )

    return {
        "ok": True,
        "log_group": log_group,
        "minutes": minutes,
        "count": len(events),
        "events": events,
    }
