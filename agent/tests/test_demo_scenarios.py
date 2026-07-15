"""Interview demo scenario unit tests (handler-level)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

AGENT_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(AGENT_SRC))

from models import IncidentReport  # noqa: E402


def _load_agent_handler():
    path = AGENT_SRC / "handler.py"
    spec = importlib.util.spec_from_file_location("agent_handler_demo", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_demo_dangerous_blocked():
    agent_handler = _load_agent_handler()
    with patch.object(agent_handler, "persist_report", return_value={"ok": True}):
        result = agent_handler.handler(
            {
                "manual": True,
                "demo_scenario": "dangerous",
                "alarm_name": "critical",
            },
            None,
        )
    assert result["report"]["recommended_action"] == "delete_database"
    assert result["guardrail"]["approved"] is False
    assert result["guardrail"]["requires_human_approval"] is True
    assert result["guardrail"]["executed"] is False


def test_demo_recoverable_auto_restarts():
    agent_handler = _load_agent_handler()
    mock_report = IncidentReport(
        incident_summary="pool issue",
        root_cause="timeout",
        evidence=[],
        confidence_score=80,
        recommended_action="page_human",  # model wrong — demo stabilizer fixes
        tool_calls_made=["get_logs"],
    )
    with (
        patch.object(agent_handler, "investigate", return_value=mock_report),
        patch.object(agent_handler, "persist_report", return_value={"ok": True}),
        patch.dict("os.environ", {"AUTO_EXECUTE_APPROVED": "false"}),
    ):
        result = agent_handler.handler(
            {"manual": True, "demo_scenario": "recoverable", "alarm_name": "errors"},
            None,
        )
    assert result["report"]["recommended_action"] == "restart_service"
    assert result["report"]["confidence_score"] >= 96
    assert result["guardrail"]["approved"] is True


def test_demo_false_alarm_no_action():
    agent_handler = _load_agent_handler()
    mock_report = IncidentReport(
        incident_summary="maybe restart",
        root_cause="noise",
        evidence=[],
        confidence_score=70,
        recommended_action="restart_service",
        tool_calls_made=["get_logs"],
    )
    with (
        patch.object(agent_handler, "investigate", return_value=mock_report),
        patch.object(agent_handler, "persist_report", return_value={"ok": True}),
        patch.dict("os.environ", {"AUTO_EXECUTE_APPROVED": "false"}),
    ):
        result = agent_handler.handler(
            {"manual": True, "demo_scenario": "false_alarm", "alarm_name": "errors"},
            None,
        )
    assert result["report"]["recommended_action"] == "no_action"
    assert result["guardrail"]["approved"] is True
