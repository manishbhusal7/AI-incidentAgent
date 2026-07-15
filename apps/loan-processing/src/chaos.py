"""Intentional failure injection for interview demos."""

from __future__ import annotations

import os
import time

from logging_utils import get_logger

logger = get_logger(__name__)

SCENARIOS = {
    "false_alarm": "Transient single-error blip that recovers (Demo 1 — no action)",
    "db_timeout": "Legacy chaos DB timeout (labeled as chaos)",
    "db_pool_exhausted": "Production-like DB connection pool exhaustion (Demo 2 — restart)",
    "simulate_error": "Alias for db_pool_exhausted (Demo 2)",
    "high_latency": "Inject artificial processing delay",
    "app_exception": "Raise an application exception",
    "failed_deploy": "Mark request as coming from a bad deploy marker",
}


class DatabaseConnectionTimeout(Exception):
    """Simulated DB connectivity failure."""


class ApplicationFault(Exception):
    """Simulated unhandled application fault."""


def list_scenarios() -> dict[str, str]:
    return dict(SCENARIOS)


def apply_chaos(scenario: str, *, request_id: str) -> None:
    scenario = (scenario or "").strip().lower().replace("-", "_")
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown chaos scenario: {scenario}. Valid: {list(SCENARIOS)}")

    if scenario == "simulate_error":
        scenario = "db_pool_exhausted"

    if scenario == "false_alarm":
        logger.warning(
            "transient_error_recovered",
            extra={
                "request_id": request_id,
                "stage": "complete",
                "error_code": "TRANSIENT_BLIP",
                "chaos_scenario": "false_alarm",
                "deploy_version": os.environ.get("DEPLOY_VERSION", "unknown"),
                "recovered": True,
                "note": "Single transient blip; subsequent health checks OK",
            },
        )
        logger.info(
            "loan_processing_completed",
            extra={
                "request_id": request_id,
                "stage": "complete",
                "decision": "approved",
                "latency_ms": 12.0,
            },
        )
        return

    if scenario == "db_pool_exhausted":
        logger.error(
            "database_error",
            extra={
                "request_id": request_id,
                "stage": "db_checkout",
                "error_code": "DB_CONNECTION_POOL_EXHAUSTED",
                "deploy_version": os.environ.get("DEPLOY_VERSION", "unknown"),
            },
        )
        logger.error(
            "unhandled_exception",
            extra={
                "request_id": request_id,
                "stage": "error",
                "error_code": "DatabaseConnectionTimeout",
                "error_message": (
                    "FATAL: remaining connection slots are reserved for non-replication "
                    "superuser connections; connection pool exhausted after 5000ms "
                    "(loan_db pool size=20, active=20, waiting=47)"
                ),
            },
        )
        time.sleep(0.05)
        raise DatabaseConnectionTimeout(
            "FATAL: remaining connection slots are reserved for non-replication "
            "superuser connections; connection pool exhausted after 5000ms "
            "(loan_db pool size=20, active=20, waiting=47)"
        )

    logger.error(
        "chaos_injected",
        extra={
            "request_id": request_id,
            "stage": "chaos",
            "error_code": f"CHAOS_{scenario.upper()}",
            "chaos_scenario": scenario,
            "deploy_version": os.environ.get("DEPLOY_VERSION", "unknown"),
        },
    )

    if scenario == "db_timeout":
        time.sleep(0.05)
        raise DatabaseConnectionTimeout(
            "FATAL: connection to loan_db timed out after 5000ms "
            "(could not connect to host loan-db.internal port 5432)"
        )

    if scenario == "high_latency":
        delay = float(os.environ.get("CHAOS_LATENCY_SECONDS", "3"))
        time.sleep(delay)
        logger.warning(
            "high_latency_injected",
            extra={
                "request_id": request_id,
                "stage": "chaos",
                "latency_ms": delay * 1000,
                "chaos_scenario": scenario,
            },
        )
        return

    if scenario == "app_exception":
        raise ApplicationFault(
            "NullReference in UnderwritingEngine.calculate_dti: expected applicant.income"
        )

    if scenario == "failed_deploy":
        os.environ["BAD_DEPLOY_ACTIVE"] = "true"
        raise ApplicationFault(
            "BAD_DEPLOY: underwriting feature flag 'new_pricing_v2' caused "
            "TypeError after deploy; rollback recommended"
        )
