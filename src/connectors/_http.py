"""Shared HTTP helpers for MCP connector servers."""

from __future__ import annotations

import json
import os

import requests


def google_access_token() -> str:
    return json.load(open(os.environ["GOOGLE_TOKEN_PATH"]))["access_token"]


def outlook_access_token() -> str:
    return json.load(open(os.environ["OUTLOOK_TOKEN_PATH"]))["access_token"]


def google_get(url: str, params: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {google_access_token()}"}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def outlook_get(url: str, params: dict | None = None, extra_headers: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {outlook_access_token()}"}
    if extra_headers:
        headers.update(extra_headers)
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()
