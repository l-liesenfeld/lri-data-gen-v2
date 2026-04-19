# Output reference

Every run writes a timestamped directory under the configured `output_dir` (default `data/output/`):

```
data/output/<experiment_name>_<YYYY-MM-DD_HHMM>/
  results.jsonl           # one line per call
  results.csv             # final table matching the legacy ML-pipeline schema
  run_meta.json           # totals, timings, cost
  config_snapshot.yaml    # byte-copy of the input YAML
```

If a directory with the same name would collide, `-2`, `-3`, etc. is appended.

---

## `results.jsonl`

One call per line. Each line is a JSON object. The schema is defined by `src/models.GenerationResult.to_json`:

| Field | Type | Notes |
|---|---|---|
| `call_index` | int | 0-based call index within the run. |
| `response_id` | int | 1-based response id. Used as the primary key in the CSV. |
| `status` | `"ok"` \| `"failed"` | — |
| `text` | string \| null | Primary text. `null` if failed or missing. |
| `text_deutsch` | string \| null | German translation. Only present in bilingual mode. |
| `motives_present` | list | Model-emitted ground-truth echo (id, name, strength). |
| `ground_truth` | list | The motives the pipeline asked for (id, strength). Always present. |
| `raw_response` | string | Unparsed model output. Preserved for debugging, useful when `status="failed"`. |
| `error` | string \| null | Short error description. Populated on `failed`. |
| `tokens_in` | int | Prompt tokens consumed (from the API `usage` block). |
| `tokens_out` | int | Completion tokens. |
| `model` | string | Model ID returned by the API. |
| `openai_request_id` | string \| null | `x-request-id` header, for cross-referencing with OpenAI logs. |
| `created_at` | string | ISO-8601 UTC timestamp, second precision. |

Lines are appended **with `fsync`** immediately after each call completes, so the file stays consistent even on crash or `Ctrl+C`.

---

## `results.csv`

This is the schema the downstream ML pipeline consumes. **It is a strict contract** — do not change column order or header names without coordinating with the ML team.

### Header rows (4 metadata + 1 blank)

```
"Generated with model","openai:gpt-4o-2024-08-06"
"Timestamp","2026-04-19T14:12:03Z"
"Token usage","1435356"
"Request ID","my_run_2026-04-19_1412"
              ← blank line
```

- `Token usage` is the sum of all input + output tokens across the run.
- `Request ID` is the run directory name (no longer maps to a single OpenAI request because each call has its own).

### Column header

```
"Response_Number","Text",["German_Text",] "A1","A2","A3","A4","A5","L1","L2","L3","L4","L5","M1","M2","M3","M4","M5","F1","F2","F3","F4","F5"
```

- `German_Text` is present **iff** any row has non-empty `text_deutsch`. Absent for English-only runs, absent for Deutsch-only runs (the German text lives in `Text` in that case), present for bilingual runs.
- 20 motive columns, always in the fixed order `A1..A5, L1..L5, M1..M5, F1..F5`.

### Data rows

- `Response_Number` = `response_id` from the JSONL (1-based).
- `Text` = the generated entry text, quoted, with internal `"` escaped as `""` and newlines replaced by single spaces.
- `German_Text` (if present) = same treatment, `text_deutsch` value.
- Each motive column = the strength (0–1) from `motives_present`, or `0` if that motive isn't listed.

### Failed rows

A failed call still gets a row:

```
42,"FAILED: invalid JSON after 2 attempts",0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
```

- `Text` column contains `FAILED: <error>`.
- `German_Text` (if present) is empty.
- All 20 motive columns are `0`.

### Encoding

UTF-8 with a leading BOM (`\ufeff`) so Excel recognizes the encoding correctly. This matters for German diacritics.

---

## `run_meta.json`

```json
{
  "experiment_name": "bilingual_affiliation_pilot",
  "notes": "first bilingual run",
  "started_at": "2026-04-19T14:12:03Z",
  "finished_at": "2026-04-19T14:15:50Z",
  "model": "openai:gpt-4o-2024-08-06",
  "language": "deutsch-english",
  "n_responses_requested": 100,
  "n_completed": 100,
  "n_failed": 0,
  "tokens_in_total": 1249312,
  "tokens_out_total": 186044,
  "cost_usd_total": 5.084124,
  "cost_estimate_usd": 4.941200,
  "elapsed_seconds": 227.13,
  "concurrency": 8,
  "synth_version": "0.1.0"
}
```

`cost_estimate_usd` vs. `cost_usd_total` is a useful calibration signal. If the estimate drifts more than ~15% from reality across several runs, update the output-token constants in `src/cost.py`.

---

## `config_snapshot.yaml`

A byte-copy of the input config, written before any calls are made. Ensures that runs are reproducible: the YAML you edit later can't retroactively change a past run's meaning.
