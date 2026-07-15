"""Agent investigation tools — registry + runners."""

from __future__ import annotations

from typing import Any, Callable

from tools.get_logs import get_logs
from tools.get_metrics import get_metrics
from tools.get_recent_deployments import get_recent_deployments

TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_logs": get_logs,
    "get_metrics": get_metrics,
    "get_recent_deployments": get_recent_deployments,
}


def run_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if name not in TOOL_HANDLERS:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    arguments = arguments or {}
    try:
        return TOOL_HANDLERS[name](**arguments)
    except TypeError as exc:
        return {"ok": False, "error": f"Invalid arguments for {name}: {exc}"}


__all__ = [
    "get_logs",
    "get_metrics",
    "get_recent_deployments",
    "run_tool",
    "TOOL_HANDLERS",
]
