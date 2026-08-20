#!/usr/bin/env python3
"""BONUS challenge C2 - KV cache quantization: what --cache-type-k/v q8_0 really costs.

The deck sells "FP8 KV cache" as free memory. This checks that claim on the hardware
you actually have, and it checks all three things C2 asks for instead of only the
flattering one:

  1. memory   -- GPU / host footprint of the server process at 2k / 8k / 16k context
  2. latency  -- TTFT and TPOT over HTTP, same prompts, same temperature
  3. quality  -- a 10-prompt auto-gradable eval (arithmetic + JSON extraction)

Memory saved while accuracy quietly drops is not a win, which is why the eval is here
rather than left to "it looked fine".

    .venv/bin/python bonus/c2-kv-cache-quant.py
    .venv/bin/python bonus/c2-kv-cache-quant.py --ctx-grid 2048,8192   # shorter run
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import labkit  # noqa: E402

C2_PORT = 8097          # off :8080 so a lab server can stay up
KV_TYPES = ["f16", "q8_0"]

# Auto-gradable eval. Deliberately easy: the question is whether quantizing the KV
# cache changes the answers, not whether a 2B model can do hard arithmetic.
ARITH_EVAL: list[tuple[str, str]] = [
    ("What is 12 + 35? Reply with only the number.", "47"),
    ("What is 9 * 7? Reply with only the number.", "63"),
    ("What is 100 - 37? Reply with only the number.", "63"),
    ("What is 6 * 8? Reply with only the number.", "48"),
    ("What is 144 / 12? Reply with only the number.", "12"),
]
JSON_EVAL: list[tuple[str, dict]] = [
    ('Extract name and age as JSON with keys "name" and "age". Text: "Mai is 27 years old."'
     " Reply with only the JSON object.", {"name": "mai", "age": 27}),
    ('Extract name and age as JSON with keys "name" and "age". Text: "Hoang, aged 41, works'
     ' here." Reply with only the JSON object.', {"name": "hoang", "age": 41}),
    ('Extract city and country as JSON with keys "city" and "country". Text: "She flew to'
     ' Hanoi, Vietnam." Reply with only the JSON object.', {"city": "hanoi", "country": "vietnam"}),
    ('Extract product and price as JSON with keys "product" and "price". Text: "The mouse'
     ' costs 25 dollars." Reply with only the JSON object.', {"product": "mouse", "price": 25}),
    ('Extract language and year as JSON with keys "language" and "year". Text: "Python was'
     ' released in 1991." Reply with only the JSON object.', {"language": "python", "year": 1991}),
]

LAT_PROMPTS = [
    "Explain TTFT and TPOT in one sentence each.",
    "What is PagedAttention and what problem does it solve?",
    "What is the difference between continuous and static batching?",
    "Explain prefix caching in two sentences.",
    "Why is decode bounded by memory bandwidth?",
    "Name two reasons to enable prefix caching.",
]


# --------------------------------------------------------------- server control

def start_server(model: str, kv_type: str, ctx: int) -> tuple[subprocess.Popen | None, str]:
    """Start llama-server with a given KV cache type. proc is None when it failed."""
    os.environ["LAB_N_CTX"] = str(ctx)
    cmd = labkit.server_cmd(model, port=C2_PORT,
                            extra=["--cache-type-k", kv_type, "--cache-type-v", kv_type])
    log_path = labkit.bench_dir() / f".c2-server-{kv_type}-{ctx}.log"
    log = open(log_path, "w")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    if labkit.wait_healthy(C2_PORT, timeout=180.0, proc=proc):
        return proc, ""
    stop_server(proc)
    log.close()
    try:
        tail = "".join(open(log_path).readlines()[-8:]).strip()
    except OSError:
        tail = ""
    return None, tail or "server did not become healthy"


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


# --------------------------------------------------------------- memory probes

def gpu_used_mib() -> float:
    """Whole-device GPU memory in use, MiB. 0.0 when there is no nvidia-smi."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=False,
        ).stdout.strip().splitlines()
        return float(out[0]) if out else 0.0
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def proc_rss_mib(pid: int) -> float:
    try:
        import psutil
        return psutil.Process(pid).memory_info().rss / 1024**2
    except Exception:  # noqa: BLE001 - psutil is optional; a missing number is not fatal
        return 0.0


# --------------------------------------------------------------- measurement

def pct(data: list[float], q: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    return s[min(max(0, math.ceil(q / 100.0 * len(s)) - 1), len(s) - 1)]


def stream_once(base: str, prompt: str, max_tokens: int) -> dict | None:
    """Same measurement shape as labs/01-measure/benchmark.py: client-side TTFT."""
    payload = {"model": "local", "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": 0.0, "stream": True}
    start = time.perf_counter()
    first_at, chunks, timings = None, 0, None
    try:
        with httpx.stream("POST", f"{base}/v1/chat/completions", json=payload, timeout=300.0) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                blob = line[6:].strip()
                if blob == "[DONE]":
                    break
                try:
                    obj = json.loads(blob)
                except ValueError:
                    continue
                if obj.get("timings"):
                    timings = obj["timings"]
                if ((obj.get("choices") or [{}])[0].get("delta") or {}).get("content"):
                    first_at = first_at or time.perf_counter()
                    chunks += 1
    except httpx.HTTPError:
        return None
    if first_at is None:
        return None
    n_out = int((timings or {}).get("predicted_n") or chunks)
    return {"ttft_ms": (first_at - start) * 1000.0,
            "tpot_ms": (time.perf_counter() - first_at) * 1000.0 / max(n_out - 1, 1)}


def ask(base: str, prompt: str, max_tokens: int = 48) -> str:
    try:
        r = httpx.post(f"{base}/v1/chat/completions",
                       json={"model": "local", "messages": [{"role": "user", "content": prompt}],
                             "max_tokens": max_tokens, "temperature": 0.0}, timeout=300.0)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError):
        return ""


def grade(base: str) -> tuple[int, int, list[dict]]:
    """(passed, total, per-item detail) over the arithmetic + JSON eval."""
    detail: list[dict] = []
    passed = 0
    for prompt, expected in ARITH_EVAL:
        got = ask(base, prompt)
        ok = expected in re.findall(r"-?\d+", got.replace(",", ""))
        passed += ok
        detail.append({"kind": "arith", "expected": expected, "got": got[:80], "ok": bool(ok)})
    for prompt, expected in JSON_EVAL:
        got = ask(base, prompt, max_tokens=80)
        ok = False
        m = re.search(r"\{.*?\}", got, re.DOTALL)
        if m:
            try:
                obj = {str(k).lower(): v for k, v in json.loads(m.group()).items()}
                ok = all(
                    str(obj.get(k, "")).lower().strip().rstrip(".") == str(v).lower()
                    for k, v in expected.items()
                )
            except ValueError:
                ok = False
        passed += ok
        detail.append({"kind": "json", "expected": expected, "got": got[:80], "ok": bool(ok)})
    return passed, len(ARITH_EVAL) + len(JSON_EVAL), detail


def measure(model: str, kv_type: str, ctx: int, with_eval: bool) -> dict:
    base_gpu = gpu_used_mib()
    labkit.banner(f"KV cache = {kv_type}   ctx = {ctx}")
    proc, err = start_server(model, kv_type, ctx)
    if proc is None:
        print(f"  !! server failed to start: {err[:200]}")
        return {"kv": kv_type, "ctx": ctx, "started": False, "error": err[:400]}

    time.sleep(3.0)                      # let allocations settle before reading memory
    gpu_after = gpu_used_mib()
    rss = proc_rss_mib(proc.pid)
    base_url = f"http://127.0.0.1:{C2_PORT}"
    row: dict = {"kv": kv_type, "ctx": ctx, "started": True,
                 "gpu_delta_mib": round(gpu_after - base_gpu, 1),
                 "gpu_total_mib": round(gpu_after, 1),
                 "host_rss_mib": round(rss, 1)}
    print(f"  GPU in use {gpu_after:.0f} MiB (delta {row['gpu_delta_mib']:+.0f})  "
          f"host RSS {rss:.0f} MiB")

    if with_eval:
        stream_once(base_url, "Hello.", 8)      # warm-up, never counted
        lat = [r for p in LAT_PROMPTS if (r := stream_once(base_url, p, 64))]
        if lat:
            row["ttft_p50"] = round(pct([r["ttft_ms"] for r in lat], 50), 1)
            row["ttft_p95"] = round(pct([r["ttft_ms"] for r in lat], 95), 1)
            row["tpot_p50"] = round(pct([r["tpot_ms"] for r in lat], 50), 2)
            row["decode_tok_s"] = round(1000.0 / max(row["tpot_p50"], 1e-6), 1)
            print(f"  TTFT p50 {row['ttft_p50']} ms - TPOT p50 {row['tpot_p50']} ms "
                  f"({row['decode_tok_s']} tok/s)")
        ok, total, detail = grade(base_url)
        row.update(eval_passed=ok, eval_total=total, eval_detail=detail)
        print(f"  eval: {ok}/{total} correct")

    stop_server(proc)
    time.sleep(2.0)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="C2 - KV cache quantization (bonus B4).")
    ap.add_argument("--ctx-grid", default="2048,8192,16384")
    ap.add_argument("--eval-ctx", type=int, default=2048,
                    help="Context size at which latency + quality are measured")
    args = ap.parse_args()

    active = labkit.load_active()
    hw = labkit.load_hardware(required=False)
    model = str(labkit.repo_root() / active["primary_model"])
    grid = [int(x) for x in args.ctx_grid.split(",") if x.strip()]

    print(f"model   : {pathlib.Path(model).name}")
    print(f"threads : {labkit.threads(hw)}  ngl: {labkit.n_gpu_layers(hw)}  "
          f"parallel: {labkit.parallel_slots()}")
    print(f"ctx grid: {grid}   eval at ctx {args.eval_ctx}\n")

    rows: list[dict] = []
    for ctx in grid:
        for kv in KV_TYPES:
            rows.append(measure(model, kv, ctx, with_eval=(ctx == args.eval_ctx)))

    ok_rows = [r for r in rows if r["started"]]
    if not ok_rows:
        labkit.die("No configuration started successfully.")

    mem_tbl = labkit.md_table(
        ["ctx", "cache-type-k/v", "GPU in use (MiB)", "GPU delta vs idle (MiB)", "Host RSS (MiB)"],
        [[r["ctx"], f"`{r['kv']}`",
          f"{r['gpu_total_mib']:.0f}" if r["started"] else "n/a",
          f"{r['gpu_delta_mib']:+.0f}" if r["started"] else "n/a",
          f"{r['host_rss_mib']:.0f}" if r["started"] else "failed to start"]
         for r in rows],
    )

    ev = [r for r in ok_rows if "eval_passed" in r]
    lat_tbl = labkit.md_table(
        ["cache-type-k/v", "TTFT P50/P95 (ms)", "TPOT P50 (ms)", "Decode (tok/s)", "Eval correct"],
        [[f"`{r['kv']}`", f"{r.get('ttft_p50', 0):.0f} / {r.get('ttft_p95', 0):.0f}",
          f"{r.get('tpot_p50', 0):.2f}", f"{r.get('decode_tok_s', 0):.1f}",
          f"{r['eval_passed']}/{r['eval_total']}"] for r in ev],
    )

    def saving(ctx: int) -> str:
        f16 = next((r for r in ok_rows if r["ctx"] == ctx and r["kv"] == "f16"), None)
        q8 = next((r for r in ok_rows if r["ctx"] == ctx and r["kv"] == "q8_0"), None)
        if not f16 or not q8:
            return f"- ctx {ctx}: one of the two configurations did not start."
        d = f16["gpu_total_mib"] - q8["gpu_total_mib"]
        return (f"- ctx {ctx}: `q8_0` holds **{d:+.0f} MiB** less GPU memory than `f16` "
                f"({f16['gpu_total_mib']:.0f} -> {q8['gpu_total_mib']:.0f} MiB in use).")

    failed = [r for r in rows if not r["started"]]
    failed_block = ""
    if failed:
        failed_block = "\n".join(
            "> **`{kv}` at ctx {ctx} did not start.** Last log line: `{line}`".format(
                kv=r["kv"], ctx=r["ctx"],
                line=((r.get("error") or "").strip().splitlines() or [""])[-1][:160])
            for r in failed
        ) + "\n"

    md = f"""# Bonus C2 - KV cache quantization (`--cache-type-k/v`)

Host `{labkit.host_tag()}` - model `{pathlib.Path(model).name}` -
llama.cpp `{labkit.LLAMA_CPP_BUILD}` - `threads={labkit.threads(hw)}` -
`ngl={labkit.n_gpu_layers(hw)}` - `--parallel {labkit.parallel_slots()}`
Latency and quality measured at `ctx={args.eval_ctx}`, `temperature=0`, warm-up discarded.

## 1. Memory footprint

{mem_tbl}

{chr(10).join(saving(c) for c in grid)}
{failed_block}
GPU figures are whole-device readings from `nvidia-smi`, taken ~3 s after the server
reports healthy, so they include the desktop's own usage; the delta column is the part
this server added. Host RSS is the llama-server process itself.

## 2. Latency and quality at ctx {args.eval_ctx}

{lat_tbl}

The eval is 5 arithmetic + 5 JSON-extraction prompts, graded automatically at
`temperature=0`. It is a *regression check*, not a benchmark: the question is whether
the answers change when the KV cache loses precision.

## Your finding (required -- replace this line)

_Did the memory saving cost you accuracy? Trading memory for quality is not a win --
say which side of that trade this machine landed on, and at what context length the
saving starts to matter._
"""
    out = labkit.write_report("bonus-c2-kv-cache-quant.md", md, rows)
    print("\n" + md)
    print(f"==> Wrote {out.relative_to(labkit.repo_root())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
