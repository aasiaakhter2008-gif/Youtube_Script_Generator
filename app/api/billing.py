from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.core.security import verify_api_key
from app.services.billing import billing_service

router = APIRouter(prefix="/billing", tags=["billing"], dependencies=[Depends(verify_api_key)])


@router.get("/plans")
async def list_plans() -> dict:
    return {
        "plans": {
            "free": {"monthly_credits": 10, "features": ["generate", "hook_test", "dub", "tts", "storyboard"]},
            "pro": {"monthly_credits": 1000, "features": ["generate", "hook_test", "dub", "tts", "storyboard", "competitor_gap"]},
            "team": {"monthly_credits": 10000, "features": ["generate", "hook_test", "dub", "tts", "storyboard", "competitor_gap", "research"]},
        }
    }


@router.get("/usage")
async def get_usage(feature: str = "generate", user_id: str = "user-1") -> dict:
    billing_service.check_limit(feature=feature, user_id=user_id, plan="free")
    return {"feature": feature, "user_id": user_id, "used_credits": billing_service._usage.get(f"{user_id}:free", 0)}


@router.post("/subscribe")
async def subscribe(plan: str = "pro", user_id: str = "user-1") -> dict:
    if plan not in ("free", "pro", "team"):
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")
    if not settings.STRIPE_API_KEY:
        raise HTTPException(status_code=501, detail="Billing not configured: STRIPE_API_KEY is missing. Add a Stripe (or Lemon Squeezy) secret key to .env to enable checkout.")
    return {"status": "redirect", "plan": plan, "checkout_url": f"https://checkout.stripe.com/subscribe?plan={plan}&user_id={user_id}"}
