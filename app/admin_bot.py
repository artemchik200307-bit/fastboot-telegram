from __future__ import annotations

import html
from typing import Any

from app import db
from app.config import settings
from app.keyboards import admin_menu
from app.telegram_api import TelegramAPI


def money(value: Any) -> str:
    return f"{float(value or 0):,.2f}".replace(",", " ")


def is_admin(telegram_user_id: int) -> bool:
    return telegram_user_id == settings.telegram_admin_id


async def deny(api: TelegramAPI, chat_id: int) -> None:
    await api.send_message(chat_id, "Доступ запрещён.")


async def show_stats(api: TelegramAPI, chat_id: int) -> None:
    data = db.rpc("telegram_admin_platform_stats") or {}

    text = (
        "<b>📊 FASTBOOT — общая статистика</b>\n\n"
        f"Пользователей: <b>{int(data.get('users_count') or 0)}</b>\n"
        f"Активных AI-ботов: <b>{int(data.get('active_ai_count') or 0)}</b>\n\n"
        f"Основные счета: <b>{money(data.get('spot_total'))} USDT</b>\n"
        f"AI-счета: <b>{money(data.get('bot_total'))} USDT</b>\n"
        f"Терминалы: <b>{money(data.get('trading_total'))} USDT</b>\n"
        f"Общий баланс: <b>{money(data.get('all_balance'))} USDT</b>\n\n"
        f"Доход платформы: <b>{money(data.get('platform_fees'))} USDT</b>\n"
        f"Ожидает пополнений: <b>{int(data.get('pending_deposits') or 0)}</b>\n"
        f"Ожидает выводов: <b>{int(data.get('pending_withdrawals') or 0)}</b>"
    )

    await api.send_message(chat_id, text, reply_markup=admin_menu())


async def show_users(api: TelegramAPI, chat_id: int) -> None:
    rows = (
        db.supabase.table("profiles")
        .select("fastboot_id,username,email,created_at")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
        .data
        or []
    )

    parts = ["<b>👤 Последние пользователи</b>"]
    for row in rows:
        parts.append(
            "\n"
            f"<code>{html.escape(str(row.get('fastboot_id') or '—'))}</code>\n"
            f"{html.escape(str(row.get('username') or 'User'))}\n"
            f"{html.escape(str(row.get('email') or '—'))}"
        )

    await api.send_message(
        chat_id,
        "\n".join(parts),
        reply_markup=admin_menu(),
    )


async def show_requests(
    api: TelegramAPI,
    chat_id: int,
    request_type: str,
) -> None:
    rows = (
        db.supabase.table("funding_requests")
        .select("id,user_id,type,amount,status,network,created_at")
        .eq("type", request_type)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
        .data
        or []
    )

    title = "💳 Пополнения" if request_type == "deposit" else "💸 Выводы"
    parts = [f"<b>{title} — ожидают обработки</b>"]

    if not rows:
        parts.append("\nНет активных заявок.")

    for row in rows:
        parts.append(
            "\n"
            f"<code>{html.escape(str(row.get('id')))}</code>\n"
            f"Сумма: <b>{money(row.get('amount'))} USDT</b>\n"
            f"Сеть: {html.escape(str(row.get('network') or 'TRC20'))}"
        )

    await api.send_message(
        chat_id,
        "\n".join(parts),
        reply_markup=admin_menu(),
    )


async def process_text(
    api: TelegramAPI,
    message: dict[str, Any],
) -> None:
    chat_id = int(message["chat"]["id"])
    user = message.get("from") or {}
    telegram_user_id = int(user["id"])
    text = str(message.get("text") or "").strip()

    if not is_admin(telegram_user_id):
        await deny(api, chat_id)
        return

    if text in {"/start", "start"}:
        await api.send_message(
            chat_id,
            "<b>FASTBOOT Admin</b>\n\nПанель администратора активна.",
            reply_markup=admin_menu(),
        )
        return

    if text == "📊 Общая статистика" or text == "/stats":
        await show_stats(api, chat_id)
    elif text == "👤 Пользователи":
        await show_users(api, chat_id)
    elif text == "💳 Пополнения":
        await show_requests(api, chat_id, "deposit")
    elif text == "💸 Выводы":
        await show_requests(api, chat_id, "withdraw")
    elif text == "🤖 AI-боты":
        data = db.rpc("telegram_admin_platform_stats") or {}
        await api.send_message(
            chat_id,
            (
                "<b>🤖 AI-боты</b>\n\n"
                f"Активных пользователей: "
                f"<b>{int(data.get('active_ai_count') or 0)}</b>\n"
                f"Баланс под управлением: "
                f"<b>{money(data.get('bot_total'))} USDT</b>"
            ),
            reply_markup=admin_menu(),
        )
    elif text == "📈 Торговля":
        await api.send_message(
            chat_id,
            "📈 Расширенное управление торговлей будет добавлено на следующем этапе.",
            reply_markup=admin_menu(),
        )
    elif text == "💰 Финансы":
        await show_stats(api, chat_id)
    else:
        await api.send_message(
            chat_id,
            "Выберите раздел в меню.",
            reply_markup=admin_menu(),
        )
