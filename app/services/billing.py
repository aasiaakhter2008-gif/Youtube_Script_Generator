from fastapi import HTTPException

PLAN_LIMITS = {
    "free": {"monthly_credits": 10, "features": ["generate", "hook_test", "dub", "tts", "storyboard"]},
    "pro": {"monthly_credits": 1000, "features": ["generate", "hook_test", "dub", "tts", "storyboard", "competitor_gap"]},
    "team": {"monthly_credits": 10000, "features": ["generate", "hook_test", "dub", "tts", "storyboard", "competitor_gap", "research"]},
}

CREDIT_COSTS = {
    "generate": 1,
    "hook_test": 2,
    "dub": 1,
    "tts": 1,
    "storyboard": 1,
    "competitor_gap": 5,
    "research": 2,
}


class BillingService:
    """Phase 4: token/credit based usage metering and plan limit enforcement (Free / Pro / Team)."""

    def __init__(self) -> None:
        self._usage: dict[str, int] = {}

    def get_plan_limit(self, plan: str) -> dict:
        return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    def check_limit(self, feature: str, user_id: str, plan: str = "free") -> None:
        allowed_features = self.get_plan_limit(plan).get("features", [])
        if feature not in allowed_features:
            raise HTTPException(status_code=402, detail=f"Feature '{feature}' not available on plan '{plan}'")
        used = self._usage.get(f"{user_id}:{plan}", 0)
        if used + CREDIT_COSTS.get(feature, 1) > self.get_plan_limit(plan).get("monthly_credits", 0):
            raise HTTPException(status_code=429, detail=f"Monthly credit limit exceeded for plan '{plan}'")

    def consume(self, feature: str, user_id: str, plan: str = "free") -> None:
        key = f"{user_id}:{plan}"
        self._usage[key] = self._usage.get(key, 0) + CREDIT_COSTS.get(feature, 1)


billing_service = BillingService()
