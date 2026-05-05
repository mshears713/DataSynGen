#!/usr/bin/env python3
"""
TokenRouter multi-variant smoke test.

Tests four API shapes to identify which one works for this account.

Usage:
  python scripts/tokenrouter_smoke.py            # test gpt-4o on all variants
  python scripts/tokenrouter_smoke.py --sweep    # test multiple models on all variants

Required env:
  TOKENROUTER_API_KEY       Your TokenRouter API key

Optional env:
  TOKENROUTER_BASE_URL      If set, adds a custom (E) variant on top of A-D
  TOKENROUTER_TEST_MODEL    Default model (default: gpt-4o)
  TOKENROUTER_TEST_MESSAGE  Test prompt  (default: "Say OK only.")

See docs/TOKENROUTER_SETUP.md for setup instructions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any


# ---------------------------------------------------------------------------
# Optional .env loading — best-effort, never raises
# ---------------------------------------------------------------------------

def _try_load_dotenv() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    candidates = [
        os.path.join(script_dir, ".env.local"),
        os.path.join(repo_root, "backend", ".env"),
        os.path.join(repo_root, ".env.local"),
    ]

    try:
        from dotenv import load_dotenv  # type: ignore[import]
        for path in candidates:
            if os.path.isfile(path):
                load_dotenv(path, override=False)
                print(f"[env] Loaded via python-dotenv: {path}")
        return
    except ImportError:
        pass

    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
            print(f"[env] Loaded (manual parse): {path}")
        except Exception as exc:
            print(f"[env] Warning — could not read {path}: {exc}")


_try_load_dotenv()


# ---------------------------------------------------------------------------
# Runtime config
# ---------------------------------------------------------------------------

API_KEY: str = os.environ.get("TOKENROUTER_API_KEY", "")
CUSTOM_BASE_URL: str = os.environ.get("TOKENROUTER_BASE_URL", "").rstrip("/")
DEFAULT_MODEL: str = os.environ.get("TOKENROUTER_TEST_MODEL", "gpt-4o")
TEST_MESSAGE: str = os.environ.get("TOKENROUTER_TEST_MESSAGE", "Say OK only.")

SWEEP_MODELS = ["gpt-4o", "auto:fast", "auto:balance", "openai:gpt-4o"]

# (label, base_url, endpoint_path, api_shape)
VARIANTS: list[tuple[str, str, str, str]] = [
    ("A  openai_chat  .com/v1", "https://api.tokenrouter.com/v1", "/chat/completions", "openai_chat"),
    ("B  openai_chat  .io/v1",  "https://api.tokenrouter.io/v1",  "/chat/completions", "openai_chat"),
    ("C  native_route .com",    "https://api.tokenrouter.com",     "/route",            "native_route"),
    ("D  responses    .io",     "https://api.tokenrouter.io",      "/v1/responses",     "responses"),
]


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def _build_payload(shape: str, model: str, message: str) -> dict[str, Any]:
    if shape == "openai_chat":
        return {
            "model": model,
            "messages": [{"role": "user", "content": message}],
            "max_tokens": 5,
        }
    if shape == "native_route":
        return {
            "prompt": message,
            "temperature": 0,
            "max_tokens": 5,
        }
    if shape == "responses":
        return {
            "model": model,
            "input": message,
            "max_tokens": 5,
        }
    raise ValueError(f"Unknown shape: {shape!r}")


# ---------------------------------------------------------------------------
# Single probe
# ---------------------------------------------------------------------------

async def _probe(
    session: Any,  # httpx.AsyncClient
    name: str,
    base: str,
    path: str,
    shape: str,
    model: str,
) -> dict[str, Any]:
    final_url = base.rstrip("/") + path
    payload = _build_payload(shape, model, TEST_MESSAGE)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    t0 = time.monotonic()
    exc_info: str | None = None
    status: int | None = None
    ct: str = ""
    body: str = ""
    parsed: Any = None

    try:
        resp = await session.post(final_url, json=payload, headers=headers, timeout=20.0)
        latency_ms = (time.monotonic() - t0) * 1000
        status = resp.status_code
        ct = resp.headers.get("content-type", "")
        body = resp.text[:1000]
        if "json" in ct or body.lstrip()[:1] in ("{", "["):
            try:
                parsed = resp.json()
            except Exception:
                pass
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        exc_info = f"{type(exc).__name__}: {exc}"

    model_label = "(router decides)" if shape == "native_route" else model

    return {
        "name": name,
        "final_url": final_url,
        "shape": shape,
        "model": model_label,
        "auth_present": bool(API_KEY),
        "status": status,
        "content_type": ct,
        "latency_ms": round(latency_ms),
        "body_excerpt": body,
        "parsed": parsed,
        "exception": exc_info,
        "success": status is not None and 200 <= status < 300,
    }


# ---------------------------------------------------------------------------
# Result printer
# ---------------------------------------------------------------------------

def _print_result(r: dict[str, Any]) -> None:
    print("-" * 60)
    print(f"  Variant      : {r['name']}")
    print(f"  final_url    : {r['final_url']}")
    print(f"  shape        : {r['shape']}")
    print(f"  model        : {r['model']}")
    print(f"  auth_present : {r['auth_present']}")

    if r["exception"]:
        print(f"  exception    : {r['exception']}")
    else:
        print(f"  status       : {r['status']}")
        print(f"  content_type : {r['content_type']}")
        print(f"  latency_ms   : {r['latency_ms']}")
        print()
        if r["parsed"] is not None:
            pretty = json.dumps(r["parsed"], indent=2)[:900]
            print("  Response (JSON):")
            for line in pretty.splitlines():
                print(f"    {line}")
        else:
            print("  Response (text):")
            for line in (r["body_excerpt"] or "(empty)").splitlines()[:20]:
                print(f"    {line}")

    outcome = "SUCCESS" if r["success"] else ("FAILED" if r["status"] is not None else "ERROR")
    print(f"\n  => {outcome}")

    if r["status"] == 404:
        print("     Hint: 404 — wrong endpoint path, wrong base URL, or account routing issue")
        if "<html" in (r["body_excerpt"] or "").lower():
            print("            Body is HTML: this is a CDN/proxy 404, not a proper API error")
    elif r["status"] == 503:
        print("     Hint: 503 — server unavailable or model unsupported on this route")
        print("            Try model gpt-4o, or try a different API shape (--sweep)")
    elif r["status"] == 401:
        print("     Hint: 401 — invalid or expired API key")
    elif r["status"] == 403:
        print("     Hint: 403 — key lacks permission for this endpoint or model")
    elif r["status"] == 422:
        print("     Hint: 422 — malformed request or unsupported model name")
    print()


# ---------------------------------------------------------------------------
# Sweep runner
# ---------------------------------------------------------------------------

async def run_smoke(models: list[str]) -> int:
    try:
        import httpx  # type: ignore[import]
    except ImportError:
        print("ERROR: httpx is not installed.  Run: pip install httpx")
        return 2

    variants = list(VARIANTS)
    if CUSTOM_BASE_URL:
        variants.append((
            "E  custom (TOKENROUTER_BASE_URL)",
            CUSTOM_BASE_URL,
            "/chat/completions",
            "openai_chat",
        ))

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as session:
        for model in models:
            print(f"\n{'='*60}")
            print(f"  Testing model: {model}")
            print(f"{'='*60}\n")
            for name, base, path, shape in variants:
                r = await _probe(session, name, base, path, shape, model)
                _print_result(r)
                results.append(r)

    # Summary
    successes = [r for r in results if r["success"]]
    print("=" * 60)
    print(f"SUMMARY: {len(successes)}/{len(results)} probes succeeded")

    if successes:
        print("\nWorking variants:")
        for r in successes:
            print(f"  {r['name']}  model={r['model']}  url={r['final_url']}")

        best = successes[0]
        # Derive base URL (strip known endpoint suffixes)
        base_url = best["final_url"]
        for suffix in ("/chat/completions", "/route", "/v1/responses"):
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
                break

        print("\nTo configure the backend, set in backend/.env:")
        print(f"  TOKENROUTER_API_MODE={best['shape']}")
        print(f"  TOKENROUTER_BASE_URL={base_url}")
    else:
        print("\nNo variants succeeded.")
        print("  - Verify TOKENROUTER_API_KEY is correct and not revoked")
        print("  - Check network connectivity to tokenrouter.com / tokenrouter.io")
        print("  - Run with --sweep to try additional model names")
        print("  - See docs/TOKENROUTER_SETUP.md")

    print("=" * 60)
    return 0 if successes else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="TokenRouter connectivity smoke test")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help=f"Test multiple models: {SWEEP_MODELS}",
    )
    args = parser.parse_args()

    key_present = bool(API_KEY)
    key_prefix = API_KEY[:6] if API_KEY else "(not set)"

    print()
    print("=" * 60)
    print("TokenRouter Smoke Test")
    print("=" * 60)
    print(f"  api_key  : {'present' if key_present else 'MISSING'} (prefix: {key_prefix}...)")
    if CUSTOM_BASE_URL:
        print(f"  custom base URL: {CUSTOM_BASE_URL}")
    print(f"  models   : {'sweep: ' + ', '.join(SWEEP_MODELS) if args.sweep else DEFAULT_MODEL}")
    print()

    if not key_present:
        print("ERROR: TOKENROUTER_API_KEY is not set.")
        print("  Option 1: create scripts/.env.local with TOKENROUTER_API_KEY=<key>")
        print("  Option 2: export TOKENROUTER_API_KEY=<key>  (PowerShell: $env:TOKENROUTER_API_KEY='<key>')")
        print("  See docs/TOKENROUTER_SETUP.md")
        return 1

    models = SWEEP_MODELS if args.sweep else [DEFAULT_MODEL]
    return asyncio.run(run_smoke(models))


if __name__ == "__main__":
    sys.exit(main())
