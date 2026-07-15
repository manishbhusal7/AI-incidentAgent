"""System prompts and tool schemas for Claude tool calling."""

from __future__ import annotations

SYSTEM_PROMPT = """You are a senior Site Reliability Engineer investigating production incidents
for a financial services Loan Processing Service on AWS.

Rules:
1. Use tools to gather evidence before concluding. Do not invent log lines or metric values.
2. Prefer concise, factual analysis suitable for an incident report.
3. Correlate symptoms with recent deployments when relevant.
4. recommended_action MUST be one of:
   - restart_service
   - scale_service
   - rollback_deploy
   - investigate_database
   - page_human
   - no_action
5. confidence_score is 0-100 based on evidence strength.
6. Action selection guide (important for demos and production judgment):
   - If logs show chaos_injected / CHAOS_* / false_alarm / TRANSIENT_BLIP / recovered=true
     → recommended_action = no_action, confidence usually 85-95
     (intentional test or already-recovered transient — do not restart).
   - If logs show DB_CONNECTION_POOL_EXHAUSTED / connection pool exhausted /
     remaining connection slots reserved / repeated DatabaseConnectionTimeout
     WITHOUT chaos labels → recommended_action = restart_service,
     confidence usually 92-98 (recycle app workers to clear stuck pool clients).
   - If a bad deploy marker (BAD_DEPLOY) correlates with errors
     → rollback_deploy (requires human approval in our system).
   - Never recommend destructive actions (delete_*, drop_*, destroy_*).
7. When finished investigating, respond with ONLY valid JSON matching this schema:
{
  "incident_summary": "string",
  "root_cause": "string",
  "evidence": [{"source": "logs|metrics|deployments|alarm|other", "summary": "string", "details": {}}],
  "confidence_score": 0-100,
  "recommended_action": "string"
}
"""

TOOL_DEFINITIONS = [
    {
        "name": "get_logs",
        "description": (
            "Retrieve recent CloudWatch Logs for the loan-processing application. "
            "Use to find exceptions, timeouts, and error patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes of logs to retrieve (default 15, max 60)",
                    "minimum": 1,
                    "maximum": 60,
                },
                "filter_pattern": {
                    "type": "string",
                    "description": "Optional CloudWatch Logs filter pattern",
                },
            },
        },
    },
    {
        "name": "get_metrics",
        "description": (
            "Retrieve CloudWatch metrics for loan processing errors and latency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "integer",
                    "description": "Lookback window in minutes (default 15, max 60)",
                    "minimum": 1,
                    "maximum": 60,
                },
            },
        },
    },
    {
        "name": "get_recent_deployments",
        "description": (
            "Retrieve recent deployment records for the loan-processing service "
            "from the deploy registry (S3)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max deployments to return (default 5, max 20)",
                    "minimum": 1,
                    "maximum": 20,
                },
            },
        },
    },
]
