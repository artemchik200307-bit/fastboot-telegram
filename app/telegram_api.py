from __future__ import annotations

from typing import Any

import httpx


class TelegramAPI:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.client = httpx.AsyncClient(timeout=25)

    async def close(self) -> None:
        await self.client.aclose()

    async def call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        response = await self.client.post(
            f"{self.base_url}/{method}",
            json=payload or {},
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(data.get("description", "Telegram API error"))

        return data.get("result")

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        message_thread_id: int | None = None,
        parse_mode: str = "HTML",
    ) -> Any:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        if message_thread_id:
            payload["message_thread_id"] = message_thread_id

        return await self.call("sendMessage", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
        }
        if text:
            payload["text"] = text

        return await self.call("answerCallbackQuery", payload)

    async def set_webhook(self, url: str) -> Any:
        return await self.call(
            "setWebhook",
            {
                "url": url,
                "allowed_updates": ["message", "callback_query"],
                "drop_pending_updates": True,
            },
        )
