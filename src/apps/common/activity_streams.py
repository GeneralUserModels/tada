"""Shared filtered activity stream parsing, rendering, merging, and chunking."""

from __future__ import annotations

import heapq
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

DEFAULT_FILTERED_STREAM_SOURCES = [
    "screen/filtered.jsonl",
    "email/filtered.jsonl",
    "calendar/filtered.jsonl",
    "notifications/filtered.jsonl",
    "filesys/filtered.jsonl",
]
DEFAULT_VALUE_MAX_CHARS = 700


@dataclass(frozen=True)
class ActivityRow:
    timestamp: datetime
    timestamp_value: float
    rel_path: str
    line_no: int
    source_name: str
    entry: dict[str, Any]


@dataclass(frozen=True)
class RenderedActivityRow:
    row: ActivityRow
    text: str


@dataclass(frozen=True)
class ActivityChunk:
    index: int
    rows: list[RenderedActivityRow]

    @property
    def rendered_text(self) -> str:
        return "\n\n".join(row.text for row in self.rows)

    @property
    def metadata(self) -> str:
        if not self.rows:
            return "Rows: 0"
        timestamps = [row.row.timestamp for row in self.rows]
        sources = Counter(row.row.source_name for row in self.rows)
        source_summary = ", ".join(f"{name}={count}" for name, count in sorted(sources.items()))
        return (
            f"Chunk: {self.index}\n"
            f"Rows: {len(self.rows)}\n"
            f"Time range: {min(timestamps).strftime('%Y-%m-%d %H:%M:%S')} to "
            f"{max(timestamps).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Sources: {source_summary}"
        )


def parse_timestamp(value: Any) -> tuple[datetime, float] | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value), float(value)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
        return parsed, parsed.timestamp()
    return None


def iter_filtered_rows(path: Path, rel_path: str, since: datetime | None) -> Iterator[ActivityRow]:
    if not path.exists() or not path.is_file():
        return
    with path.open(errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            parsed_ts = parse_timestamp(entry.get("timestamp"))
            if parsed_ts is None:
                continue
            ts, ts_value = parsed_ts
            if since is not None and ts <= since:
                continue
            source_name = str(entry.get("source_name") or rel_path.split("/", 1)[0])
            yield ActivityRow(
                timestamp=ts,
                timestamp_value=ts_value,
                rel_path=rel_path,
                line_no=line_no,
                source_name=source_name,
                entry=entry,
            )


def merge_filtered_streams(
    logs_path: Path,
    since: datetime | None,
    rel_paths: list[str] | None = None,
) -> Iterator[ActivityRow]:
    heap: list[tuple[float, int, ActivityRow, Iterator[ActivityRow]]] = []
    seq = 0
    for rel_path in rel_paths or DEFAULT_FILTERED_STREAM_SOURCES:
        iterator = iter(iter_filtered_rows(logs_path / rel_path, rel_path, since))
        try:
            row = next(iterator)
        except StopIteration:
            continue
        heapq.heappush(heap, (row.timestamp_value, seq, row, iterator))
        seq += 1

    while heap:
        _, _, row, iterator = heapq.heappop(heap)
        yield row
        try:
            next_row = next(iterator)
        except StopIteration:
            continue
        heapq.heappush(heap, (next_row.timestamp_value, seq, next_row, iterator))
        seq += 1


def clean_scalar(value: Any, max_chars: int = DEFAULT_VALUE_MAX_CHARS) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return " ".join(str(value).split())[:max_chars]
    if isinstance(value, dict):
        if "dateTime" in value:
            return clean_scalar(value.get("dateTime"), max_chars=max_chars)
        if "date" in value:
            return clean_scalar(value.get("date"), max_chars=max_chars)
    return ""


def source_summary(entry: dict[str, Any], max_chars: int = DEFAULT_VALUE_MAX_CHARS) -> dict[str, str]:
    source = entry.get("source")
    if not isinstance(source, dict):
        return {}
    preferred = [
        "id",
        "summary",
        "subject",
        "from",
        "sender",
        "path",
        "type",
        "start",
        "end",
        "location",
        "description",
        "screenshot_path",
    ]
    result: dict[str, str] = {}
    for key in preferred:
        value = clean_scalar(source.get(key), max_chars=max_chars)
        if value:
            result[f"source.{key}"] = value
    for key, value in source.items():
        if key in preferred or key == "raw_events" or len(result) >= 12:
            continue
        clean = clean_scalar(value, max_chars=max_chars)
        if clean:
            result[f"source.{key}"] = clean
    return result


def row_text(entry: dict[str, Any], max_chars: int = DEFAULT_VALUE_MAX_CHARS) -> str:
    text = clean_scalar(entry.get("text"), max_chars=max_chars)
    if text:
        return text
    source = entry.get("source")
    if isinstance(source, dict):
        summary = clean_scalar(source.get("summary"), max_chars=max_chars)
        if summary:
            return summary
    return "(no text)"


def render_activity_row(row: ActivityRow, max_chars: int = DEFAULT_VALUE_MAX_CHARS) -> str:
    entry = row.entry
    fields: list[tuple[str, str]] = [
        ("time", row.timestamp.strftime("%Y-%m-%d %H:%M:%S")),
        ("source", row.source_name),
        ("source_file", f"{row.rel_path}:{row.line_no}"),
        ("text", row_text(entry, max_chars=max_chars)),
    ]
    dense_caption = clean_scalar(entry.get("dense_caption"), max_chars=max_chars)
    if dense_caption:
        fields.append(("dense_caption", dense_caption))
    img_path = clean_scalar(entry.get("img_path"), max_chars=max_chars)
    if img_path:
        fields.append(("img_path", img_path))
    fields.extend(source_summary(entry, max_chars=max_chars).items())
    return "\n".join(f"{key}: {value}" for key, value in fields if value)


def overlap_tail(rows: list[RenderedActivityRow], overlap_chars: int) -> list[RenderedActivityRow]:
    if overlap_chars <= 0:
        return []
    total = 0
    keep: list[RenderedActivityRow] = []
    for row in reversed(rows):
        total += len(row.text) + 2
        keep.append(row)
        if total >= overlap_chars:
            break
    keep.reverse()
    return keep


def chunk_activity_rows(
    rows: Iterator[ActivityRow],
    target_chars: int,
    overlap_chars: int,
) -> Iterator[ActivityChunk]:
    chunk_rows: list[RenderedActivityRow] = []
    chunk_size = 0
    chunk_index = 1

    for row in rows:
        rendered = RenderedActivityRow(row=row, text=render_activity_row(row))
        rendered_size = len(rendered.text) + 2
        if chunk_rows and chunk_size + rendered_size > target_chars:
            yield ActivityChunk(index=chunk_index, rows=chunk_rows)
            chunk_index += 1
            chunk_rows = overlap_tail(chunk_rows, overlap_chars)
            chunk_size = sum(len(item.text) + 2 for item in chunk_rows)
        chunk_rows.append(rendered)
        chunk_size += rendered_size

    if chunk_rows:
        yield ActivityChunk(index=chunk_index, rows=chunk_rows)
