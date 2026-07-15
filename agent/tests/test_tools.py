"""Tool unit tests with moto where practical."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from tools import run_tool  # noqa: E402


def test_unknown_tool():
    result = run_tool("drop_database", {})
    assert result["ok"] is False


def test_get_recent_deployments_without_bucket():
    with patch.dict("os.environ", {"ARTIFACTS_BUCKET": ""}, clear=False):
        # Ensure missing bucket is handled
        import os

        os.environ.pop("ARTIFACTS_BUCKET", None)
        result = run_tool("get_recent_deployments", {"limit": 2})
        assert result["ok"] is False
        assert "ARTIFACTS_BUCKET" in result["error"]
