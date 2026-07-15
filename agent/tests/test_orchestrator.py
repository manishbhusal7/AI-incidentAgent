"""Orchestrator + handler tests with mocked Claude / AWS."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

AGENT_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(AGENT_SRC))

from models import IncidentReport  # noqa: E402
from orchestrator import _extract_json, _heuristic_fallback, investigate  # noqa: E402


def _load_agent_handler():
    """Load agent handler by file path to avoid colliding with loan-processing handler.py."""
    path = AGENT_SRC / "handler.py"
    spec = importlib.util.spec_from_file_location("agent_handler_module", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Ensure agent package imports resolve while loading
    if str(AGENT_SRC) not in sys.path:
        sys.path.insert(0, str(AGENT_SRC))
    spec.loader.exec_module(mod)
    return mod


def test_extract_json_from_fenced_noise():
    text = (
        'Here you go:\n{"incident_summary":"x","root_cause":"y","evidence":[],'
        '"confidence_score":90,"recommended_action":"page_human"}\nThanks'
    )
    data = _extract_json(text)
    assert data["recommended_action"] == "page_human"


def test_heuristic_db_timeout():
    report = _heuristic_fallback({"alarm_name": "db-timeout-alarm", "reason": "DB timeout"}, [])
    assert report.recommended_action == "restart_service"
    assert report.confidence_score >= 60


def test_heuristic_pool_exhausted():
    report = _heuristic_fallback(
        {"alarm_name": "errors", "reason": "connection pool exhausted"},
        [],
    )
    assert report.recommended_action == "restart_service"
    assert report.confidence_score >= 90


@patch("orchestrator.check_budget", return_value={"allowed": False, "count": 99, "limit": 50})
def test_investigate_respects_budget(mock_budget):
    report = investigate({"alarm_name": "x", "reason": "latency spike"})
    assert isinstance(report, IncidentReport)
    assert report.raw_model_notes == "fallback_heuristic"


def test_handler_applies_guardrails():
    agent_handler = _load_agent_handler()
    mock_report = IncidentReport(
        incident_summary="test",
        root_cause="boom",
        evidence=[],
        confidence_score=95,
        recommended_action="restart_service",
        tool_calls_made=["get_logs"],
    )

    with (
        patch.object(agent_handler, "investigate", return_value=mock_report),
        patch.object(agent_handler, "persist_report", return_value={"ok": True, "incident_id": "abc"}),
        patch.dict("os.environ", {"AUTO_EXECUTE_APPROVED": "false"}),
    ):
        result = agent_handler.handler(
            {
                "detail": {
                    "alarmName": "LoanErrorsAlarm",
                    "state": {"value": "ALARM", "reason": "Threshold crossed"},
                }
            },
            None,
        )

    assert result["ok"] is True
    assert result["guardrail"]["approved"] is True
    assert result["report"]["recommended_action"] == "restart_service"


def test_parse_manual_event():
    agent_handler = _load_agent_handler()
    ctx = agent_handler._parse_alarm_context({"manual": True, "alarm_name": "demo"})
    assert ctx["alarm_name"] == "demo"
