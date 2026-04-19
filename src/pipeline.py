"""Async orchestrator: N single-response calls -> JSONL."""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import httpx
from tqdm import tqdm

from .cost import CostTracker
from .llm.interface import LLMProvider, ProviderError
from .models import (
    ExperimentConfig,
    GenerationResult,
    LLMRequest,
    MotiveMatrix,
    MotivePresent,
    RunSummary,
)
from .rate_limit import RateLimiter

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_response(raw: str) -> tuple[str | None, str | None, list[MotivePresent]]:
    """Accept {'responses':[{...}]} or flat {...}. Return (text, text_deutsch, motives_present)."""
    data = json.loads(raw)
    if isinstance(data, dict) and "responses" in data:
        arr = data["responses"]
        if not isinstance(arr, list) or not arr:
            raise ValueError("'responses' array empty or not a list")
        entry = arr[0]
    elif isinstance(data, dict) and "text" in data:
        entry = data
    else:
        raise ValueError("response missing 'responses' array or 'text' field")

    if not isinstance(entry, dict):
        raise ValueError("response entry is not an object")
    text = entry.get("text")
    text_deutsch = entry.get("text_deutsch")
    motives_raw = entry.get("motives_present") or []
    motives = [
        MotivePresent(
            id=str(m["id"]),
            name=str(m.get("name", "")),
            strength=float(m.get("strength", 0)),
        )
        for m in motives_raw
        if isinstance(m, dict) and "id" in m
    ]
    return (
        text if isinstance(text, str) else None,
        text_deutsch if isinstance(text_deutsch, str) else None,
        motives,
    )


class _JsonlWriter:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._fh = path.open("a", encoding="utf-8")

    async def append(self, result: GenerationResult) -> None:
        async with self._lock:
            self._fh.write(json.dumps(result.to_json(), ensure_ascii=False) + "\n")
            self._fh.flush()
            import os
            os.fsync(self._fh.fileno())

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


def _load_completed_response_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    done: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("status") == "ok":
                done.add(int(rec["response_id"]))
        except Exception:
            continue
    return done


_RL_WARN_THRESHOLD = 0.25  # warn if >25% of early calls hit rate limits
_RL_WARN_WINDOW = 20        # ...within the first 20 calls


def _classify_error(msg: str | None) -> str:
    if not msg:
        return "unknown"
    m = msg.lower()
    if "rate" in m or "429" in m or "tpm" in m or "rpm" in m or "rate_limit" in m:
        return "rate_limited"
    if "timeout" in m or "network" in m:
        return "network"
    if "invalid json" in m or "malformed response" in m or "'responses'" in m:
        return "parse_error"
    if "401" in m or "403" in m:
        return "auth"
    if "context" in m or "400" in m:
        return "bad_request"
    return "other"


async def run(
    cfg: ExperimentConfig,
    matrix: MotiveMatrix,  # noqa: ARG001 (reserved for phase 2)
    provider: LLMProvider,
    request: LLMRequest,
    *,
    output_dir: Path,
    resume_path: Path | None = None,
    show_progress: bool = True,
) -> RunSummary:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "results.jsonl"

    completed = _load_completed_response_ids(resume_path) if resume_path else set()
    if resume_path and resume_path != jsonl_path:
        # copy prior progress into the new file so everything ends up in one place.
        jsonl_path.write_bytes(resume_path.read_bytes())

    writer = _JsonlWriter(jsonl_path)
    tracker = CostTracker(provider)
    sem = asyncio.Semaphore(cfg.concurrency)
    shutdown = asyncio.Event()

    limiter = RateLimiter(
        requests_per_minute=cfg.requests_per_minute,
        tokens_per_minute=cfg.tokens_per_minute,
    )
    # Estimate per-call token cost for TPM reservations (input exact + max output).
    input_tokens_est = provider.count_tokens(request.system, request.user)
    per_call_reserve = input_tokens_est + request.max_tokens

    failure_counts: dict[str, int] = {}
    rl_seen_early = 0

    loop = asyncio.get_running_loop()
    prev_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(signum, frame):  # noqa: ARG001
        if shutdown.is_set():
            # Second Ctrl+C: hard exit.
            raise KeyboardInterrupt
        print("\ninterrupt received; draining in-flight calls (Ctrl+C again to hard-exit)")
        shutdown.set()

    try:
        signal.signal(signal.SIGINT, _on_sigint)
    except ValueError:
        # Not main thread; skip custom handler.
        pass

    results_count = {"ok": 0, "failed": 0, "skipped": 0}
    start = time.time()

    pbar = tqdm(
        total=cfg.n_responses,
        disable=not show_progress,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] {postfix}",
    )
    pbar.set_postfix_str("$0.00")

    async def _run_one(client: httpx.AsyncClient, idx: int) -> None:
        nonlocal rl_seen_early
        if shutdown.is_set():
            return
        response_id = idx + 1
        if response_id in completed:
            results_count["skipped"] += 1
            pbar.update(1)
            return

        async with sem:
            if shutdown.is_set():
                return
            if limiter.enabled:
                await limiter.acquire(per_call_reserve)
            attempts_on_parse = 0
            raw = ""
            last_error: str | None = None
            text = text_deutsch = None
            motives_present: list[MotivePresent] = []
            tokens_in = tokens_out = 0
            model_used = provider.model_name()
            req_id: str | None = None

            while attempts_on_parse < 2:
                try:
                    resp = await provider.complete(client, request)
                    raw = resp.text
                    tokens_in = resp.tokens_in
                    tokens_out = resp.tokens_out
                    model_used = resp.model
                    req_id = resp.request_id
                    text, text_deutsch, motives_present = _parse_response(raw)
                    last_error = None
                    break
                except (ValueError, json.JSONDecodeError) as exc:
                    attempts_on_parse += 1
                    last_error = f"invalid JSON: {exc}"
                    if attempts_on_parse >= 2:
                        break
                except ProviderError as exc:
                    last_error = str(exc)
                    break
                except Exception as exc:  # unexpected
                    last_error = f"unexpected: {exc!r}"
                    break

            status = "ok" if last_error is None and text is not None else "failed"
            tracker.record(tokens_in, tokens_out)

            if status == "failed":
                cls = _classify_error(last_error)
                failure_counts[cls] = failure_counts.get(cls, 0) + 1
                if cls == "rate_limited" and idx < _RL_WARN_WINDOW:
                    rl_seen_early += 1
                    if rl_seen_early / max(1, idx + 1) > _RL_WARN_THRESHOLD and not limiter.enabled:
                        pbar.write(
                            "heads up: rate limits observed early. "
                            "Consider setting `runtime.requests_per_minute` / "
                            "`runtime.tokens_per_minute` in your config, "
                            "or lowering `runtime.concurrency`."
                        )

            result = GenerationResult(
                call_index=idx,
                response_id=response_id,
                status=status,
                text=text,
                text_deutsch=text_deutsch,
                motives_present=motives_present,
                ground_truth=list(cfg.motives),
                raw_response=raw,
                error=last_error,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=model_used,
                openai_request_id=req_id,
                created_at=_now_iso(),
            )
            await writer.append(result)
            results_count[status] += 1
            pbar.update(1)
            pbar.set_postfix_str(f"${tracker.cost_usd:.2f}")

    try:
        async with httpx.AsyncClient() as client:
            tasks = [
                asyncio.create_task(_run_one(client, i)) for i in range(cfg.n_responses)
            ]
            await asyncio.gather(*tasks, return_exceptions=False)
    finally:
        pbar.close()
        writer.close()
        try:
            signal.signal(signal.SIGINT, prev_handler)
        except Exception:
            pass

    elapsed = time.time() - start
    return RunSummary(
        n_requested=cfg.n_responses,
        n_completed=results_count["ok"],
        n_failed=results_count["failed"],
        tokens_in_total=tracker.tokens_in,
        tokens_out_total=tracker.tokens_out,
        cost_usd_total=tracker.cost_usd,
        elapsed_seconds=elapsed,
        output_dir=output_dir,
        results_jsonl=jsonl_path,
        failure_breakdown=failure_counts,
    )


def iter_results(path: Path) -> Iterable[GenerationResult]:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        yield GenerationResult.from_json(json.loads(line))
