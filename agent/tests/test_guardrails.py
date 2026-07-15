"""Guardrail engine unit tests — interview centerpiece."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from guardrails.engine import evaluate, is_blocked, normalize_action  # noqa: E402
from guardrails.policies import ACTION_POLICIES  # noqa: E402


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Restart Service", "restart_service"),
        ("scale-service", "scale_service"),
        ("PAGE_HUMAN", "page_human"),
    ],
)
def test_normalize_action(raw, expected):
    assert normalize_action(raw) == expected


@pytest.mark.parametrize(
    "action",
    [
        "delete_bucket",
        "delete_resources",
        "modify_iam",
        "iam_attach_policy",
        "destroy_database",
        "terminate_instances",
        "wipe_data",
        "purge_logs",
        "unknown_crazy_action",
        "",
    ],
)
def test_blocked_actions_require_human(action):
    assert is_blocked(normalize_action(action) or action)
    decision = evaluate(action, 99.0, execute=False)
    assert decision.approved is False
    assert decision.requires_human_approval is True
    assert decision.executed is False


@pytest.mark.parametrize("action", ["restart_service", "scale_service"])
def test_high_confidence_allowed_actions_auto_approve(action):
    decision = evaluate(action, 95.0, execute=False)
    assert decision.approved is True
    assert decision.requires_human_approval is False
    assert decision.executed is False


@pytest.mark.parametrize("action", ["restart_service", "scale_service"])
def test_low_confidence_requires_human(action):
    decision = evaluate(action, 80.0, execute=False)
    assert decision.approved is False
    assert decision.requires_human_approval is True


@pytest.mark.parametrize(
    "action",
    ["rollback_deploy", "investigate_database"],
)
def test_sensitive_actions_always_need_human_even_at_100(action):
    decision = evaluate(action, 100.0, execute=False)
    assert decision.approved is False
    assert decision.requires_human_approval is True


def test_page_human_allowed_at_low_confidence():
    decision = evaluate("page_human", 10.0, execute=False)
    assert decision.approved is True
    assert decision.requires_human_approval is False


def test_no_action_always_ok():
    decision = evaluate("no_action", 0.0, execute=False)
    assert decision.approved is True


def test_execute_no_action_sets_executed():
    decision = evaluate("no_action", 100.0, execute=True)
    assert decision.approved is True
    assert decision.executed is True
    assert decision.execution_result is not None
    assert decision.execution_result.get("ok") is True


def test_catalog_completeness():
    required = {
        "restart_service",
        "scale_service",
        "rollback_deploy",
        "investigate_database",
        "page_human",
        "no_action",
    }
    assert required.issubset(set(ACTION_POLICIES))


def test_boundary_confidence_90_approves_restart():
    decision = evaluate("restart_service", 90.0, execute=False)
    assert decision.approved is True


def test_boundary_confidence_89_9_rejects_restart():
    decision = evaluate("restart_service", 89.9, execute=False)
    assert decision.approved is False
