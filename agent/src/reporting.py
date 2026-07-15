"""Write JSON + Markdown incident reports to S3 and notify via SNS."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from aws_clients import client
from models import GuardrailDecision, IncidentReport


def report_to_markdown(report: IncidentReport, decision: GuardrailDecision) -> str:
    evidence_lines = []
    for i, e in enumerate(report.evidence, 1):
        evidence_lines.append(f"{i}. **[{e.source}]** {e.summary}")

    tools = ", ".join(report.tool_calls_made) or "none"
    return f"""# Incident Report — {report.service}

**Generated:** {datetime.now(timezone.utc).isoformat()}
**Alarm:** {report.alarm_name or "n/a"}
**Confidence:** {report.confidence_score}
**Recommended action:** `{report.recommended_action}`

## Summary
{report.incident_summary}

## Root Cause
{report.root_cause}

## Evidence
{chr(10).join(evidence_lines) if evidence_lines else "_No evidence items_"}

## Guardrail Decision
- **Approved (autonomous):** {decision.approved}
- **Requires human approval:** {decision.requires_human_approval}
- **Reason:** {decision.reason}
- **Executed:** {decision.executed}
- **Execution result:** `{json.dumps(decision.execution_result)}`

## Tools Used
{tools}

## Model Notes
{report.raw_model_notes or "_n/a_"}
"""


def persist_report(
    report: IncidentReport,
    decision: GuardrailDecision,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bucket = os.environ.get("ARTIFACTS_BUCKET")
    if not bucket:
        return {"ok": False, "error": "ARTIFACTS_BUCKET not set"}

    incident_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    prefix = os.environ.get("REPORT_PREFIX", "incidents/")
    base = f"{prefix}{incident_id}"

    payload = {
        "incident_id": incident_id,
        "report": report.model_dump(),
        "guardrail": decision.model_dump(),
        "extra": extra or {},
    }
    markdown = report_to_markdown(report, decision)

    s3 = client("s3")
    json_key = f"{base}.json"
    md_key = f"{base}.md"
    s3.put_object(
        Bucket=bucket,
        Key=json_key,
        Body=json.dumps(payload, indent=2, default=str).encode("utf-8"),
        ContentType="application/json",
    )
    s3.put_object(
        Bucket=bucket,
        Key=md_key,
        Body=markdown.encode("utf-8"),
        ContentType="text/markdown",
    )

    notify = _notify(report, decision, json_key=json_key, md_key=md_key)
    return {
        "ok": True,
        "incident_id": incident_id,
        "json_key": json_key,
        "md_key": md_key,
        "bucket": bucket,
        "notify": notify,
    }


def _notify(
    report: IncidentReport,
    decision: GuardrailDecision,
    *,
    json_key: str,
    md_key: str,
) -> dict[str, Any]:
    topic = os.environ.get("SNS_TOPIC_ARN")
    if not topic:
        return {"skipped": True, "reason": "SNS_TOPIC_ARN not set"}

    subject = (
        "[HUMAN APPROVAL]" if decision.requires_human_approval else "[AUTO]"
    ) + f" Incident: {report.recommended_action}"
    message = (
        f"Summary: {report.incident_summary}\n"
        f"Root cause: {report.root_cause}\n"
        f"Confidence: {report.confidence_score}\n"
        f"Action: {report.recommended_action}\n"
        f"Guardrail: {decision.reason}\n"
        f"Report JSON: s3://{os.environ.get('ARTIFACTS_BUCKET')}/{json_key}\n"
        f"Report MD: s3://{os.environ.get('ARTIFACTS_BUCKET')}/{md_key}\n"
    )
    sns = client("sns")
    resp = sns.publish(TopicArn=topic, Subject=subject[:100], Message=message[:4000])
    return {"ok": True, "message_id": resp.get("MessageId")}
