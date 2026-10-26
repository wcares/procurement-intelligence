"""Webhooks for sources in push mode (procintel.pipeline.webhook). Open to the network on purpose: the caller is a
source system, not a signed-in user, so every request is checked by its signature instead."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from procintel.pipeline import webhook

router = APIRouter()
MAX_BYTES = 5 * 1024 * 1024


@router.post("/connectors/{name}/webhook")
async def post_webhook(name: str, request: Request) -> dict:
    if int(request.headers.get("content-length") or 0) > MAX_BYTES:
        return JSONResponse({"error": f"body over {MAX_BYTES // 2**20} MB"}, status_code=413)
    body = await request.body()
    if len(body) > MAX_BYTES:
        return JSONResponse({"error": f"body over {MAX_BYTES // 2**20} MB"}, status_code=413)
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        return JSONResponse({"error": "body is not JSON"}, status_code=400)
    try:
        return webhook.receive(name, body, request.headers.get("x-signature"), payload if isinstance(payload, dict) else {})
    except webhook.Refused as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
