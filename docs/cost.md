# Cost estimation and tracking

## How the estimate is computed

Two numbers, per call:

- **Input tokens (exact):** the system + user message are encoded with the model's tiktoken encoding, plus OpenAI's chat-completions overhead (3 tokens per message + 3 priming). This is real, not heuristic.
- **Output tokens (estimate):** a formula in `src/cost.py:_estimate_output_tokens`:

  ```
  base = 90 + 30 * response_length
  if language == "deutsch":          base *= 1.1
  if language == "deutsch-english":  base *= 2.0
  total = base + 60   # JSON envelope overhead
  ```

Multiply by `n_responses` → totals. Multiply by the model's per-token pricing → dollar estimate.

## Pricing table

Phase 1 ships with one entry (see `src/llm/openai.py:OPENAI_PRICING`):

| Model | Input $/1M | Output $/1M | Context |
|---|---|---|---|
| `gpt-4o-2024-08-06` | $2.50 | $10.00 | 128,000 |

Adding a model is one line in that dict (plus whatever the provider adapter needs to actually call it).

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
