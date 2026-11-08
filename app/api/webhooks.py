
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.services.webhooks import webhook_dispatcher

router = APIRouter(prefix="/webhooks", tags=["webhooks"], dependencies=[Depends(verify_api_key)])


class WebhookRegister(BaseModel):
    job_id: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=10, max_length=2000)
    secret: str = Field(min_length=16, max_length=500)


@router.post("", status_code=201)
async def register_webhook(body: WebhookRegister) -> dict:
    webhook_dispatcher.register(body.job_id, body.url, body.secret)
    return {"job_id": body.job_id, "registered": True}


@router.get("/{job_id}")
async def get_webhook(job_id: str) -> dict:
    hook = webhook_dispatcher.get(job_id)
    if hook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"job_id": job_id, "registered": True, "url": hook["url"]}


@router.delete("/{job_id}", status_code=204)
async def unregister_webhook(job_id: str):
    webhook_dispatcher.unregister(job_id)
