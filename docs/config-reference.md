# Configuration reference

Every experiment is a YAML file. This page is the exhaustive schema. For a walkthrough, see [`usage.md`](usage.md). For motive meanings, see [`motives.md`](motives.md).

## Top-level structure

```yaml
experiment:   # optional metadata
  name: "..."
  output_dir: "data/output"
  notes: "..."

model: "openai:gpt-5.4-mini"   # required, provider-prefixed

generation:
  n_responses: 10
  response_length: 3
  language: "english"
  context_hint: ""
  temperature: 0.9
  max_tokens: 512

runtime:
  concurrency: 5
  max_retries: 5
  timeout_seconds: 60

motives:
  - id: A1
    strength: 0.7
```

---

## Fields

### `experiment` (optional)

| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | string | `"run"` | Used in the output directory name (slugged). |
| `output_dir` | string | `"data/output"` | Where runs land. Each run creates a timestamped subdirectory. |
| `notes` | string | `""` | Copied verbatim into `run_meta.json`. |

### `model` (required)

A provider-prefixed model string. Supported providers: `openai:`, `anthropic:`.

**OpenAI models:**

| Value | Notes |
|---|---|
| `openai:gpt-5.4-mini` | Recommended default — best quality-to-cost for this workload. |
| `openai:gpt-5.4` | Flagship reasoning model. |
| `openai:gpt-5.4-nano` | Cheapest GPT-5.4 tier. |
| `openai:gpt-5.4-pro` | Maximum capability (expensive). |
| `openai:gpt-5.2` | Previous GPT-5 generation. |
| `openai:gpt-4.1`, `openai:gpt-4.1-mini`, `openai:gpt-4.1-nano` | 1M-context family. |
| `openai:gpt-4o`, `openai:gpt-4o-mini`, `openai:gpt-4o-2024-08-06` | Previous-gen 128K. |

**Anthropic models:**

| Value | Notes |
|---|---|
| `anthropic:claude-opus-4-7` | Latest flagship (April 2026). |
| `anthropic:claude-opus-4-6` | Prior flagship, same price. |
| `anthropic:claude-sonnet-4-6` | Production workhorse. |
| `anthropic:claude-haiku-4-5` | Speed/volume tier. |

Full pricing and context windows: [`cost.md`](cost.md). Auth: `OPENAI_API_KEY` for `openai:`, `ANTHROPIC_API_KEY` for `anthropic:`.

### `generation` (required)

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `n_responses` | int | — | ≥ 1 | Number of single-response API calls to make. |
| `response_length` | int | 3 | 1–5 | Target sentences per entry. |
| `language` | string | `"english"` | one of: `english`, `deutsch`, `deutsch-english` | Bilingual mode adds a `text_deutsch` field to each response. |
| `context_hint` | string | `""` | — | Optional free text injected into the prompt (e.g. `"workplace situation"`). |
| `temperature` | float | 0.9 | 0.0–2.0 | Forwarded to the model. Lower = more deterministic. |
| `max_tokens` | int | 512 | ≥ 1 | Max output tokens per call. |

### `runtime` (optional)

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `concurrency` | int | 3 | ≥ 1 | Max in-flight calls at once (semaphore). |
| `max_retries` | int | 8 | ≥ 0 | Per-call retries on 408/429/5xx with exponential backoff (capped at 60s). |
| `timeout_seconds` | int | 60 | ≥ 1 | Per-call HTTP timeout. |
| `requests_per_minute` | int | (off) | ≥ 1 | Proactive RPM ceiling. If set, the pipeline paces below this via a token bucket. |
| `tokens_per_minute` | int | (off) | ≥ 1 | Proactive TPM ceiling. Reserves `input_tokens + max_tokens` per call up front. |

Set `requests_per_minute` / `tokens_per_minute` to your OpenAI tier's limits to avoid hitting 429s. See [`troubleshooting.md`](troubleshooting.md) for common tier values.

### `motives` (required, at least one entry)

Three input forms, freely mixable.

**Form 1 — explicit list of objects (canonical):**

```yaml
motives:
  - id: A1
    strength: 0.7
  - id: L3
    strength: 0.4
```

**Form 2 — shorthand mapping:**

```yaml
motives:
  A1: 0.7
  L3: 0.4
```

**Form 3 — category expansion** (applies to all 5 cells in a category):

```yaml
motives:
  - category: A       # A1..A5
    strength: 0.5
  - id: L3            # additional / explicit override
    strength: 0.8
```

**Conflict resolution:** if a category expansion and an explicit `id` assign the same motive, the explicit value wins and a warning is printed.

**Strength rules:**

- Must be a number between `0.1` and `1.0` (inclusive).
- Values outside this range fail validation.

**Motive IDs:**

- Four categories: `A`, `L`, `M`, `F`.
- Five cells per category, indexed 1–5.
- Valid IDs: `A1..A5, L1..L5, M1..M5, F1..F5` (20 total).
- Full names and descriptions: [`motives.md`](motives.md) or `python cli.py list-motives`.

---

## Validation

Run `python cli.py validate <config>` to check a file without spending anything. The validator enforces:

- Top level is a mapping.
- `model` is present and provider-prefixed.
- `n_responses ≥ 1`, `response_length ∈ [1,5]`, `concurrency ≥ 1`.
- `language` is one of the three supported values.
- Every motive ID exists in the matrix.
- Every strength is in `[0.1, 1.0]`.
- At least one motive is selected.

---

## Example

```yaml
experiment:
  name: "bilingual_affiliation_pilot"
  notes: "first bilingual run, low-affiliation probe"

model: "openai:gpt-5.4-mini"

generation:
  n_responses: 100
  response_length: 4
  language: "deutsch-english"
  context_hint: "family dinner"

runtime:
  concurrency: 8

motives:
  - category: A      # all 5 affiliation cells
    strength: 0.6
  - id: F5           # add one freedom cell explicitly
    strength: 0.3
```
