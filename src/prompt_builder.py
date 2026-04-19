"""Assembles the legacy prompt for a single-response call."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .models import ExperimentConfig, LLMRequest, MotiveMatrix, MotiveWeight

SYSTEM_MESSAGE = (
    "You are an expert in psychological text generation, skilled at creating realistic "
    "human-like journal entries that subtly incorporate specific psychological motives "
    "and patterns. You understand how underlying psychological drives manifest in "
    "writing without being explicitly stated."
)

LANGUAGE_FRAGMENTS: dict[str, dict[str, str | bool]] = {
    "english": {
        "prompt_instructions": "All journal entry text should be written in English.",
        "placeholder_primary": "[TEXT WILL BE GENERATED HERE IN ENGLISH]",
        "bilingual": False,
    },
    "deutsch": {
        "prompt_instructions": (
            "All journal entry text should be written in German (Deutsch). "
            "Only the actual text paragraphs should be in German; everything else "
            "including JSON structure remains in English."
        ),
        "placeholder_primary": "[TEXT WILL BE GENERATED HERE IN GERMAN]",
        "bilingual": False,
    },
    "deutsch-english": {
        "prompt_instructions": (
            "For each journal entry, provide both the original English version and a "
            "German (Deutsch) translation. The JSON structure should include both "
            "versions for each entry."
        ),
        "placeholder_primary": "[TEXT WILL BE GENERATED HERE IN ENGLISH]",
        "placeholder_secondary": "[GERMAN TRANSLATION WILL BE GENERATED HERE]",
        "bilingual": True,
    },
}

DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "legacy.txt"


@lru_cache(maxsize=1)
def _load_template(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def build_single_template(
    language: str, motives: list[MotiveWeight], matrix: MotiveMatrix
) -> dict:
    frag = LANGUAGE_FRAGMENTS[language]
    motives_present = [
        {"id": m.id, "name": matrix.get(m.id).name, "strength": m.strength}
        for m in motives
    ]
    entry: dict = {
        "response_id": 1,
        "text": frag["placeholder_primary"],
    }
    if frag["bilingual"]:
        entry["text_deutsch"] = frag["placeholder_secondary"]
    entry["motives_present"] = motives_present
    return {"responses": [entry]}


def _format_motives_block(motives: list[MotiveWeight], matrix: MotiveMatrix) -> str:
    lines = []
    for m in motives:
        cell = matrix.get(m.id)
        lines.append(
            f"- {cell.name} (ID: {m.id}): {cell.description}. "
            f"Strength: {m.strength} out of 1.0"
        )
    return "\n".join(lines)


def _format_context_block(context_hint: str) -> str:
    # demographic/situation params are not surfaced in phase 1; hint-only.
    parts = ["Vary demographics naturally", "Vary life situations"]
    hint = context_hint.strip()
    if hint:
        parts.append(f"Additional context: {hint}")
    return "\n".join(parts)


def build_prompt(
    cfg: ExperimentConfig,
    matrix: MotiveMatrix,
    *,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
) -> LLMRequest:
    template = _load_template(str(template_path))
    frag = LANGUAGE_FRAGMENTS[cfg.language]
    filled = template.format(
        motives_block=_format_motives_block(cfg.motives, matrix),
        language_instructions=frag["prompt_instructions"],
        context_block=_format_context_block(cfg.context_hint),
        response_length=cfg.response_length,
        response_template_json=json.dumps(
            build_single_template(cfg.language, cfg.motives, matrix),
            indent=2,
            ensure_ascii=False,
        ),
    )
    return LLMRequest(
        system=SYSTEM_MESSAGE,
        user=filled,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        response_format_json=True,
    )
