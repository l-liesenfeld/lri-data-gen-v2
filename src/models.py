"""Dataclasses + config loader for synth-data."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

Language = Literal["english", "deutsch", "deutsch-english"]
VALID_LANGUAGES: tuple[str, ...] = ("english", "deutsch", "deutsch-english")
VALID_CATEGORIES: tuple[str, ...] = ("A", "L", "M", "F")


# ---------------------------------------------------------------------------
# Motive matrix
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MotiveCell:
    id: str
    category: str
    index: int
    name: str
    description: str
    psi_reference: str | None


@dataclass
class MotiveMatrix:
    cells: dict[str, MotiveCell]
    categories: dict[str, str]
    levels: dict[str, dict[str, Any]]

    def get(self, motive_id: str) -> MotiveCell:
        if motive_id not in self.cells:
            raise KeyError(f"unknown motive id: {motive_id!r}")
        return self.cells[motive_id]

    def category_ids(self, category: str) -> list[str]:
        return sorted(cid for cid in self.cells if self.cells[cid].category == category)

    @classmethod
    def load(cls, path: Path) -> MotiveMatrix:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cells: dict[str, MotiveCell] = {}
        categories: dict[str, str] = {}
        for cat_key, cat_val in raw["motives"].items():
            categories[cat_key] = cat_val["name"]
            for idx_key, cell in cat_val["cells"].items():
                cid = cell["key"]
                cells[cid] = MotiveCell(
                    id=cid,
                    category=cat_key,
                    index=int(idx_key),
                    name=cell["name"],
                    description=cell["description"],
                    psi_reference=cell.get("psi_reference"),
                )
        return cls(cells=cells, categories=categories, levels=raw.get("levels", {}))


# ---------------------------------------------------------------------------
# Experiment config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MotiveWeight:
    id: str
    strength: float


@dataclass
class ExperimentConfig:
    experiment_name: str
    output_dir: Path
    notes: str
    model: str
    n_responses: int
    response_length: int
    language: str
    context_hint: str
    temperature: float
    max_tokens: int
    concurrency: int
    max_retries: int
    timeout_seconds: int
    motives: list[MotiveWeight]
    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None

    @property
    def provider_prefix(self) -> str:
        return self.model.split(":", 1)[0] if ":" in self.model else ""

    @property
    def model_id(self) -> str:
        return self.model.split(":", 1)[1] if ":" in self.model else self.model


class ConfigError(ValueError):
    """Raised when YAML config fails validation."""


def load_config(path: Path, matrix: MotiveMatrix) -> ExperimentConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top-level must be a mapping")

    exp = raw.get("experiment") or {}
    gen = raw.get("generation") or {}
    rt = raw.get("runtime") or {}
    motives_raw = raw.get("motives")
    model = raw.get("model")

    if not model or not isinstance(model, str):
        raise ConfigError("missing required field: model")
    if ":" not in model:
        raise ConfigError(f"model must be prefixed (e.g. 'openai:gpt-5.4-mini'), got {model!r}")
    _provider = model.split(":", 1)[0]
    if _provider not in ("openai", "anthropic"):
        raise ConfigError(
            f"unsupported provider {_provider!r}. Supported: 'openai', 'anthropic'."
        )

    name = exp.get("name") or "run"
    output_dir = Path(exp.get("output_dir") or "data/output")
    notes = exp.get("notes") or ""

    n = gen.get("n_responses")
    if not isinstance(n, int) or n < 1:
        raise ConfigError("generation.n_responses must be an integer >= 1")

    rlen = gen.get("response_length", 3)
    if not isinstance(rlen, int) or not (1 <= rlen <= 5):
        raise ConfigError("generation.response_length must be an integer 1..5")

    lang = gen.get("language", "english")
    if lang not in VALID_LANGUAGES:
        raise ConfigError(f"generation.language must be one of {VALID_LANGUAGES}, got {lang!r}")

    hint = gen.get("context_hint", "") or ""
    temperature = float(gen.get("temperature", 0.9))
    max_tokens = int(gen.get("max_tokens", 512))

    concurrency = int(rt.get("concurrency", 3))
    if concurrency < 1:
        raise ConfigError("runtime.concurrency must be >= 1")
    max_retries = int(rt.get("max_retries", 8))
    timeout_seconds = int(rt.get("timeout_seconds", 60))
    rpm = rt.get("requests_per_minute")
    tpm = rt.get("tokens_per_minute")
    if rpm is not None:
        if not isinstance(rpm, int) or rpm < 1:
            raise ConfigError("runtime.requests_per_minute must be a positive integer")
    if tpm is not None:
        if not isinstance(tpm, int) or tpm < 1:
            raise ConfigError("runtime.tokens_per_minute must be a positive integer")

    motives = _normalize_motives(motives_raw, matrix)
    if not motives:
        raise ConfigError("at least one motive must be selected")

    return ExperimentConfig(
        experiment_name=name,
        output_dir=output_dir,
        notes=notes,
        model=model,
        n_responses=n,
        response_length=rlen,
        language=lang,
        context_hint=hint,
        temperature=temperature,
        max_tokens=max_tokens,
        concurrency=concurrency,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
        motives=motives,
        requests_per_minute=rpm,
        tokens_per_minute=tpm,
    )


def _normalize_motives(raw: Any, matrix: MotiveMatrix) -> list[MotiveWeight]:
    """Accept three input forms; return an explicit-id list, explicit wins on conflict."""
    explicit: dict[str, float] = {}
    from_category: dict[str, float] = {}
    warnings: list[str] = []

    if raw is None:
        return []

    if isinstance(raw, dict):
        # Shorthand mapping form: {A1: 0.7, L3: 0.4}
        for mid, strength in raw.items():
            _validate_id_and_strength(mid, strength, matrix)
            explicit[mid] = float(strength)
    elif isinstance(raw, list):
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise ConfigError(f"motives[{i}] must be a mapping, got {type(entry).__name__}")
            if "category" in entry:
                cat = entry["category"]
                if cat not in VALID_CATEGORIES:
                    raise ConfigError(
                        f"motives[{i}].category must be one of {VALID_CATEGORIES}, got {cat!r}"
                    )
                strength = entry.get("strength")
                _validate_strength(strength, f"motives[{i}].strength")
                for cid in matrix.category_ids(cat):
                    from_category[cid] = float(strength)
            elif "id" in entry:
                mid = entry["id"]
                strength = entry.get("strength")
                _validate_id_and_strength(mid, strength, matrix)
                if mid in explicit:
                    raise ConfigError(f"motive {mid!r} listed more than once explicitly")
                explicit[mid] = float(strength)
            else:
                # Could be a single-key mapping {A1: 0.7}
                if len(entry) == 1:
                    mid, strength = next(iter(entry.items()))
                    _validate_id_and_strength(mid, strength, matrix)
                    explicit[mid] = float(strength)
                else:
                    raise ConfigError(
                        f"motives[{i}] must have either 'id' or 'category' (or be a single-key map)"
                    )
    else:
        raise ConfigError(f"motives must be a list or mapping, got {type(raw).__name__}")

    combined: dict[str, float] = dict(from_category)
    for mid, s in explicit.items():
        if mid in combined and combined[mid] != s:
            warnings.append(f"motive {mid} overridden: {combined[mid]} -> {s} (explicit wins)")
        combined[mid] = s

    for w in warnings:
        print(f"warning: {w}")

    # Stable order: A1..A5, L1..L5, M1..M5, F1..F5
    ordered = sorted(
        combined.items(),
        key=lambda kv: (VALID_CATEGORIES.index(kv[0][0]), int(kv[0][1:])),
    )
    return [MotiveWeight(id=mid, strength=s) for mid, s in ordered]


def _validate_id_and_strength(mid: Any, strength: Any, matrix: MotiveMatrix) -> None:
    if not isinstance(mid, str) or mid not in matrix.cells:
        valid = ", ".join(sorted(matrix.cells))
        raise ConfigError(f"unknown motive id {mid!r}. Valid ids: {valid}")
    _validate_strength(strength, f"motive {mid!r} strength")


def _validate_strength(strength: Any, label: str) -> None:
    if not isinstance(strength, (int, float)):
        raise ConfigError(f"{label} must be a number, got {type(strength).__name__}")
    if not (0.1 <= float(strength) <= 1.0):
        raise ConfigError(f"{label} must be in [0.1, 1.0], got {strength}")


# ---------------------------------------------------------------------------
# LLM interface types
# ---------------------------------------------------------------------------

@dataclass
class LLMRequest:
    system: str
    user: str
    max_tokens: int = 512
    temperature: float = 0.9
    response_format_json: bool = True
    # Provider-agnostic JSON schema for structured output. If set, Anthropic uses
    # output_config.format.json_schema to enforce it. OpenAI still uses json_object mode.
    json_schema: dict | None = None


@dataclass
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    request_id: str | None = None


# ---------------------------------------------------------------------------
# Generation / run artifacts
# ---------------------------------------------------------------------------

@dataclass
class MotivePresent:
    id: str
    name: str
    strength: float


@dataclass
class GenerationResult:
    call_index: int
    response_id: int
    status: str  # "ok" | "failed"
    text: str | None
    text_deutsch: str | None
    motives_present: list[MotivePresent]
    ground_truth: list[MotiveWeight]
    raw_response: str
    error: str | None
    tokens_in: int
    tokens_out: int
    model: str
    openai_request_id: str | None
    created_at: str

    def to_json(self) -> dict[str, Any]:
        return {
            "call_index": self.call_index,
            "response_id": self.response_id,
            "status": self.status,
            "text": self.text,
            "text_deutsch": self.text_deutsch,
            "motives_present": [
                {"id": m.id, "name": m.name, "strength": m.strength}
                for m in self.motives_present
            ],
            "ground_truth": [
                {"id": m.id, "strength": m.strength} for m in self.ground_truth
            ],
            "raw_response": self.raw_response,
            "error": self.error,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "model": self.model,
            "openai_request_id": self.openai_request_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> GenerationResult:
        return cls(
            call_index=d["call_index"],
            response_id=d["response_id"],
            status=d["status"],
            text=d.get("text"),
            text_deutsch=d.get("text_deutsch"),
            motives_present=[
                MotivePresent(id=m["id"], name=m["name"], strength=float(m["strength"]))
                for m in d.get("motives_present", [])
            ],
            ground_truth=[
                MotiveWeight(id=m["id"], strength=float(m["strength"]))
                for m in d.get("ground_truth", [])
            ],
            raw_response=d.get("raw_response", ""),
            error=d.get("error"),
            tokens_in=int(d.get("tokens_in", 0)),
            tokens_out=int(d.get("tokens_out", 0)),
            model=d.get("model", ""),
            openai_request_id=d.get("openai_request_id"),
            created_at=d.get("created_at", ""),
        )


@dataclass
class CostEstimate:
    input_tokens_per_call: int
    output_tokens_per_call: int
    total_input_tokens: int
    total_output_tokens: int
    n_calls: int
    cost_usd: float
    model: str
    context_window: int
    fits_context: bool


@dataclass
class RunSummary:
    n_requested: int
    n_completed: int
    n_failed: int
    tokens_in_total: int
    tokens_out_total: int
    cost_usd_total: float
    elapsed_seconds: float
    output_dir: Path
    results_jsonl: Path
    results_csv: Path | None = field(default=None)
    failure_breakdown: dict[str, int] = field(default_factory=dict)
