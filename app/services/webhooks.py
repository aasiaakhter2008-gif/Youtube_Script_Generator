import hashlib
import hmac
import json
from typing import Optional

import httpx


class WebhookDispatcher:
    """Phase 4: HMAC-signed job completion webhooks."""

    def __init__(self) -> None:
        self._hooks: dict[str, dict] = {}

    def register(self, job_id: str, url: str, secret: str) -> None:
        if url:
            self._hooks[job_id] = {"url": url, "secret": secret}

    def unregister(self, job_id: str) -> None:
        self._hooks.pop(job_id, None)

    def get(self, job_id: str) -> Optional[dict]:
        return self._hooks.get(job_id)

    async def dispatch(self, job_id: str, event: str, payload: dict) -> None:
        hook = self._hooks.get(job_id)
        if not hook:
            return
        body = json.dumps({"job_id": job_id, "event": event, "data": payload})
        signature = hmac.new(hook["secret"].encode(), body.encode(), hashlib.sha256).hexdigest()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(hook["url"], content=body, headers={"X-Signature": f"sha256={signature}", "Content-Type": "application/json"})
        except Exception:
            # graceful degradation: webhook delivery failures must not crash the pipeline
            pass


webhook_dispatcher = WebhookDispatcher()
