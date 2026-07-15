"""HTTP route handlers for the Loan Processing Service."""

from __future__ import annotations

import json
import time
from typing import Any

from chaos import apply_chaos, list_scenarios
from logging_utils import get_logger

logger = get_logger(__name__)


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def handle_health(request_id: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "loan-processing",
        "request_id": request_id,
        "status_code": 200,
    }


def handle_process_loan(event: dict[str, Any], request_id: str) -> dict[str, Any]:
    start = time.perf_counter()
    body = _parse_body(event)

    applicant = body.get("applicant_name", "unknown")
    amount = float(body.get("amount", 0))
    credit_score = int(body.get("credit_score", 0))

    logger.info(
        "loan_processing_started",
        extra={
            "request_id": request_id,
            "stage": "validate",
            "applicant": applicant,
            "amount": amount,
            "credit_score": credit_score,
        },
    )

    # Simulated underwriting decision (deterministic for demos)
    if amount <= 0:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "status_code": 400,
            "error": "invalid_amount",
            "request_id": request_id,
            "latency_ms": round(latency_ms, 2),
        }

    decision = "approved" if credit_score >= 650 and amount <= 750_000 else "declined"
    reason = (
        "credit_and_ltv_ok"
        if decision == "approved"
        else "credit_score_or_amount_threshold"
    )

    latency_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "loan_processing_completed",
        extra={
            "request_id": request_id,
            "stage": "complete",
            "decision": decision,
            "latency_ms": round(latency_ms, 2),
        },
    )

    return {
        "status_code": 200,
        "request_id": request_id,
        "decision": decision,
        "reason": reason,
        "applicant_name": applicant,
        "amount": amount,
        "credit_score": credit_score,
        "latency_ms": round(latency_ms, 2),
    }


def handle_chaos(path: str, request_id: str, demo_mode: bool) -> dict[str, Any]:
    if not demo_mode:
        return {
            "status_code": 403,
            "error": "chaos_disabled",
            "message": "DEMO_MODE is false",
            "request_id": request_id,
        }

    parts = path.strip("/").split("/")
    # Expected: chaos/{scenario}
    scenario = parts[1] if len(parts) > 1 else ""
    if not scenario or scenario == "list":
        return {
            "status_code": 200,
            "scenarios": list_scenarios(),
            "request_id": request_id,
        }

    start = time.perf_counter()
    apply_chaos(scenario, request_id=request_id)
    # apply_chaos either raises or sleep-injects; high latency returns normally
    latency_ms = (time.perf_counter() - start) * 1000
    return {
        "status_code": 200,
        "chaos": scenario,
        "message": f"Chaos scenario '{scenario}' applied",
        "request_id": request_id,
        "latency_ms": round(latency_ms, 2),
    }


def handle_request(
    *,
    method: str,
    path: str,
    event: dict[str, Any],
    request_id: str,
    demo_mode: bool,
) -> dict[str, Any]:
    normalized = path.rstrip("/") or "/"
    if method == "GET" and normalized in ("/health", "/"):
        return handle_health(request_id)
    if method == "POST" and normalized == "/process-loan":
        return handle_process_loan(event, request_id)
    # Interview Demo 2 primary trigger
    if method in ("GET", "POST") and normalized in ("/simulate-error", "/simulate-error/"):
        return handle_chaos("/chaos/db_pool_exhausted", request_id, demo_mode)
    if method in ("GET", "POST") and normalized.startswith("/chaos"):
        return handle_chaos(normalized, request_id, demo_mode)

    return {
        "status_code": 404,
        "error": "not_found",
        "path": path,
        "request_id": request_id,
    }
