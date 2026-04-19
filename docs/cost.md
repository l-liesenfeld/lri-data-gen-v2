# Cost estimation and tracking

## How the estimate is computed

Two numbers, per call:

- **Input tokens:**
  - *OpenAI:* exact — system + user encoded with the model's tiktoken encoding, plus chat-completions overhead (3 tokens per message + 3 priming).
  - *Anthropic:* heuristic — `(len(system) + len(user)) // 4`. Anthropic's official token counter needs a network call, which isn't worth it for pre-flight estimates. The **actual** run cost is still exact because it uses `usage.input_tokens` from each response.
- **Output tokens (estimate):** a formula in `src/cost.py:_estimate_output_tokens`:

  ```
  base = 90 + 30 * response_length
  if language == "deutsch":          base *= 1.1
  if language == "deutsch-english":  base *= 2.0
  total = base + 60   # JSON envelope overhead
  ```

Multiply by `n_responses` → totals. Multiply by the model's per-token pricing → dollar estimate.

## Pricing table

**OpenAI** (`src/llm/openai.py:OPENAI_PRICING`):

| Model | Input $/1M | Output $/1M | Context |
|---|---|---|---|
| `gpt-5.4` | $2.50 | $15.00 | 272,000 |
| `gpt-5.4-mini` | $0.75 | $4.50 | 272,000 |
| `gpt-5.4-nano` | $0.20 | $1.25 | 272,000 |
| `gpt-5.4-pro` | $30.00 | $180.00 | 272,000 |
| `gpt-5.2` | $1.75 | $14.00 | 272,000 |
| `gpt-4.1` | $2.00 | $8.00 | 1,000,000 |
| `gpt-4.1-mini` | $0.40 | $1.60 | 1,000,000 |
| `gpt-4.1-nano` | $0.10 | $0.40 | 1,000,000 |
| `gpt-4o` | $2.50 | $10.00 | 128,000 |
| `gpt-4o-mini` | $0.15 | $0.60 | 128,000 |
| `gpt-4o-2024-08-06` | $2.50 | $10.00 | 128,000 |

**Anthropic** (`src/llm/anthropic.py:ANTHROPIC_PRICING`):

| Model | Input $/1M | Output $/1M | Context |
|---|---|---|---|
| `claude-opus-4-7` | $5.00 | $25.00 | 1,000,000 |
| `claude-opus-4-6` | $5.00 | $25.00 | 1,000,000 |
| `claude-sonnet-4-6` | $3.00 | $15.00 | 1,000,000 |
| `claude-haiku-4-5` | $1.00 | $5.00 | 200,000 |

Adding a model is one line in the relevant provider's pricing dict. Confirm numbers against the provider's pricing page before a large run.

## Pre-run gate

`generate` always prints the estimate and asks `Proceed? [y/N]`. Pass `-y` to skip. Warnings are shown if:

- Per-call tokens exceed the model's context window → aborts, no `-y` override.
- Estimated cost > $20 or call count > 500 → prints a warning but the confirmation still happens.

## Runtime tracking

Every successful call records its real `tokens_in` / `tokens_out` from the API's `usage` block. A `CostTracker` accumulates the total and updates the progress bar's postfix:

```
Generating [========>   ] 47/100 ... $1.18
```

Final totals land in `run_meta.json` alongside the estimate so drift is visible.

## Calibrating the output estimate

The input-token count is exact; the output-token formula is a heuristic. After ~100 real responses at a given language and length, check the drift in `run_meta.json`:

```json
"cost_usd_total":   5.08,
"cost_estimate_usd": 4.94
```

~3% drift is fine. Consistent >15% drift means the constants in `_estimate_output_tokens` should be tuned. The sensible approach:

1. Run a small (n=50) experiment for each language setting.
2. Look at `tokens_out / n_responses` in the JSONL for each run.
3. Update `base` / multipliers in `src/cost.py` to match.

This is a 10-minute task once there's real data.

## Why estimate at all

For a desktop-scale tool, the main benefit is psychological: you see the dollar figure before clicking through. It also catches bugs fast — if the estimate says $0.02 and the actual bill is $20, something is very wrong (infinite retry loop, wrong model, etc.).
