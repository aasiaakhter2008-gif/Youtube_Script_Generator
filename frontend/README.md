# YouTube Script Generator — Frontend (Next.js)

React-based dashboard for the FastAPI YouTube Script Generator backend.

## Stack
- Next.js 15 (App Router) + TypeScript + Tailwind CSS
- No heavy UI libraries; simple clean components, dark/light mode, responsive layout

## Run

```bash
cd frontend
npm install
cp .env.local.example .env.local
# set NEXT_PUBLIC_API_BASE_URL if your backend is not on http://127.0.0.1:8000

npm run dev
```

The dev server opens at **http://localhost:3000**.

Backend must be running (default): `uvicorn app.main:app --port 8000` at **http://127.0.0.1:8000**.

## Features
- API key settings stored in localStorage (`ytg_api_key`), sent as `X-API-Key` header.
- New Script: generate via `POST /v1/scripts/generate`, live progress via SSE (`GET /v1/scripts/{job_id}/stream`), final script display.
- Script Editor: outline, sections with `[B-roll]` / `[On-screen text]` cues, critic feedback, per-section regenerate, copy, export (txt/md/docx/pdf).
- History: list scripts, search by topic.
- Extras: Trends, Plans, Billing, Storyboard, Hook Tests, Dub, TTS.

## Build

```bash
npm run build
```
