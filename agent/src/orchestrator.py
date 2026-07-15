"""Claude tool-calling orchestrator for incident triage."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from models import EvidenceItem, IncidentReport
from prompts import SYSTEM_PROMPT, TOOL_DEFINITIONS
from tools import run_tool
from usage import check_budget, increment_usage


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    # Prefer SSM SecureString
    param = os.environ.get("ANTHROPIC_API_KEY_PARAM")
    if param:
        from aws_clients import client

        ssm = client("ssm")
        resp = ssm.get_parameter(Name=param, WithDecryption=True)
        return resp["Parameter"]["Value"]

    raise RuntimeError("ANTHROPIC_API_KEY or ANTHROPIC_API_KEY_PARAM must be set")


def _heuristic_fallback(alarm_context: dict[str, Any], tool_trace: list[str]) -> IncidentReport:
    """Used when Claude budget is exhausted or API unavailable — still demoable."""
    state_reason = json.dumps(alarm_context)[:500]
    root = "Insufficient model budget or API error; heuristic triage only"
    action = "page_human"
    confidence = 40.0

    blob = state_reason.lower()
    if "pool" in blob or "exhausted" in blob:
        root = "Database connection pool exhausted (heuristic)"
        action = "restart_service"
        confidence = 94.0
    elif "false_alarm" in blob or "transient" in blob or "blip" in blob:
        root = "Transient recovered error / false alarm (heuristic)"
        action = "no_action"
        confidence = 90.0
    elif "db" in blob or "timeout" in blob:
        root = "Probable database connectivity timeout (heuristic)"
        action = "restart_service"
        confidence = 92.0
    elif "latency" in blob:
        root = "Elevated processing latency (heuristic)"
        action = "scale_service"
        confidence = 65.0
    elif "deploy" in blob or "bad_deploy" in blob:
        root = "Recent deployment correlation suspected (heuristic)"
        action = "rollback_deploy"
        confidence = 75.0
    elif "exception" in blob or "error" in blob:
        root = "Application exception pattern detected (heuristic)"
        action = "restart_service"
        confidence = 60.0

    return IncidentReport(
        incident_summary="Automated heuristic triage (Claude unavailable or budget blocked)",
        root_cause=root,
        evidence=[
            EvidenceItem(
                source="alarm",
                summary="Alarm / event context",
                details={"alarm_context": alarm_context},
            )
        ],
        confidence_score=confidence,
        recommended_action=action,
        alarm_name=(alarm_context.get("alarm_name") if isinstance(alarm_context, dict) else None),
        tool_calls_made=tool_trace,
        raw_model_notes="fallback_heuristic",
    )


def investigate(alarm_context: dict[str, Any]) -> IncidentReport:
    budget = check_budget()
    tool_trace: list[str] = []

    if not budget.get("allowed", True):
        return _heuristic_fallback(alarm_context, tool_trace)

    try:
        import anthropic
    except ImportError:
        return _heuristic_fallback(alarm_context, tool_trace)

    model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    max_rounds = int(os.environ.get("MAX_TOOL_ROUNDS", "4"))
    max_tokens = int(os.environ.get("CLAUDE_MAX_TOKENS", "1024"))

    try:
        api_key = _get_api_key()
    except Exception:
        return _heuristic_fallback(alarm_context, tool_trace)

    client_ai = anthropic.Anthropic(api_key=api_key)

    user_message = (
        "Investigate this production incident. Use tools as needed, then return ONLY JSON.\n\n"
        f"Alarm/Event context:\n{json.dumps(alarm_context, default=str)}"
    )

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    try:
        increment_usage()
    except Exception:
        # Usage counter is best-effort; do not fail triage
        pass

    try:
        for _ in range(max_rounds):
            response = client_ai.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            # Collect assistant content blocks for message history
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            tool_uses = [b for b in assistant_content if getattr(b, "type", None) == "tool_use"]
            text_blocks = [b for b in assistant_content if getattr(b, "type", None) == "text"]

            if tool_uses:
                tool_results = []
                for tu in tool_uses:
                    tool_trace.append(tu.name)
                    result = run_tool(tu.name, tu.input if isinstance(tu.input, dict) else {})
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": json.dumps(result, default=str)[:35000],
                        }
                    )
                messages.append({"role": "user", "content": tool_results})
                continue

            # No more tools — parse final JSON
            text = "\n".join(getattr(b, "text", "") for b in text_blocks).strip()
            try:
                data = _extract_json(text)
                evidence = [
                    EvidenceItem(**e) if not isinstance(e, EvidenceItem) else e
                    for e in data.get("evidence", [])
                ]
                return IncidentReport(
                    incident_summary=data.get("incident_summary", "No summary"),
                    root_cause=data.get("root_cause", "Unknown"),
                    evidence=evidence,
                    confidence_score=float(data.get("confidence_score", 50)),
                    recommended_action=data.get("recommended_action", "page_human"),
                    alarm_name=alarm_context.get("alarm_name"),
                    tool_calls_made=tool_trace,
                    raw_model_notes=text[:2000],
                )
            except Exception as exc:  # noqa: BLE001
                return IncidentReport(
                    incident_summary="Model returned unparseable output",
                    root_cause=f"JSON parse failure: {exc}",
                    evidence=[
                        EvidenceItem(
                            source="other",
                            summary="Raw model text",
                            details={"text": text[:1500]},
                        )
                    ],
                    confidence_score=30,
                    recommended_action="page_human",
                    alarm_name=alarm_context.get("alarm_name"),
                    tool_calls_made=tool_trace,
                    raw_model_notes=text[:2000],
                )

        return _heuristic_fallback(alarm_context, tool_trace)
    except Exception as exc:  # noqa: BLE001 — invalid key, network, etc.
        fallback = _heuristic_fallback(alarm_context, tool_trace)
        fallback.raw_model_notes = f"fallback_after_claude_error: {exc}"
        return fallback
