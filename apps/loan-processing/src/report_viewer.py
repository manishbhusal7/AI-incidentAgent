"""Serve incident reports from S3 via a presentation-friendly HTML viewer."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import boto3

_VIEWER_HTML = Path(__file__).resolve().parent / "static" / "report_viewer.html"


def _bucket() -> str:
    bucket = os.environ.get("ARTIFACTS_BUCKET", "").strip()
    if not bucket:
        raise ValueError("ARTIFACTS_BUCKET not configured")
    return bucket


def _prefix() -> str:
    return os.environ.get("REPORT_PREFIX", "incidents/")


def _s3():
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def viewer_html() -> str:
    return _VIEWER_HTML.read_text(encoding="utf-8")


def list_reports(*, limit: int = 20) -> list[dict[str, Any]]:
    bucket = _bucket()
    prefix = _prefix()
    resp = _s3().list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=200)
    items = resp.get("Contents") or []
    json_objects = sorted(
        [o for o in items if o["Key"].endswith(".json")],
        key=lambda o: o["LastModified"],
        reverse=True,
    )[:limit]

    reports: list[dict[str, Any]] = []
    for obj in json_objects:
        key = obj["Key"]
        body = _s3().get_object(Bucket=bucket, Key=key)["Body"].read()
        payload = json.loads(body)
        report = payload.get("report") or {}
        guardrail = payload.get("guardrail") or {}
        incident_id = payload.get("incident_id") or key.rsplit("/", 1)[-1].replace(".json", "")
        reports.append(
            {
                "incident_id": incident_id,
                "json_key": key,
                "created_at": obj["LastModified"].isoformat(),
                "recommended_action": report.get("recommended_action"),
                "confidence_score": report.get("confidence_score"),
                "approved": guardrail.get("approved"),
                "executed": guardrail.get("executed"),
                "requires_human_approval": guardrail.get("requires_human_approval"),
                "summary": (report.get("incident_summary") or "")[:120],
            }
        )
    return reports


def get_report(*, json_key: str | None = None, latest: bool = False) -> dict[str, Any]:
    bucket = _bucket()
    prefix = _prefix()

    if latest:
        items = list_reports(limit=1)
        if not items:
            return {"status_code": 404, "error": "no_reports", "message": "No incident reports found"}
        json_key = items[0]["json_key"]
    elif not json_key:
        return {"status_code": 400, "error": "missing_key", "message": "Provide json_key or latest=1"}

    if not json_key.startswith(prefix) or ".." in json_key:
        return {"status_code": 400, "error": "invalid_key", "message": "Invalid report key"}

    body = _s3().get_object(Bucket=bucket, Key=json_key)["Body"].read()
    payload = json.loads(body)
    return {"status_code": 200, "report": payload, "json_key": json_key}


def handle_reports_api(path: str, query: dict[str, Any] | None) -> dict[str, Any]:
    query = query or {}
    normalized = path.rstrip("/")

    if normalized == "/reports/api/list":
        return {"status_code": 200, "reports": list_reports()}

    if normalized == "/reports/api/latest":
        return get_report(latest=True)

    if normalized == "/reports/api/report":
        key = query.get("key") or query.get("json_key")
        if not key:
            return {"status_code": 400, "error": "missing_key", "message": "Query param: key"}
        return get_report(json_key=key)

    return {"status_code": 404, "error": "not_found", "path": path}
