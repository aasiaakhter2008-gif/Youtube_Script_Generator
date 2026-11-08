"""Smoke test for the YouTube Script Generator API.

Creates one generation job and walks every router endpoint, printing PASS/FAIL per check.
Existent 2xx and documented domain errors (401/403/404/405/409/413/415/422/429/501/503) count as PASS —
what we are verifying is that no route 500s or crashes the server.
Run: python scripts/smoke_test.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY", "").strip()

if not API_KEY:
    # fall back to .env so `python scripts/smoke_test.py` works out of the box
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", ".env"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("API_KEY="):
                    API_KEY = line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass

HEADERS = {"Content-Type": "application/json", "X-API-Key": API_KEY}
results: list[tuple[str, int, bool, str]] = []


def req(method: str, path: str, body: object | None = None, headers: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    request = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(request, timeout=300) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, (e.read() or b"").decode("utf-8", errors="replace")
    except Exception as exc:  # network/connection failure
        return 0, f"connection error: {exc}"


def check(name: str, method: str, path: str, body: object | None = None, accept: tuple[int, ...] = (200, 201, 202, 204)) -> None:
    status, text = req(method, path, body)
    ok = status in accept
    preview = (text or "")[:120].replace("\n", " ")
    results.append((name, status, ok, preview))
    print(f"{'PASS' if ok else 'FAIL':4} [{status}] {name} -> {path}")


def check_sse(name: str, path: str, accept: tuple[int, ...] = (200, 404)) -> None:
    """SSE streams: connect and read one byte-chunk only, then close."""
    request = urllib.request.Request(BASE_URL + path, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            chunk = resp.read(64)
            status = resp.status
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        chunk = (e.read() or b"")[:120]
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")
        status = e.code
    except Exception:
        status = 0
        chunk = ""
    ok = status in accept
    preview = (chunk or "")[:80].replace("\n", " ")
    results.append((name, status, ok, preview))
    print(f"{'PASS' if ok else 'FAIL':4} [{status}] {name} -> {path}")


def main() -> int:
    if not API_KEY:
        print("ERROR: API_KEY not set (export API_KEY=... or put it in .env)")
        return 2

    print(f"Smoke testing {BASE_URL}\n")

    # Public routes (no auth)
    check("root", "GET", "/", accept=(200,))
    check("health", "GET", "/health", accept=(200,))
    check("health/vector", "GET", "/health/vector", accept=(200,))
    check("models", "GET", "/v1/models", accept=(200,))

    # Scripts lifecycle
    check("scripts list", "GET", "/v1/scripts", accept=(200,))
    check("daily quota", "GET", "/v1/scripts/quota", accept=(200,))
    generate_status, generate_text = req(
        "POST",
        "/v1/scripts/generate",
        {"topic": "Why do we sleep", "audience": "general", "tone": "educational", "language": "English", "duration_minutes": 1, "format": "shorts"},
    )
    generate_ok = generate_status in (202, 429)
    results.append(("generate script (1m shorts)", generate_status, generate_ok, (generate_text or "")[:120].replace("\n", " ")))
    print(f"{'PASS' if generate_ok else 'FAIL':4} [{generate_status}] generate script (1m shorts) -> /v1/scripts/generate")
    job_id = None
    try:
        job_id = json.loads(generate_text or "{}").get("job_id")
    except Exception:
        job_id = None
    if not job_id:
        print("ERROR: could not create a generation job; skipping job-dependent checks")
        summarize()
        return 1
    print(f"   -> job_id={job_id}\n")

    check("get job", "GET", f"/v1/scripts/{job_id}", accept=(200, 404))
    check("job activity", "GET", f"/v1/scripts/{job_id}/activity", accept=(200, 404))
    check(
        "add comment",
        "POST",
        f"/v1/scripts/{job_id}/comments",
        body={"section_type": "hook", "content": "smoke test", "created_by": "smoke"},
        accept=(200, 201, 404, 422),
    )
    check("list comments", "GET", f"/v1/scripts/{job_id}/comments", accept=(200, 404))
    check(
        "regenerate section",
        "POST",
        f"/v1/scripts/{job_id}/regenerate-section",
        body={"section_type": "hook"},
        accept=(200, 202, 404, 409, 429, 503),
    )
    check("retry job", "POST", f"/v1/scripts/{job_id}/retry", accept=(200, 202, 404, 409))
    check(
        "set job status",
        "POST",
        f"/v1/scripts/{job_id}/status",
        body={"status": "draft", "actor": "smoke"},
        accept=(200, 404, 422),
    )
    check_sse("stream", f"/v1/scripts/{job_id}/stream", accept=(200, 404))
    check("export txt", "GET", f"/v1/scripts/{job_id}/export?format=txt", accept=(200, 404, 409))

    # Hooks
    check("generate hook tests", "POST", f"/v1/scripts/{job_id}/hook-tests", accept=(200, 201, 404, 429, 503))
    check(
        "log hook test result",
        "POST",
        f"/v1/scripts/{job_id}/hook-tests/results",
        body={"winner_hook": "h", "metrics": {}, "notes": "smoke"},
        accept=(200, 201, 404, 422),
    )
    check("get hook test result", "GET", f"/v1/scripts/{job_id}/hook-tests/results", accept=(200, 404))

    # Dub / TTS / Storyboard
    check(
        "dub script",
        "POST",
        f"/v1/scripts/{job_id}/dub",
        body={"language": "Urdu"},
        accept=(200, 201, 404, 409, 429, 503),
    )
    check(
        "tts (may be unconfigured -> 501/503)",
        "POST",
        f"/v1/scripts/{job_id}/tts",
        body={"voice": "en-US-AriaNeural"},
        accept=(200, 201, 404, 409, 501, 503),
    )
    check(
        "generate storyboard",
        "POST",
        f"/v1/scripts/{job_id}/storyboard",
        accept=(200, 201, 404, 409, 429, 503),
    )
    check("get storyboard", "GET", f"/v1/scripts/{job_id}/storyboard", accept=(200, 404))
    check("export storyboard json", "GET", f"/v1/scripts/{job_id}/storyboard/export?format=json", accept=(200, 404))

    # Trends / Plans / Competitors
    check("trends", "GET", "/v1/trends?niche=technology", accept=(200,))
    check("refresh trends", "POST", "/v1/trends/refresh?niche=technology", accept=(200, 429, 503))
    check("create plan", "POST", "/v1/plans", body={"niche": "technology", "goal": "growth", "episodes": 2}, accept=(200, 201, 429, 503))
    check(
        "competitor gap",
        "POST",
        "/v1/competitors/gap",
        body={"urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]},
        accept=(200, 429, 503),
    )

    # Billing / Feedback / Webhooks / Jobs / Prompt registry
    check("billing plans", "GET", "/v1/billing/plans", accept=(200,))
    check("billing usage", "GET", "/v1/billing/usage?feature=generate&user_id=smoke", accept=(200,))
    check(
        "billing subscribe (needs Stripe key -> 501)",
        "POST",
        "/v1/billing/subscribe",
        body={"plan": "pro", "user_id": "smoke"},
        accept=(200, 402, 501),
    )
    check(
        "add feedback",
        "POST",
        "/v1/feedback",
        body={"script_job_id": job_id, "section_type": "hook", "rating": "up", "edited_content": None},
        accept=(200, 201, 422),
    )
    check("list feedback", "GET", f"/v1/feedback/{job_id}", accept=(200,))
    check(
        "register webhook",
        "POST",
        "/v1/webhooks",
        body={"job_id": job_id, "url": "https://example.com/hook", "secret": "a-very-long-webhook-secret-1234"},
        accept=(200, 201),
    )
    check("get webhook", "GET", f"/v1/webhooks/{job_id}", accept=(200,))
    check("delete webhook", "DELETE", f"/v1/webhooks/{job_id}", accept=(204,))
    check("jobs list", "GET", "/v1/jobs", accept=(200,))
    check(
        "register prompt",
        "POST",
        "/v1/prompts",
        body={"name": "smoke-prompt", "version": 1, "template": "You are a helpful assistant that answers in {language}.", "rollout_pct": 100},
        accept=(200, 201),
    )
    check("get active prompt", "GET", "/v1/prompts/smoke-prompt", accept=(200, 404))
    check("rollback prompt", "POST", "/v1/prompts/smoke-prompt/rollback?version=1", accept=(200, 404, 422))

    # Voice profiles
    check(
        "create voice profile",
        "POST",
        "/v1/voice-profiles",
        body={"name": "smoke-voice", "texts": ["Short sentences. No fluff. Clear call to action.", "End with one ask."]},
        accept=(200, 201, 503),
    )
    check(
        "search voice profiles",
        "POST",
        "/v1/voice-profiles/search",
        body={"query": "opening hook style", "top_k": 3},
        accept=(200, 404, 503),
    )

    # YouTube channels (in-memory stub)
    check(
        "connect youtube channel",
        "POST",
        "/v1/youtube/channels",
        body={"owner_user_id": "smoke", "youtube_channel_id": "UCsmoke", "handle": "@smoke"},
        accept=(200, 201),
    )

    summarize()
    ok = all(ok for (_, _, ok, _) in results)
    return 0 if ok else 1


def summarize() -> None:
    passed = sum(1 for (_, _, ok, _) in results if ok)
    failed = len(results) - passed
    print("\n" + "=" * 60)
    print(f"SMOKE TEST SUMMARY: {passed} passed, {failed} failed, {len(results)} checks")
    if failed:
        print("FAILED CHECKS:")
        for name, status, ok, preview in results:
            if not ok:
                print(f"  [{status}] {name}: {preview}")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
