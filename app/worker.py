from __future__ import annotations

import asyncio
import html
import logging
from typing import Any

from app import db
from app.config import settings
from app.telegram_api import TelegramAPI


logger = logging.getLogger(__name__)


async def dispatch_row(
    row: dict[str, Any],
    user_api: TelegramAPI,
    admin_api: TelegramAPI,
) -> None:
    destination = row.get("destination")
    text = str(row.get("message_text") or "")
    chat_id = row.get("chat_id")
    topic_key = row.get("topic_key")

    if destination == "user":
        if not chat_id:
            raise RuntimeError("User notification has no chat_id")
        await user_api.send_message(int(chat_id), text)
        return

    if destination == "admin":
        thread_id = settings.topic_map.get(str(topic_key))
        await admin_api.send_message(
            settings.telegram_admin_group_id,
            text,
            message_thread_id=thread_id,
        )
        return

    raise RuntimeError(f"Unknown notification destination: {destination}")


async def notification_worker(
    user_api: TelegramAPI,
    admin_api: TelegramAPI,
) -> None:
    while True:
        try:
            rows = db.queue_rows(30)

            for row in rows:
                notification_id = str(row["id"])

                try:
                    await dispatch_row(row, user_api, admin_api)
                    db.mark_notification(
                        notification_id,
                        status="sent",
                    )
                except Exception as error:
                    logger.exception("Notification delivery failed")
                    db.mark_notification(
                        notification_id,
                        status="failed",
                        error_message=str(error)[:1000],
                    )

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Notification worker loop failed")

        await asyncio.sleep(5)
