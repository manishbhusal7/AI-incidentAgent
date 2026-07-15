"""Loan Processing Service — Lambda handler for API Gateway HTTP API."""

from __future__ import annotations

import json
import os
from typing import Any

from chaos import apply_chaos
from logging_utils import get_logger, new_request_id
from metrics import emit_metric
from routes import handle_request

logger = get_logger(__name__)


def _response(status: int, body: dict[str, Any] | str, *, content_type: str = "application/json") -> dict[str, Any]:
    if content_type == "text/html":
        return {
            "statusCode": status,
            "headers": {
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-store",
            },
            "body": body if isinstance(body, str) else str(body),
        }
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(body),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint (API Gateway HTTP API payload format 2.0)."""
    request_id = new_request_id()
    method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "GET"
    )
    path = event.get("rawPath") or event.get("path") or "/"
    demo_mode = os.environ.get("DEMO_MODE", "true").lower() == "true"

    logger.info(
        "request_received",
        extra={
            "request_id": request_id,
            "method": method,
            "path": path,
            "stage": "ingress",
        },
    )

    try:
        # Chaos can be applied globally via query/header, or via /chaos/{scenario}
        chaos_header = None
        headers = event.get("headers") or {}
        for k, v in headers.items():
            if k.lower() == "x-chaos-scenario":
                chaos_header = v
                break

        query = event.get("queryStringParameters") or {}
        chaos_scenario = chaos_header or query.get("chaos")

        if chaos_scenario and demo_mode:
            apply_chaos(chaos_scenario, request_id=request_id)

        result = handle_request(
            method=method,
            path=path,
            event=event,
            request_id=request_id,
            demo_mode=demo_mode,
        )
        emit_metric("LoanProcessed", 1, unit="Count")
        if result.get("latency_ms") is not None:
            emit_metric("ProcessingLatencyMs", float(result["latency_ms"]), unit="Milliseconds")

        status = int(result.pop("status_code", 200))
        html_body = result.pop("body", None)
        content_type = result.pop("content_type", "application/json")
        if content_type == "text/html" and isinstance(html_body, str):
            return _response(status, html_body, content_type=content_type)
        return _response(status, result, content_type=content_type)

    except Exception as exc:  # noqa: BLE001 — intentional for demo error surface
        logger.exception(
            "unhandled_exception",
            extra={
                "request_id": request_id,
                "stage": "error",
                "error_code": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        emit_metric("LoanErrors", 1, unit="Count")
        return _response(
            500,
            {
                "error": "internal_error",
                "error_code": type(exc).__name__,
                "message": str(exc),
                "request_id": request_id,
            },
        )
