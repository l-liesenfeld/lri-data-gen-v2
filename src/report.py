"""JSONL -> CSV exporter matching the legacy schema byte-for-byte."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import GenerationResult

MOTIVE_COLUMNS: list[str] = [
    f"{cat}{i}" for cat in ("A", "L", "M", "F") for i in range(1, 6)
]


def _escape_cell(raw: str) -> str:
    """Legacy behavior: double internal quotes, replace newlines with a single space."""
    s = raw.replace('"', '""')
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def _detect_bilingual(results: list[GenerationResult]) -> bool:
    return any(
        r.status == "ok" and r.text_deutsch and r.text_deutsch.strip()
        for r in results
    )


def _meta_rows(model: str, timestamp: str, token_usage: int, request_id: str) -> list[str]:
    return [
        f'"Generated with model","{model}"',
        f'"Timestamp","{timestamp}"',
        f'"Token usage","{token_usage}"',
        f'"Request ID","{request_id}"',
    ]


def _build_header(bilingual: bool) -> str:
    parts = ['"Response_Number"', '"Text"']
    if bilingual:
        parts.append('"German_Text"')
    parts.extend(f'"{col}"' for col in MOTIVE_COLUMNS)
    return ",".join(parts)


def _build_row(result: GenerationResult, bilingual: bool) -> str:
    if result.status == "ok":
        text = result.text or ""
    else:
        text = f"FAILED: {result.error or 'unknown error'}"

    parts: list[str] = [str(result.response_id), _escape_cell(text)]
    if bilingual:
        parts.append(_escape_cell(result.text_deutsch or "" if result.status == "ok" else ""))

    # Build strength map from motives_present (ground truth for failed rows is 0s).
    strength_map: dict[str, float] = {}
    if result.status == "ok":
        for m in result.motives_present:
            strength_map[m.id] = m.strength

    for col in MOTIVE_COLUMNS:
        parts.append(str(strength_map.get(col, 0)))
    return ",".join(parts)


def render_csv(
    results: list[GenerationResult],
    *,
    model: str,
    timestamp: str,
    token_usage: int,
    request_id: str,
) -> str:
    bilingual = _detect_bilingual(results)
    lines: list[str] = []
    lines.extend(_meta_rows(model, timestamp, token_usage, request_id))
    lines.append("")  # blank separator
    lines.append(_build_header(bilingual))

    # Sort by response_id for stable output.
    ordered = sorted(results, key=lambda r: r.response_id)
    for r in ordered:
        lines.append(_build_row(r, bilingual))

    return "\n".join(lines) + "\n"


def write_csv(
    results: Iterable[GenerationResult],
    out_path: Path,
    *,
    model: str,
    timestamp: str,
    token_usage: int,
    request_id: str,
) -> None:
    csv_text = render_csv(
        list(results),
        model=model,
        timestamp=timestamp,
        token_usage=token_usage,
        request_id=request_id,
    )
    # UTF-8 BOM for Excel.
    out_path.write_text("\ufeff" + csv_text, encoding="utf-8")


def load_jsonl(path: Path) -> list[GenerationResult]:
    out: list[GenerationResult] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(GenerationResult.from_json(json.loads(line)))
    return out
