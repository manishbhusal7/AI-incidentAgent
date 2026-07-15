"""Retrieve CloudWatch metrics for the loan service."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from aws_clients import client


def get_metrics(minutes: int = 15) -> dict[str, Any]:
    minutes = max(1, min(int(minutes or 15), 60))
    namespace = os.environ.get("METRIC_NAMESPACE", "LoanProcessing")
    service = os.environ.get("SERVICE_NAME", "loan-processing")
    cw = client("cloudwatch")

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    period = 60

    metric_names = ["LoanErrors", "ProcessingLatencyMs", "LoanProcessed"]
    results: dict[str, Any] = {}

    for metric_name in metric_names:
        try:
            stats = ["Sum"] if metric_name != "ProcessingLatencyMs" else ["Average", "Maximum"]
            resp = cw.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=[{"Name": "Service", "Value": service}],
                StartTime=start,
                EndTime=end,
                Period=period,
                Statistics=stats,
            )
            datapoints = sorted(resp.get("Datapoints", []), key=lambda d: d["Timestamp"])
            cleaned = []
            for dp in datapoints[-20:]:
                item = {"Timestamp": dp["Timestamp"].isoformat()}
                for k in ("Sum", "Average", "Maximum", "SampleCount"):
                    if k in dp:
                        item[k] = float(dp[k])
                cleaned.append(item)
            results[metric_name] = cleaned
        except Exception as exc:  # noqa: BLE001
            results[metric_name] = {"error": str(exc)}

    alarm_name = os.environ.get("PRIMARY_ALARM_NAME")
    alarm_info = None
    if alarm_name:
        try:
            alarms = cw.describe_alarms(AlarmNames=[alarm_name])
            if alarms.get("MetricAlarms"):
                a = alarms["MetricAlarms"][0]
                alarm_info = {
                    "AlarmName": a.get("AlarmName"),
                    "StateValue": a.get("StateValue"),
                    "StateReason": a.get("StateReason"),
                }
        except Exception as exc:  # noqa: BLE001
            alarm_info = {"error": str(exc)}

    return {
        "ok": True,
        "namespace": namespace,
        "service": service,
        "minutes": minutes,
        "metrics": results,
        "alarm": alarm_info,
    }
