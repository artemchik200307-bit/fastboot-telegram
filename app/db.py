from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from app.config import settings


supabase: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key,
)


def rpc(name: str, params: dict[str, Any] | None = None) -> Any:
    result = supabase.rpc(name, params or {}).execute()
    return result.data


def get_session(telegram_user_id: int, bot_kind: str) -> dict[str, Any] | None:
    result = (
        supabase.table("telegram_sessions")
        .select("state,data")
        .eq("telegram_user_id", telegram_user_id)
        .eq("bot_kind", bot_kind)
        .maybe_single()
        .execute()
    )
    return result.data


def set_session(
    telegram_user_id: int,
    bot_kind: str,
    state: str,
    data: dict[str, Any] | None = None,
) -> None:
    supabase.table("telegram_sessions").upsert(
        {
            "telegram_user_id": telegram_user_id,
            "bot_kind": bot_kind,
            "state": state,
            "data": data or {},
        },
        on_conflict="telegram_user_id,bot_kind",
    ).execute()


def clear_session(telegram_user_id: int, bot_kind: str) -> None:
    (
        supabase.table("telegram_sessions")
        .delete()
        .eq("telegram_user_id", telegram_user_id)
        .eq("bot_kind", bot_kind)
        .execute()
    )


def get_linked_account(
    telegram_user_id: int,
) -> dict[str, Any] | None:
    result = (
        supabase.table("telegram_accounts")
        .select(
            "user_id,"
            "telegram_user_id,"
            "telegram_chat_id,"
            "is_active"
        )
        .eq("telegram_user_id", telegram_user_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    rows = result.data or []

    return rows[0] if rows else None


def queue_rows(limit: int = 30) -> list[dict[str, Any]]:
    result = rpc("telegram_claim_notifications", {"p_limit": limit})
    return result or []


def mark_notification(
    notification_id: str,
    *,
    status: str,
    error_message: str | None = None,
) -> None:
    rpc(
        "telegram_finish_notification",
        {
            "p_notification_id": notification_id,
            "p_status": status,
            "p_error_message": error_message,
        },
    )
