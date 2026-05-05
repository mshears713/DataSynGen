# TokenRouter Setup & Smoke Test

## Quick start

1. Create a temporary API key in the TokenRouter dashboard.
2. Copy the example env:
   ```
   cp scripts/tokenrouter_smoke.env.example scripts/.env.local
   ```
3. Edit `scripts/.env.local` and set `TOKENROUTER_API_KEY=<your key>`.
4. Run from the repo root:
   ```
   python scripts/tokenrouter_smoke.py
   ```
5. Revoke/delete the temporary key afterward.

PowerShell alternative (no file needed):
```powershell
$env:TOKENROUTER_API_KEY = "sk-..."
python scripts/tokenrouter_smoke.py
```

---

## Testing multiple models

```
python scripts/tokenrouter_smoke.py --sweep
```

Default sweep tests: `gpt-4o`, `auto:fast`, `auto:balance`, `openai:gpt-4o`

To test a specific model:
```powershell
$env:TOKENROUTER_TEST_MODEL = "openai/gpt-4o-mini"
python scripts/tokenrouter_smoke.py
```

---

## Confirmed findings (tested 2026-05-05)

### Working configuration

| Setting | Value |
|---------|-------|
| `TOKENROUTER_BASE_URL` | `https://api.tokenrouter.com/v1` |
| `TOKENROUTER_API_MODE` | `openai_chat` |
| Endpoint | `POST /chat/completions` |

### Root cause of prior failures

| URL tried | Result | Reason |
|-----------|--------|--------|
| `api.tokenrouter.ai` | DNS failure | Dead domain |
| `api.tokenrouter.io/v1/chat/completions` | HTML 404 | CDN/proxy, not an API endpoint |
| `api.tokenrouter.com/v1/chat/completions` + `gpt-4o` | JSON 503 `model_not_found` | Wrong model name for this account group |
| `api.tokenrouter.com/v1/chat/completions` + `openai/gpt-4o-mini` | **200 OK** | ✓ Works |
| `api.tokenrouter.com/v1/chat/completions` + `google/gemini-3-flash-preview` | **200 OK** | ✓ Works |

**Key insight**: This account's group uses prefixed model IDs (`provider/model-name`).
Generic names like `gpt-4o`, `auto:fast`, `google/gemini-flash` are not available.

### Available text models for this account

Models confirmed via `GET /v1/models` — all use `openai` endpoint type (i.e., `openai_chat` mode):

| Model ID | Notes |
|----------|-------|
| `google/gemini-3-flash-preview` | Fast, cheap — replacement for `google/gemini-flash` |
| `google/gemini-3.1-pro-preview` | Higher quality Google model |
| `openai/gpt-4o-mini` | Fast OpenAI — replacement for `openai/gpt-4.1` |
| `openai/gpt-5-mini` | Newer OpenAI small model |
| `openai/gpt-5.4` | Higher quality OpenAI |
| `deepseek/deepseek-v4-flash` | Very fast, cheap |
| `deepseek/deepseek-v3.2` | High quality |
| `qwen/qwen3.5-flash` | Fast Qwen |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | **Free tier** |
| `claude-haiku-4-5` | Anthropic Haiku (openai endpoint) |

---

## Required `dataset_config.yaml` changes

The pipeline config in `backend/data/configs/dataset_config.yaml` uses model names that don't
exist on this account. Update the `models:` section:

| Current (broken) | Replace with |
|-----------------|-------------|
| `google/gemini-flash` | `google/gemini-3-flash-preview` |
| `openai/gpt-4.1` | `openai/gpt-4o-mini` |

---

## Backend configuration after smoke passes

Set in `backend/.env`:

```
TOKENROUTER_BASE_URL=https://api.tokenrouter.com/v1
TOKENROUTER_API_MODE=openai_chat
TOKENROUTER_API_KEY=<your-production-key>
```

Restart the backend (settings are cached with `lru_cache`).

---

## What the smoke script tests

The script fires the same tiny request (`"Say OK only."`, max_tokens=5) against four
API shape variants:

| Variant | Base URL | Endpoint | Body shape |
|---------|----------|----------|------------|
| A | `https://api.tokenrouter.com/v1` | `/chat/completions` | `{model, messages}` |
| B | `https://api.tokenrouter.io/v1`  | `/chat/completions` | `{model, messages}` |
| C | `https://api.tokenrouter.com`    | `/route`            | `{prompt}` (no model) |
| D | `https://api.tokenrouter.io`     | `/v1/responses`     | `{model, input}` |

If `TOKENROUTER_BASE_URL` is set, a custom variant (E) is added.

---

## Interpreting results

| Status | Meaning | Next step |
|--------|---------|-----------|
| DNS / connect error | Domain unreachable | `.ai` is dead; check network |
| HTML 404 | CDN 404 — wrong endpoint | Try variant A |
| JSON 503 `model_not_found` | Endpoint works, model name wrong | Check `/v1/models` for valid IDs |
| JSON 401 | API key invalid or expired | Regenerate key |
| JSON 403 | Key lacks permission | Check key scopes |
| JSON 422 | Malformed request | Usually model name format issue |
| 200 empty body | `/route` always does this — not useful | Use variant A |
| 2xx with JSON | Working | Note model + endpoint |

---

## API mode reference

| Mode | Endpoint suffix | Body keys | Response key |
|------|----------------|-----------|--------------|
| `openai_chat` (**confirmed working**) | `/chat/completions` | `model`, `messages` | `choices[0].message.content` |
| `native_route` | `/route` | `prompt`, `temperature` | `response` / `text` |
| `responses` | `/responses` | `model`, `input` | `output[0].content[0].text` |

---

## Recommended run size until smoke passes

Keep `target_count=1` on test runs so a failing API call doesn't retry 3× across
5 samples. Once the smoke test returns 2xx, increase to normal batch sizes.
