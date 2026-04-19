# MCP server (Claude Desktop integration)

synth-data ships a local MCP (Model Context Protocol) server so Claude Desktop can drive generation directly from chat. You don't run a daemon — Claude Desktop spawns the server as a subprocess on demand, talks to it over stdin/stdout, and tears it down when the app closes.

This is the fast iteration loop: write a chat message describing the motive profile you want, Claude calls the `generate` tool, results come back inline in the conversation. From there, Claude Desktop's built-in filesystem / email / etc. MCPs can save, share, or forward the output — the synth-data server doesn't need to do any of that itself.

## Install

1. Install dependencies (if not already):
   ```bash
   pip install -r requirements.txt
   ```
   This adds the `mcp` package alongside the existing CLI deps.

2. Make sure your `.env` at the project root has the API keys for whichever providers you plan to use:
   ```
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   ```

3. Register the server in Claude Desktop's config file.

   macOS path: `~/Library/Application Support/Claude/claude_desktop_config.json`

   ```json
   {
     "mcpServers": {
       "synth-data": {
         "command": "/absolute/path/to/synth-data/.venv/bin/python",
         "args": ["/absolute/path/to/synth-data/mcp_server.py"]
       }
     }
   }
   ```

   Replace both paths with absolute paths. If you have other `mcpServers` entries, add `synth-data` alongside them.

4. Quit and relaunch Claude Desktop. The `synth-data` server should show up in the tools picker with three tools: `list_motives`, `estimate_cost`, `generate`.

## Tools

### `list_motives()`

No arguments. Returns all 20 motives grouped by category (A/L/M/F), with id, name, and description. Useful for Claude to reference before composing a generation request.

### `estimate_cost(motives, n_responses, ...)`

Dry-run budget check. Same arg shape as `generate` below (minus the actual execution params). Returns estimated input/output tokens and total USD cost. No network calls made. Useful for "how much would N of these cost" questions.

### `generate(motives, n_responses, ...)`

The main tool.

**Arguments:**
- `motives: dict[str, float]` — mapping of motive id to strength in `[0.1, 1.0]`. Example: `{"A1": 0.7, "L3": 0.4}`.
- `n_responses: int` — number of entries, `1..100`. Runs larger than 100 go through the CLI.
- `model: str` — provider-prefixed model name. Default: `openai:gpt-5.4-mini`. Any model in the OpenAI or Anthropic pricing tables works.
- `language: str` — `"english"`, `"deutsch"`, or `"deutsch-english"`. Default `"english"`.
- `response_length: int` — sentences per entry, `1..5`. Default 3.
- `context_hint: str` — optional scene nudge for the prompt (e.g. `"workplace situation"`).
- `experiment_name: str | None` — used in the output directory name. Default `"mcp_run"`.
- `temperature: float` — sampling temperature, `0.0..2.0`. Default 0.9.
- `max_cost_usd: float` — **pre-flight cost cap. Default $1.00.** If the estimate exceeds this, the tool refuses and returns the estimate instead. Re-call with a higher cap to proceed.
- `output_dir: str | None` — where to write results. Default: project's `data/output/`.

**Returns:**
```jsonc
{
  "status": "ok",                 // "ok" | "partial" | "refused"
  "summary": {
    "n_completed": 5,
    "n_failed": 0,
    "cost_usd_actual": 0.0234,
    "elapsed_seconds": 12.4,
    "output_dir": "/abs/path/to/data/output/mcp_run_2026-04-19_1430",
    "results_jsonl": ".../results.jsonl",
    "results_csv":   ".../results.csv"
  },
  "estimate": { ... pre-flight estimate ... },
  "results": [ {text, motives_present, ...}, ... ],   // inline for n <= 20
  "results_truncated": false,     // true for n > 20; a 5-entry preview is returned
  "failure_breakdown": {}         // keyed by rate_limited/network/parse_error/...
}
```

When `status == "refused"`, the response includes a `reason` field (`cost_cap_exceeded`, `context_window_exceeded`, `provider_error`) and the estimate it rejected on, so Claude can tell you exactly what cap to raise.

## Guardrails (defaults, overridable)

- `n_responses` hard cap: 100 per call. Bigger runs go through the CLI.
- `max_cost_usd` default: $1.00. Blocks accidental large spends when iterating.
- Context window check: if per-call tokens exceed the model's window, the tool refuses before spending.

## Troubleshooting

**"synth-data" doesn't show up in Claude Desktop after editing the config.**
Fully quit Claude Desktop (Cmd-Q, not just closing the window) and relaunch. Check `~/Library/Logs/Claude/mcp-server-synth-data.log` for startup errors.

**Tool call fails with "OPENAI_API_KEY not set" / "ANTHROPIC_API_KEY not set".**
The `.env` at the project root isn't being found. Either:
- Confirm `.env` exists in the same directory as `mcp_server.py`, **or**
- Add the keys explicitly in the Claude Desktop config's `env` block:
  ```json
  "synth-data": {
    "command": "...",
    "args": ["..."],
    "env": { "OPENAI_API_KEY": "sk-...", "ANTHROPIC_API_KEY": "sk-ant-..." }
  }
  ```

**Large runs time out in Claude Desktop.**
The `n_responses` cap is 100, but even smaller runs can hit Claude Desktop's tool-call timeout if the provider is slow. Drop to `n_responses: 20` or run the CLI directly.

**Tool returned `"status": "refused"` with `"reason": "cost_cap_exceeded"`.**
Expected — pass a higher `max_cost_usd` on the retry. The refused response includes the exact estimate it blocked on.

**Stdout contamination.**
The server must only emit JSON-RPC frames on stdout. If you see parse errors in Claude Desktop's log, the culprit is usually a stray `print()` statement somewhere in the loaded modules. All synth-data logging goes to stderr; if you add custom hooks, keep them on stderr too.

## Design notes

- **stdio, not HTTP.** Claude Desktop spawns the process; there's no port, no persistent server, no extra config surface.
- **Shared pipeline.** Both the CLI (`cli.py`) and the MCP server (`mcp_server.py`) call `src/runner.py`. No parallel code paths — behavior, prompting, cost tracking, JSONL/CSV output are identical.
- **Always writes files.** Even for small runs, the server writes JSONL/CSV/run_meta.json to the output directory. This gives you a persistent audit trail and lets Claude Desktop's filesystem MCP pick up the artifacts for delivery elsewhere.
- **Not all CLI features are exposed.** The wizard, resume flow, and YAML-file path input are CLI-only. The MCP surface is deliberately narrow — one `generate` tool with flat kwargs so Claude's tool picker can compose requests naturally.
