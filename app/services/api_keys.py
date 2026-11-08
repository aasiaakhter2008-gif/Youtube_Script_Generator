from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


class ApiKey:
    def __init__(self, key_id: str, key: str, owner: str, scopes: list, rate_limit_per_minute: int, created_at: datetime, revoked: bool = False) -> None:
        self.key_id = key_id
        self.key = key
        self.owner = owner
        self.scopes = scopes
        self.rate_limit_per_minute = rate_limit_per_minute
        self.created_at = created_at
        self.revoked = revoked


class ApiKeyStore:
    """Phase 4: API key store with scopes, rotation and per-key rate limits (in-memory MVP)."""

    def __init__(self) -> None:
        self._keys: dict[str, ApiKey] = {}

    def create(self, owner: str, scopes: list, rate_limit_per_minute: int = 10) -> tuple[str, ApiKey]:
        raw_key = f"sk_{owner[:8]}_{uuid4().hex[:12]}"
        api_key = ApiKey(key_id=uuid4().hex, key=raw_key, owner=owner, scopes=scopes, rate_limit_per_minute=rate_limit_per_minute, created_at=datetime.now(timezone.utc))
        self._keys[raw_key] = api_key
        return raw_key, api_key

    def get_by_key(self, raw_key: str) -> Optional[ApiKey]:
        return self._keys.get(raw_key)

    def revoke(self, raw_key: str) -> Optional[ApiKey]:
        api_key = self._keys.get(raw_key)
        if api_key is not None:
            api_key.revoked = True
        return api_key

    def rotate(self, raw_key: str) -> Optional[ApiKey]:
        api_key = self._keys.get(raw_key)
        if api_key is None or api_key.revoked:
            return None
        new_key, new_api_key = self.create(owner=api_key.owner, scopes=api_key.scopes, rate_limit_per_minute=api_key.rate_limit_per_minute)
        self.revoke(raw_key)
        return new_api_key


api_key_store = ApiKeyStore()
