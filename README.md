# YouTube Script Generator

Turns a topic + audience/tone/length into a ready-to-record YouTube script using a
multi-agent pipeline — **Outline → Hook → Writer → Critic** — streamed live over SSE and
persisted to SQLite locally / PostgreSQL in production.

The default path costs **$0/month**: Gemini free tier + optional Groq free tier, Render
free web service, Neon free Postgres, Vercel Hobby frontend, Qdrant Cloud free tier.
No paid service is required in the default path.

## What you get

- **Script generation** — long-form (1–30 min) and Shorts, multiple tones/languages.
- **Live progress** — SSE events per agent, per section, per critic revision, plus a
  `llm.retry` event when the fallback chain switches models.
- **Resume / retry** — failed jobs resume from the last completed step.
- **Outline, hook A/B testing, critic feedback, section regeneration.**
- **Export** — TXT, Markdown, DOCX, PDF (and storyboards as JSON/CSV/PDF).
- **Series planner, trend detection, competitor gap analysis.**
- **Dub scripts, TTS preview** (ElevenLabs if configured, otherwise free Edge TTS/501).
- **Voice profiles** stored in Qdrant (in-memory fallback when unconfigured).
- **Collaboration** — workspaces, comments, status workflow, activity log, webhooks.
- **Next.js dashboard** — new script, history, script editor, storyboard, hook tests,
  dub, TTS, trends, plans, billing, settings; API key kept in `localStorage`.
- **Ops-friendly** — JSON logs with secret redaction, optional Sentry, security headers,
  per-key/per-IP rate limits, body-size limit, prompt-injection sanitisation.

## Tech stack

- Python 3.11+ / FastAPI / Pydantic v2 / SQLModel / SQLAlchemy async
- Plain async orchestration (no LangGraph/LangChain)
- Google Gemini + Groq (OpenAI-compatible) with fallback chain, cooldowns, cache
- SQLite locally; PostgreSQL (Neon) in production; Alembic migrations
- SSE streaming; Next.js 15 + TypeScript + Tailwind
- Qdrant Cloud (optional), pytest, ruff, GitHub Actions

## Quick start (Windows, no Docker)

```bat
start_all.bat
```

or PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_all.ps1
```

The script:

1. creates `.venv` if missing and installs `requirements.txt`;
2. creates/repairs `.env` (generates a strong `API_KEY` when empty) and `frontend/.env.local`;
3. runs `alembic upgrade head` (SQLite by default);
4. opens the backend (`http://127.0.0.1:8000`) and frontend (`http://localhost:3000`)
   in two windows and opens the browser;
5. prints your API key — paste it at **Settings** in the app.

Add your free Gemini key to `.env` first:

```env
GEMINI_API_KEY=...        # https://aistudio.google.com/apikey
GROQ_API_KEY=...          # optional free fallback: https://console.groq.com/keys
```

### Manual start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then set API_KEY + GEMINI_API_KEY
python scripts/bootstrap.py
uvicorn app.main:app --reload --port 8000

cd frontend
npm install
npm run dev
```

## Free deployment (no credit card)

Full click-by-click instructions: **[DEPLOY.md](DEPLOY.md#path-b--free-deployment-render--neon--vercel--0-no-credit-card)**.

| Piece | Free service | Notes |
|---|---|---|
| Backend | **Render** free web service (`render.yaml`) | sleeps after 15 min idle (~60 s wake) |
| Database | **Neon** free Postgres | no card, 1 GB, scale-to-zero |
| Frontend | **Vercel** Hobby | set `NEXT_PUBLIC_API_BASE_URL` |
| Vectors | **Qdrant Cloud** free 1 GB | optional; in-memory fallback |
| LLM | **Gemini** free + **Groq** free | fallback chain + quota cooldowns |

Hugging Face Docker Spaces are **not** used: as of Nov 2026 Docker Spaces require a paid
plan (free accounts only get ZeroGPU Gradio).

Cold starts: the frontend shows an amber **“Waking up the free server”** banner and
retries `/health` every 5 s. If a restart interrupts a job, the backend marks it failed
with a retry hint; press **Retry** in the UI.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | Production refuses to boot with an empty/default/<32-char `API_KEY` or `*` CORS. |
| `API_KEY` | — | **Required.** Generate with `python scripts/generate_secret.py`. |
| `ALLOWED_ORIGINS` | localhost:3000 | Comma-separated exact origins. Never `*` in production. |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/...` | Use `postgresql+psycopg://…?sslmode=require` on Neon; `postgresql+asyncpg://…` for local Docker Postgres. |
| `LLM_PROVIDER` | `gemini` | `gemini` (free chain) or `anthropic` (paid). |
| `GEMINI_API_KEY` | — | Google AI Studio key (free). |
| `GEMINI_MODEL_FAST` | `gemini-3.1-flash-lite` | Outline/hook/critic/SEO. |
| `GEMINI_MODEL_WRITER` | `gemini-3.8-flash` | Strongest free writer model first. |
| `GEMINI_MODEL_FALLBACKS` | `gemini-3.1-flash-lite,…` | Ordered chain for 429/503/timeout. |
| `GROQ_API_KEY` | — | Optional second free provider. |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq's strongest free model (Nov 2026 docs). |
| `LLM_REQUESTS_PER_MINUTE` | `8` | Global token bucket for all LLM calls. |
| `LLM_MAX_CONCURRENCY` | `2` | Global async semaphore. |
| `LLM_CACHE_TTL_SECONDS` | `3600` | Exact-match response cache (saves free quota). |
| `GEMINI_REQUEST_TIMEOUT_SECONDS` | `90` | Per-model request timeout. A stalled model is cooled down and the chain tries the next one. |
| `GENERATION_DAILY_LIMIT_PER_USER` | `20` | Generations per API-key owner per UTC day; `0` = unlimited. |
| `RATE_LIMIT_PER_MINUTE` | `10` | Per-key HTTP rate limit (plus per-IP bucket). |
| `MAX_REVISIONS` | `2` | Critic → writer revision loops. |
| `CRITIC_PASS_THRESHOLD` | `8.0` | Critic average needed to pass. |
| `AGENT_TIMEOUT_SECONDS` | `90` | Per-agent timeout so jobs never hang. |
| `EVAL_MODE` | `auto` | `auto` = report-only on free chains; `enforce` = fail below score; `report` = never fail. |
| `EVAL_MIN_SCORE` | `7.0` | Offline eval threshold. |
| `QDRANT_URL` / `QDRANT_API_KEY` | — | Empty = in-memory vector store. |
| `EMBEDDING_MODEL` | `gemini-embedding-2` | Embedding model (dimension auto-detected). |
| `TTS_PROVIDER` | `elevenlabs` | `edge` for free local TTS; otherwise 501 when no key. |
| `ELEVENLABS_API_KEY` | — | Optional; absent → TTS returns 501. |
| `STRIPE_API_KEY` | — | Optional; absent → billing subscribe returns 501. |
| `SENTRY_DSN` | — | Optional error tracking. |
| `LOG_LEVEL` | `INFO` | JSON logs (secrets redacted). |

Anthropic path (optional): `ANTHROPIC_API_KEY`, `LLM_OUTLINE_MODEL`, `LLM_CRITIC_MODEL`,
`LLM_WRITER_MODEL`, `ANTHROPIC_BASE_URL`.

## API

Base URL locally: `http://127.0.0.1:8000`. Interactive docs: `/docs`.
Every `/v1/*` route requires `X-API-Key: $API_KEY`.

| Area | Endpoints |
|---|---|
| Scripts | `POST /v1/scripts/generate`, `GET /v1/scripts`, `GET /v1/scripts/{id}`, `GET /v1/scripts/{id}/stream`, `POST /v1/scripts/{id}/retry`, `POST /v1/scripts/{id}/regenerate-section`, `GET /v1/scripts/{id}/export?format=txt|md|docx|pdf` |
| Quota / jobs | `GET /v1/scripts/quota`, `GET /v1/jobs` |
| Plans | `POST /v1/plans`, `GET /v1/plans/{id}`, `PATCH /v1/plans/{id}/items/{item_id}`, `POST /v1/plans/{plan_id}/items/{item_id}/generate-script` |
| Trends / competitors | `GET /v1/trends`, `POST /v1/trends/refresh`, `POST /v1/competitors/gap` |
| Hooks / dub / TTS / storyboard | `/v1/scripts/{id}/hook-tests`, `/dub`, `/tts`, `/storyboard` (+ `/storyboard/export`) |
| Voice profiles | `POST/GET /v1/voice-profiles`, `POST /v1/voice-profiles/search`, `POST /v1/voice-profiles/import-file` |
| Collaboration | workspaces, comments, status, activity, webhooks |
| YouTube | channel connect + performance insights (in-memory stub, no OAuth yet) |
| Billing | plans, usage, subscribe (Stripe key required, else 501) |
| Feedback / prompts | `POST /v1/feedback`, prompt registry + rollback |
| Health | `GET /health`, `GET /health/vector`, `GET /v1/models` (public) |

Example:

```bash
curl -X POST http://localhost:8000/v1/scripts/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"topic":"Why the sky is blue","audience":"students","tone":"educational",
       "language":"English","duration_minutes":8,"format":"long_form"}'
# -> {"job_id":"…","status":"pending"}

curl -N http://localhost:8000/v1/scripts/<job_id>/stream -H "X-API-Key: $API_KEY"
curl http://localhost:8000/v1/scripts/<job_id> -H "X-API-Key: $API_KEY"
```

`GET /v1/scripts/{id}` includes `model_usage`, e.g. `{"writer":"gemini-3.8-flash","critic":"gemini-3.1-flash-lite"}`.

## Free-tier behavior

- **Fallback chain:** every role tries its primary model, then `GEMINI_MODEL_FALLBACKS`,
  then Groq (if configured). Retries use exponential backoff + jitter.
- **Quota-aware cooldown:** a 429 with `Retry-After` (including daily quotas, often
  12–24 h) puts that model in cooldown until the hint expires, so later calls skip it fast.
- **Timeout-aware fallback:** a model that stalls past `GEMINI_REQUEST_TIMEOUT_SECONDS` is
  skipped for 5 minutes; the writer for the rest of that script uses the next model instead
  of paying the timeout on every section.
- **Rate limiting:** global token bucket + semaphore keep free RPM/TPM budgets intact.
- **Response cache:** identical prompts reuse a cached result for `LLM_CACHE_TTL_SECONDS`.
- **Daily generation quota:** `GENERATION_DAILY_LIMIT_PER_USER` per API-key owner; the UI
  shows remaining quota and disables the button with the reset time when exhausted.
- **Model tiering:** Writer uses the strongest free model available; outline/hook/critic/SEO
  use the lighter fast model.
- **Never hangs:** SSE sends keep-alives and an immediate terminal event when a job already
  finished; failed jobs can be retried from the last completed step.

## Eval

```bash
python -m app.eval
```

Runs 32 benchmark topics through the Writer and an LLM judge, plus deterministic structure
checks. `EVAL_MODE=auto` (default) prints the score and exits 0 on free-tier chains — it
never blocks CI. Set `EVAL_MODE=enforce` to fail when the score is below
`EVAL_MIN_SCORE` (paid keys recommended for realistic scores).

## Tests & CI

```bash
pytest -q
ruff check app tests sdk --select F,E9,E7
python -m compileall -q app tests sdk
python scripts/smoke_test.py     # 40+ PASS/FAIL checks across every router
```

GitHub Actions (`.github/workflows/ci.yml`) runs ruff, compile, pytest, then **builds both
Docker images and smoke-tests the running containers** — so container correctness is
verified from GitHub even if Docker is not installed locally.

## Known limitations (free tier)

- Free LLM quota is daily and model-specific; quality and availability vary. The chain
  degrades gracefully but cannot guarantee paid-model quality.
- Render free spins down after 15 minutes; first request can take ~60 s.
- Render free disk is ephemeral → always use Neon `DATABASE_URL` for real data.
- Neon free scales to zero after 5 minutes (wakes in <1 s).
- Vercel Hobby is intended for personal/non-commercial projects.
- Qdrant free 1 GB; leaving it unset uses an in-memory store (lost on restart).
- YouTube OAuth, Stripe checkout, ElevenLabs, and Tavily are not configured by default;
  those endpoints return a clear 501/503 instead of crashing.
- SSE/background jobs are in-process; a restart marks in-flight jobs failed and offers retry.

## Troubleshooting

| Symptom | Fix |
|---|---|
| First request slow / amber “Waking up” banner | Free host cold start; wait ~60 s. |
| `429 Daily generation limit reached` | Wait for the UTC reset shown in the message, or raise/disable `GENERATION_DAILY_LIMIT_PER_USER`. |
| `429`/`503` from Gemini | Daily quota or overload; the model is cooled down and the chain tries the next one. Add `GROQ_API_KEY`. |
| `501 TTS/Billing not configured` | Set `ELEVENLABS_API_KEY` / `STRIPE_API_KEY`, or use `TTS_PROVIDER=edge`. |
| `401` everywhere | Wrong/missing API key in Settings, or frontend points at the wrong `NEXT_PUBLIC_API_BASE_URL`. |
| CORS error | `ALLOWED_ORIGINS` must be the exact frontend origin (no trailing slash, no `*`). |
| `/health/vector` shows `provider: memory` | `QDRANT_URL`/`QDRANT_API_KEY` unset or wrong; scripts still work. |
| Alembic failure on boot | Use `postgresql+psycopg://` (not `postgres://`) with `?sslmode=require` on Neon. |

## Project structure

```
app/
  api/        routers (scripts, plans, trends, competitors, hooks, dub, tts, storyboard,
              voice_profiles, workspaces, billing, youtube, feedback, webhooks, jobs, prompts)
  agents/     outline, hook, writer, critic, planner, trend, gap, guardrails, translator, storyboard…
  pipeline/   state, runner, events (SSE bus)
  services/   llm_client, llm_runtime, generation, jobs, quota, export, vector_store, security_utils…
  models/     SQLModel tables
  schemas/    Pydantic request/response models
  eval/       benchmarks, checks, judge, runner, CLI
  core/       config, security, logging
  main.py     app wiring, lifespan, security middleware
frontend/     Next.js dashboard (standalone build)
scripts/      bootstrap.py, generate_secret.py, smoke_test.py
alembic/      migrations (0001 initial, 0002 owner)
Dockerfile.backend, frontend/Dockerfile, docker-compose.prod.yml, Caddyfile
render.yaml, .github/workflows/ci.yml, DEPLOY.md
```

## Security notes

- No default API key; production startup fails on weak keys and wildcard CORS.
- Per-key + per-IP rate limits, 6 MB request body ceiling, validated uploads (type/size).
- Security headers on every response; HSTS in production.
- Fetched competitor content is sanitised before it reaches prompts (prompt-injection guard).
- Logs redact Gemini/Groq/Qdrant/ElevenLabs/Stripe/API keys; `/health` exposes no secrets.
- Never commit `.env`; `.gitignore`/`.dockerignore` already exclude secrets, DBs, audio, exports.
