"""CloudWatch metric emission via Embedded Metric Format (EMF)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone


def emit_metric(name: str, value: float, unit: str = "Count") -> None:
    """Emit a custom metric using CloudWatch EMF (no extra API call cost)."""
    namespace = os.environ.get("METRIC_NAMESPACE", "LoanProcessing")
    service = os.environ.get("SERVICE_NAME", "loan-processing")
    payload = {
        "_aws": {
            "Timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [["Service"]],
                    "Metrics": [{"Name": name, "Unit": unit}],
                }
            ],
        },
        "Service": service,
        name: value,
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()
