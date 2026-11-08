# Deployment Guide — YouTube Script Generator

Three deployment paths:

1. **Free managed (recommended for $0):** Render + Neon + Vercel — **no credit card**, cold starts.
2. **Single VPS** with Docker Compose — ~$5–10/month, always-on, no cold starts.
3. **Railway** — managed paid alternative.

Domain + HTTPS included on all. Qdrant stays on **Qdrant Cloud** (free tier available).

## Prerequisites
- A GitHub account (free)
- Google AI Studio API key (Gemini): https://aistudio.google.com/apikey (free, no card)
- Optional: Groq free key https://console.groq.com and Qdrant Cloud free cluster https://cloud.qdrant.io
- VPS path only: a domain and a server

---

## Path A — Single VPS with Docker Compose

### 1. Create the server
- **Hetzner CX22** (2 vCPU, 4 GB RAM) — €4.50/mo, or **DigitalOcean Basic** $12/mo, or **Oracle Cloud Always Free** ($0)
- Ubuntu 22.04/24.04, SSH key auth

### 2. Install Docker
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # re-login afterwards
sudo apt-get update && sudo apt-get install -y docker-compose-plugin
```

### 3. DNS
Create an A record: `app.example.com` → your VPS public IP. Wait for propagation (`dig app.example.com`).

### 4. Get the code
```bash
git clone <your-repo-url> youtube_script_generator
cd youtube_script_generator
```

### 5. Configure environment
```bash
cp .env.production.example .env.production
python3 scripts/generate_secret.py   # prints a strong 64-char API_KEY — paste it
nano .env.production                 # fill every value
```

Minimum required (app **refuses to boot** without them):

| Variable | Where to get it |
|---|---|
| `API_KEY` | `python scripts/generate_secret.py` |
| `POSTGRES_PASSWORD` | `openssl rand -hex 32` |
| `DOMAIN` | your domain |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `QDRANT_URL` / `QDRANT_API_KEY` | Qdrant Cloud → Clusters → your cluster → API Keys |
| `DATABASE_URL` | `postgresql+asyncpg://ysg:$POSTGRES_PASSWORD@db:5432/ysg` |

### 6. Launch
```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api   # watch startup
```

The API image runs `alembic upgrade head` on boot — all tables are created automatically.

### 7. Verify
```bash
curl https://app.example.com/health                 # {"status":"ok"}
curl https://app.example.com/health/vector         # {"status":"ok","provider":"qdrant",...}
curl https://app.example.com/docs                  # Swagger UI
docker compose -f docker-compose.prod.yml exec api python scripts/smoke_test.py
```

Then open `https://app.example.com` in the browser.

### Backups (set up immediately)
```bash
# Daily Postgres dump (add to crontab: 0 3 * * *)
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U ysg ysg | gzip > /opt/backups/ysg-$(date +%F).sql.gz
# Keep 14 days
find /opt/backups -name 'ysg-*.sql.gz' -mtime +14 -delete
```

### Updating / rollbacks
```bash
cd youtube_script_generator
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build api
# Rollback:
git checkout <previous-tag>
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build api
```

---

## Path B — Free deployment (Render + Neon + Vercel) — $0, no credit card

### Why this combination (checked November 2026)

| Service | Free tier | Card required? | Catch |
|---|---|---|---|
| **Render** web service | 512 MB RAM, 750 instance-hours/month, free TLS, custom domains | No | Spins down after 15 min idle (~60 s cold start); ephemeral disk |
| **Neon** Postgres | Permanent free plan, 1 GB storage/project, 100 CU-hours/project/month, scale-to-zero | **No** | Compute sleeps after 5 min idle (wakes in <1 s) |
| **Vercel** Hobby | Next.js hosting + CDN | **No** | Personal / non-commercial projects |
| **Hugging Face Spaces** | Docker Spaces are **no longer free** (free accounts only get ZeroGPU Gradio) | — | Ruled out |
| **Qdrant Cloud** | 1 GB cluster | No | Optional; app falls back to in-memory |

This is why the backend goes to Render (not HF Spaces), the database to Neon (Render's free
Postgres expires after 30 days), and the frontend to Vercel.

### 1. Push the repo to GitHub
```bash
git init && git add . && git commit -m "YouTube Script Generator"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```
GitHub Actions then runs ruff + compile + pytest, builds both Docker images, and smoke-tests them.

### 2. Create the free Neon database
1. Go to https://neon.com → **Sign up** (no card) → **New Project**.
2. Choose the region closest to your Render region (e.g. `us-east` / Oregon).
3. Copy the **connection string** (Direct connection, not the pooled one).
4. Convert the scheme for SQLAlchemy async. Use **psycopg 3** (`+psycopg`), because it
   understands Neon's `sslmode=require` (asyncpg does not):
   ```
   postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
   → postgresql+psycopg://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
   ```
5. Keep it for step 3.

### 3. Deploy the backend on Render
1. Render Dashboard → **New** → **Blueprint** → connect your GitHub repo.
2. Render reads `render.yaml` and proposes `youtube-script-generator-api` on the **Free** plan.
3. Fill every `sync: false` variable:

   | Variable | Value |
   |---|---|
   | `API_KEY` | output of `python scripts/generate_secret.py` |
   | `DATABASE_URL` | `postgresql+psycopg://…?sslmode=require` from step 2 |
   | `GEMINI_API_KEY` | https://aistudio.google.com/apikey (free) |
   | `GROQ_API_KEY` | https://console.groq.com/keys (optional, free fallback) |
   | `ALLOWED_ORIGINS` | leave blank for now; set it in step 5 |
   | `QDRANT_URL` / `QDRANT_API_KEY` | optional; empty = in-memory |

4. Click **Apply**. First build takes a few minutes.
5. Verify: `https://<api-name>.onrender.com/health` → `{"status":"ok"}`.
   The service sleeps after 15 idle minutes; the first request takes ~60 s.

### 4. Deploy the frontend on Vercel
1. https://vercel.com → **Add New** → **Project** → import the same repo.
2. **Root Directory** = `frontend` (framework auto-detects Next.js).
3. Environment variable:
   ```
   NEXT_PUBLIC_API_BASE_URL = https://<api-name>.onrender.com
   ```
4. **Deploy**. Copy the production domain, e.g. `https://your-app.vercel.app`.

### 5. Wire CORS
1. Render Dashboard → your API service → **Environment**.
2. Set `ALLOWED_ORIGINS` to the exact Vercel origin:
   ```
   ALLOWED_ORIGINS=https://your-app.vercel.app
   ```
   No trailing slash, no `*`.
3. Save — Render restarts the service automatically.

### 6. First run
1. Open the Vercel URL → **Settings** → paste `API_KEY` → **Save**.
2. Generate a script. If the backend was asleep, the amber *"Waking up the free server"*
   banner appears and retries automatically.
3. If Render restarted mid-generation, the job is marked failed with a retry hint; press **Retry**.

### 7. Free-tier limits to expect

| Limit | What happens | Mitigation |
|---|---|---|
| Render 15-min idle spin-down | 30–60 s wake on next request | Frontend health banner retries automatically |
| Render ephemeral disk | Local SQLite/uploads lost on restart | Use Neon `DATABASE_URL` (required for real use) |
| Render 750 instance-hours/month | Services suspended until next month | One service is ~730 h; keep only the API there |
| Neon 1 GB storage / 100 CU-hours | Writes/queries blocked until next month | Fine for thousands of scripts |
| Gemini free daily quota | `429` → model enters cooldown until `Retry-After` | Fallback chain + Groq; quota resets next day |
| Gemini model stalls (no response) | After `GEMINI_REQUEST_TIMEOUT_SECONDS` (90 s) the model is skipped for 5 min | Chain continues on the next free model; no hang |
| Groq free tier | ~1K RPM / 250K TPM on `gpt-oss-120b` | Used only as last resort |
| Per-user daily limit | HTTP 429 with reset time; button disabled | `GENERATION_DAILY_LIMIT_PER_USER` (default 20) |

Qdrant Cloud free (1 GB) is optional; without it voice-profile vectors live in memory and are
lost on restart (scripts still work).

### Optional paid managed alternative — Railway
Railway is no longer free for always-on services. If you later prefer it:
- API: Dockerfile `Dockerfile.backend`, port `8000`, health `/health`.
- Frontend: `frontend/Dockerfile`, port `3000`, build arg `NEXT_PUBLIC_API_BASE_URL`.
- Add its PostgreSQL plugin and rewrite `DATABASE_URL` to `postgresql+asyncpg://…`.
- Same env vars and `ALLOWED_ORIGINS` rules as Render.

---

## Required secrets & external services (summary)

| Secret | Used for | Required? |
|---|---|---|
| `API_KEY` | API auth | **Yes** (app refuses to boot otherwise) |
| `GEMINI_API_KEY` | All LLM calls (free tier, no card) | **Yes** (or use Anthropic/Groq) |
| `QDRANT_URL` / `QDRANT_API_KEY` | Voice profiles, competitor storage | Recommended (fallback = in-memory, lost on restart) |
| `POSTGRES_PASSWORD` | Postgres | **Yes** for Docker Compose path |
| `GROQ_API_KEY` | Extra fallback provider | Optional (skipped when empty) |
| `ANTHROPIC_API_KEY` | Claude fallback | Optional |
| `ELEVENLABS_API_KEY` | TTS | Optional (else TTS returns 501 "not configured") |
| `STRIPE_API_KEY` | Billing checkout | Optional (else 501 "not configured") |
| `SENTRY_DSN` | Error tracking | Optional |

## Troubleshooting

| Symptom | Fix |
|---|---|
| First request after idle takes ~60 s (Render) | Normal free-tier cold start; the frontend banner retries. Keep a free uptime pinger if it bothers you. |
| `429 Daily generation limit reached` | Per-user guard; wait for the UTC reset shown in the message, or raise `GENERATION_DAILY_LIMIT_PER_USER` (0 = unlimited). |
| `429` from Gemini with a multi-hour Retry-After | Daily model quota exhausted; that model is put in cooldown and skipped. Add `GROQ_API_KEY` for another free provider. |
| `503 Unavailable` / `429` on generation | Gemini free tier saturated — fallback chain handles it; check `GET /health`, `GEMINI_MODEL_FALLBACKS`, or add Groq |
| `501 TTS/Billing not configured` | Set `ELEVENLABS_API_KEY` / `STRIPE_API_KEY` or use `TTS_PROVIDER=edge` |
| `401` on every call | Frontend `NEXT_PUBLIC_API_BASE_URL` wrong or API key mismatch — check browser DevTools → Network → headers |
| `/health/vector` says `provider: memory` | `QDRANT_URL`/`QDRANT_API_KEY` missing or wrong |
| Postgres won't start | Check `docker compose logs db`; verify `POSTGRES_PASSWORD` contains only URL-safe characters (or a-zA-Z0-9_-) |
| Alembic fails at boot | Check `DATABASE_URL` dialect is `postgresql+asyncpg://` not `postgres://` |
| Blank frontend | Check browser console; confirm frontend build used correct `NEXT_PUBLIC_API_BASE_URL` |
| CORS errors | Set `ALLOWED_ORIGINS` to exactly the frontend origin (with `https://`), no trailing slash |

## Cost estimate

| Setup | Components | Monthly |
|---|---|---|
| **Zero cost** | Render free + Neon free + Vercel Hobby + Qdrant free + Gemini/Groq free | **$0** (cold starts, free quotas) |
| **Always-on VPS** | Hetzner CX22 + domain + Caddy + Postgres in Docker + free LLM | **~$5–6** |
| **Paid managed** | Railway/Render paid + managed Postgres + paid LLM | $15–30+ |

If you outgrow free Gemini quota: add Groq first (still free), then consider paid Gemini
(~$10–30/mo) or Anthropic Claude (pay-per-token). The app works unchanged.
