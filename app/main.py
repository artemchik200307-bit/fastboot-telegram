from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from app.admin_bot import process_text as process_admin_text
from app.config import settings
from app.telegram_api import TelegramAPI
from app.user_bot import (
    process_callback as process_user_callback,
    process_text as process_user_text,
)
from app.worker import notification_worker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

user_api = TelegramAPI(settings.telegram_user_bot_token)
admin_api = TelegramAPI(settings.telegram_admin_bot_token)
worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global worker_task

    base = settings.webhook_base_url.rstrip("/")

    await user_api.set_webhook(
        f"{base}/telegram/user/{settings.user_webhook_secret}"
    )
    await admin_api.set_webhook(
        f"{base}/telegram/admin/{settings.admin_webhook_secret}"
    )

    worker_task = asyncio.create_task(
        notification_worker(user_api, admin_api)
    )

    await admin_api.send_message(
        settings.telegram_admin_group_id,
        "🟢 <b>FASTBOOT Telegram service запущен</b>",
        message_thread_id=settings.topic_system,
    )

    yield

    if worker_task:
        worker_task.cancel()

    await user_api.close()
    await admin_api.close()


app = FastAPI(
    title="FASTBOOT Telegram",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/user/{secret}")
async def user_webhook(
    secret: str,
    request: Request,
) -> dict[str, bool]:
    if secret != settings.user_webhook_secret:
        raise HTTPException(status_code=404)

    update: dict[str, Any] = await request.json()

    if update.get("message"):
        await process_user_text(user_api, update["message"])
    elif update.get("callback_query"):
        await process_user_callback(user_api, update["callback_query"])

    return {"ok": True}


@app.post("/telegram/admin/{secret}")
async def admin_webhook(
    secret: str,
    request: Request,
) -> dict[str, bool]:
    if secret != settings.admin_webhook_secret:
        raise HTTPException(status_code=404)

    update: dict[str, Any] = await request.json()

    if update.get("message"):
        await process_admin_text(admin_api, update["message"])

    return {"ok": True}
