"""Shared boto3 client helpers."""

from __future__ import annotations

import os

import boto3


def region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def client(service: str):
    return boto3.client(service, region_name=region())
