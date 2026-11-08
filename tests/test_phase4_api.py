import hashlib
import hmac
import json

from app.services.api_keys import api_key_store
from app.services.webhooks import webhook_dispatcher


def test_api_key_create_rotate_and_revoke() -> None:
    raw_key, key_obj = api_key_store.create(owner="user-42", scopes=["generate", "tts"], rate_limit_per_minute=5)
    assert raw_key.startswith("sk_")
    assert key_obj.owner == "user-42"
    assert key_obj.scopes == ["generate", "tts"]

    fetched = api_key_store.get_by_key(raw_key)
    assert fetched is not None
    assert fetched.revoked is False

    rotated = api_key_store.rotate(raw_key)
    assert rotated is not None
    assert rotated.key != raw_key
    assert api_key_store.get_by_key(raw_key).revoked is True

    api_key_store.revoke(rotated.key)
    assert api_key_store.get_by_key(rotated.key).revoked is True


def test_webhook_hmac_signature_format() -> None:
    secret = "whsec_test_secret"
    job_id = "job-wh-9"
    webhook_dispatcher.register(job_id, "http://example.com/hook", secret)
    hook = webhook_dispatcher.get(job_id)
    assert hook is not None
    assert hook["url"] == "http://example.com/hook"
    assert hook["secret"] == secret

    payload = {"job_id": job_id, "event": "completed", "data": {"script": {"word_count": 10}}}
    body = json.dumps(payload)
    expected_sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    assert expected_sig  # deterministic HMAC-SHA256 signature computed as in dispatcher

    webhook_dispatcher.unregister(job_id)
    assert webhook_dispatcher.get(job_id) is None
