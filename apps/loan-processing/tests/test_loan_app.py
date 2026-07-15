"""Unit tests for the Loan Processing Service."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from chaos import DatabaseConnectionTimeout, ApplicationFault  # noqa: E402
from handler import handler  # noqa: E402


def _event(method: str, path: str, body: dict | None = None, query: dict | None = None):
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "headers": {},
        "queryStringParameters": query,
        "requestContext": {"http": {"method": method, "path": path}},
        "body": json.dumps(body) if body is not None else None,
    }


def test_health():
    resp = handler(_event("GET", "/health"), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "ok"


def test_process_loan_approved():
    resp = handler(
        _event(
            "POST",
            "/process-loan",
            {"applicant_name": "Ada Lovelace", "amount": 250000, "credit_score": 740},
        ),
        None,
    )
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["decision"] == "approved"


def test_process_loan_declined():
    resp = handler(
        _event(
            "POST",
            "/process-loan",
            {"applicant_name": "Test User", "amount": 900000, "credit_score": 500},
        ),
        None,
    )
    body = json.loads(resp["body"])
    assert body["decision"] == "declined"


def test_chaos_db_timeout():
    resp = handler(_event("POST", "/chaos/db_timeout"), None)
    assert resp["statusCode"] == 500
    body = json.loads(resp["body"])
    assert body["error_code"] == "DatabaseConnectionTimeout"


def test_simulate_error_pool_exhausted():
    resp = handler(_event("POST", "/simulate-error"), None)
    assert resp["statusCode"] == 500
    body = json.loads(resp["body"])
    assert body["error_code"] == "DatabaseConnectionTimeout"
    assert "pool" in body["message"].lower()


def test_false_alarm_recovers():
    resp = handler(_event("POST", "/chaos/false_alarm"), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["chaos"] == "false_alarm"


def test_chaos_app_exception():
    resp = handler(_event("GET", "/chaos/app_exception"), None)
    assert resp["statusCode"] == 500
    assert json.loads(resp["body"])["error_code"] == "ApplicationFault"


def test_chaos_list():
    resp = handler(_event("GET", "/chaos/list"), None)
    assert resp["statusCode"] == 200
    assert "db_timeout" in json.loads(resp["body"])["scenarios"]


def test_not_found():
    resp = handler(_event("GET", "/nope"), None)
    assert resp["statusCode"] == 404
