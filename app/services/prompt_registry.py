from typing import Optional


class PromptRegistryService:
    """Phase 4: prompt registry with versions, rollout percentage and rollback."""

    def __init__(self) -> None:
        self._versions: dict[str, list[dict]] = {}

    def register(self, name: str, version: int, template: str, rollout_pct: int = 100) -> dict:
        entry = {"name": name, "version": version, "template": template, "rollout_pct": rollout_pct, "active": rollout_pct >= 100}
        self._versions.setdefault(name, []).append(entry)
        return entry

    def get_active(self, name: str) -> Optional[dict]:
        versions = sorted(self._versions.get(name, []), key=lambda v: v["version"], reverse=True)
        for version in versions:
            if version.get("active"):
                return version
        return versions[0] if versions else None

    def rollback(self, name: str, version: int) -> Optional[dict]:
        for existing in self._versions.get(name, []):
            if existing["version"] == version:
                existing["active"] = True
                return existing
        return None


prompt_registry = PromptRegistryService()
