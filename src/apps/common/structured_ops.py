"""Small helpers for structured JSON operations returned by agents."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


class StructuredOpsError(ValueError):
    """Raised when a structured operation payload is invalid."""


def extract_json_object(text: str) -> dict[str, Any]:
    matches = JSON_BLOCK_RE.findall(text)
    if not matches:
        raise StructuredOpsError("missing fenced JSON block")
    try:
        payload = json.loads(matches[-1])
    except json.JSONDecodeError as exc:
        raise StructuredOpsError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise StructuredOpsError("JSON payload must be an object")
    return payload


def require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise StructuredOpsError(f"{key} must be a list")
    return value


def require_string(obj: dict[str, Any], key: str, required: bool = True) -> str:
    value = obj.get(key)
    if value is None:
        if required:
            raise StructuredOpsError(f"{key} is required")
        return ""
    if not isinstance(value, str):
        raise StructuredOpsError(f"{key} must be a string")
    value = value.strip()
    if required and not value:
        raise StructuredOpsError(f"{key} is required")
    return value


def safe_rel_path(root: Path, rel_path: str, *, suffix: str | None = None) -> Path:
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise StructuredOpsError("path is required")
    rel = Path(rel_path.strip())
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise StructuredOpsError(f"unsafe relative path: {rel_path}")
    if suffix and rel.suffix != suffix:
        raise StructuredOpsError(f"path must end with {suffix}: {rel_path}")
    path = (root / rel).resolve()
    root_resolved = root.resolve()
    try:
        path.relative_to(root_resolved)
    except ValueError as exc:
        raise StructuredOpsError(f"path escapes root: {rel_path}") from exc
    return path
