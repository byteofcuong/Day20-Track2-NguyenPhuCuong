#!/usr/bin/env python3
"""02 - Serve: start llama-server.

One launcher for every platform (the old .sh + .ps1 pair is gone). The prebuilt
native binary means /metrics, --parallel and --cont-batching are all available by
default -- there is no second, feature-poor server to switch to.

    make serve                     # chat + /metrics on :8080
    make serve-embed               # embedding regime on :8081 (bonus section 5)

Ports come from LAB_SERVER_PORT / LAB_EMBED_PORT when set. Colab already uses 8080,
which is why the cloud notebook overrides it.
    .venv/bin/python labs/02-serve/serve.py --port 9000
    .venv/bin/python labs/02-serve/serve.py -- --cache-type-k q8_0 --cache-type-v q8_0
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "lib"))
import labkit  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Start llama-server for the lab.",
        epilog="Anything after a bare -- is passed straight to llama-server.",
    )
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--embedding", action="store_true",
                    help="Embedding regime: pooled vectors, no decode loop (bonus C9)")
    ap.add_argument("--model", default=None, help="Override the model from models/active.json")
    ap.add_argument("--compare", action="store_true",
                    help="Serve the comparison quantization instead of the primary")
    ap.add_argument("extra", nargs="*", help="Extra llama-server flags (after --)")
    args = ap.parse_args()

    active = labkit.load_active()
    if args.model:
        model = args.model
    else:
        key = "compare_model" if args.compare else "primary_model"
        model = str(labkit.repo_root() / active[key])
    if not pathlib.Path(model).exists():
        labkit.die(f"Model file not found: {model}", "Run: make setup")

    port = args.port or (labkit.embed_port() if args.embedding else labkit.server_port())
    cmd = labkit.server_cmd(model, port=port, embedding=args.embedding, extra=args.extra)

    quant = active.get("compare_quant" if args.compare else "primary_quant", "?")
    labkit.banner(f"llama-server{' (embedding regime)' if args.embedding else ''} on :{port}")
    print(f"  binary   : {pathlib.Path(cmd[0]).name}  (llama.cpp {labkit.LLAMA_CPP_BUILD})")
    print(f"  model    : {pathlib.Path(model).name}  [{quant}]")
    print(f"  threads  : {labkit.threads()}    ngl: {labkit.n_gpu_layers()}    "
          f"ctx: {labkit.n_ctx()}")
    if not args.embedding:
        print(f"  slots    : {labkit.parallel_slots()} (continuous batching on)")
        print(f"  endpoints: http://localhost:{port}/v1/chat/completions")
        print(f"             http://localhost:{port}/metrics   <- Prometheus, rubric item 7")
        print(f"             http://localhost:{port}/slots     <- per-slot state")
    else:
        print(f"  endpoints: http://localhost:{port}/v1/embeddings")
    print(f"\n  {' '.join(cmd)}\n")

    # Windows has no real exec: os.execv re-quotes argv through the CRT, which splits
    # any argument containing a space. A repo under "D:\Direc of code\..." therefore
    # dies with `error: invalid argument: of`. Run the server as a child there instead
    # -- Ctrl-C still reaches it, because it shares this console's process group.
    if sys.platform == "win32":
        return subprocess.run(cmd, check=False).returncode
    try:
        os.execv(cmd[0], cmd)          # hand the terminal over; Ctrl-C stops the server
    except OSError:
        return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
