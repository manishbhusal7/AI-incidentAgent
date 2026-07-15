"""Read recent deployments from the S3 deploy registry."""

from __future__ import annotations

import json
import os
from typing import Any

from aws_clients import client


def get_recent_deployments(limit: int = 5) -> dict[str, Any]:
    limit = max(1, min(int(limit or 5), 20))
    bucket = os.environ.get("ARTIFACTS_BUCKET")
    prefix = os.environ.get("DEPLOY_PREFIX", "deploys/")

    if not bucket:
        return {
            "ok": False,
            "error": "ARTIFACTS_BUCKET not configured",
            "deployments": [],
        }

    s3 = client("s3")
    try:
        listed = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "deployments": []}

    contents = listed.get("Contents") or []
    contents = sorted(contents, key=lambda o: o["LastModified"], reverse=True)

    deployments = []
    for obj in contents[: limit * 2]:
        key = obj["Key"]
        if key.endswith("/"):
            continue
        try:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
            data = json.loads(body)
            data["_s3_key"] = key
            data["_last_modified"] = obj["LastModified"].isoformat()
            deployments.append(data)
        except Exception as exc:  # noqa: BLE001
            deployments.append({"_s3_key": key, "error": str(exc)})
        if len(deployments) >= limit:
            break

    return {
        "ok": True,
        "bucket": bucket,
        "prefix": prefix,
        "count": len(deployments),
        "deployments": deployments,
    }
