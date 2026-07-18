from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from app import db
from app.config import settings
from app.keyboards import cancel_keyboard, user_menu
from app.telegram_api import TelegramAPI


def money(value: Any) -> str:
    return f"{float(value or 0):,.2f}".replace(",", " ")


def date_only(value: Any) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime(
            "%d.%m.%Y"
        )
    except ValueError:
        return str(value)[:10]


async def show_start(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    linked = db.get_linked_account(telegram_user_id)

    if linked:
        await api.send_message(
            chat_id,
            "<b>FASTBOOT</b>\n\nАккаунт подключён. Выберите нужный раздел.",
            reply_markup=user_menu(),
        )
        return

    db.set_session(telegram_user_id, "user", "awaiting_fastboot_id")

    await api.send_message(
        chat_id,
        (
            "<b>Добро пожаловать в FASTBOOT</b>\n\n"
            "Введите ваш FASTBOOT ID с сайта.\n"
            "Пример: <code>FB-A1B2C3D4</code>"
        ),
        reply_markup=cancel_keyboard(),
    )


async def show_balance(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    data = db.rpc(
        "telegram_get_dashboard",
        {"p_telegram_user_id": telegram_user_id},
    )

    if not data:
        await api.send_message(chat_id, "Аккаунт не привязан.")
        return

    text = (
        "<b>💰 Балансы FASTBOOT</b>\n\n"
        f"Основной счёт: <b>{money(data.get('spot_balance'))} USDT</b>\n"
        f"AI Bot: <b>{money(data.get('bot_balance'))} USDT</b>\n"
        f"Терминал: <b>{money(data.get('trading_balance'))} USDT</b>\n"
        f"Общий баланс: <b>{money(data.get('total_balance'))} USDT</b>\n\n"
        f"Доступно к выводу: <b>{money(data.get('withdraw_available'))} USDT</b>\n"
        f"Доход AI: <b>{money(data.get('ai_net_profit'))} USDT</b>\n"
        f"Комиссия: <b>{money(data.get('ai_fees'))} USDT</b>"
    )

    await api.send_message(chat_id, text, reply_markup=user_menu())


async def show_ai(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    data = db.rpc(
        "telegram_get_dashboard",
        {"p_telegram_user_id": telegram_user_id},
    )

    status = "🟢 Включён" if data and data.get("ai_active") else "⚪ Выключен"

    text = (
        "<b>🤖 AI-бот</b>\n\n"
        f"Статус: <b>{status}</b>\n"
        f"Баланс: <b>{money((data or {}).get('bot_balance'))} USDT</b>\n"
        f"Сделок: <b>{int((data or {}).get('ai_trades_count') or 0)}</b>\n"
        f"Чистый доход: <b>{money((data or {}).get('ai_net_profit'))} USDT</b>"
    )

    await api.send_message(chat_id, text, reply_markup=user_menu())


async def show_trades(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    rows = db.rpc(
        "telegram_get_ai_history",
        {
            "p_telegram_user_id": telegram_user_id,
            "p_limit": 10,
        },
    ) or []

    if not rows:
        await api.send_message(
            chat_id,
            "📈 История AI-сделок пока пустая.",
            reply_markup=user_menu(),
        )
        return

    parts = ["<b>📈 Последние AI-сделки</b>"]

    for row in rows:
        net = float(row.get("net_pnl_amount") or row.get("pnl_amount") or 0)
        sign = "+" if net > 0 else ""
        parts.append(
            "\n"
            f"<b>{html.escape(str(row.get('pair') or '—'))}</b> · "
            f"{html.escape(str(row.get('side') or '—'))}\n"
            f"Результат: <b>{sign}{money(net)} USDT</b>\n"
            f"Доходность: {float(row.get('pnl_percent') or 0):+.2f}%\n"
            f"Дата: {date_only(row.get('created_at') or row.get('closed_at'))}"
        )

    await api.send_message(
        chat_id,
        "\n".join(parts),
        reply_markup=user_menu(),
    )


async def show_deposit(api: TelegramAPI, chat_id: int) -> None:
    text = (
        "<b>💳 Пополнение FASTBOOT</b>\n\n"
        f"Монета: <b>{html.escape(settings.deposit_asset)}</b>\n"
        f"Сеть: <b>{html.escape(settings.deposit_network)}</b>\n"
        f"Минимум: <b>{settings.min_deposit:g} USDT</b>\n\n"
        "Адрес для пополнения:\n"
        f"<code>{html.escape(settings.deposit_address)}</code>\n\n"
        "После перевода нажмите «Создать заявку» и отправьте сумму и TXID."
    )

    markup = {
        "inline_keyboard": [
            [{"text": "Создать заявку", "callback_data": "deposit:create"}]
        ]
    }
    await api.send_message(chat_id, text, reply_markup=markup)


async def show_withdraw(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    data = db.rpc(
        "telegram_get_dashboard",
        {"p_telegram_user_id": telegram_user_id},
    ) or {}

    text = (
        "<b>💸 Вывод USDT</b>\n\n"
        f"Доступно: <b>{money(data.get('withdraw_available'))} USDT</b>\n"
        f"Минимум: <b>{settings.min_withdrawal:g} USDT</b>\n"
        "Новая заявка доступна один раз в 14 дней."
    )

    markup = {
        "inline_keyboard": [
            [{"text": "Создать заявку", "callback_data": "withdraw:create"}]
        ]
    }
    await api.send_message(chat_id, text, reply_markup=markup)


async def show_referrals(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    data = db.rpc(
        "telegram_get_referral_dashboard",
        {"p_telegram_user_id": telegram_user_id},
    ) or {}

    text = (
        "<b>👥 Реферальная программа</b>\n\n"
        f"Код: <code>{html.escape(str(data.get('referral_code') or '—'))}</code>\n"
        f"Уровень: <b>{html.escape(str(data.get('level_name') or 'Start'))}</b>\n"
        f"Процент: <b>{float(data.get('reward_percent') or 5):g}%</b>\n"
        f"Рефералов: <b>{int(data.get('total_referrals') or 0)}</b>\n"
        f"Доход: <b>{money(data.get('total_earned'))} USDT</b>\n"
        f"Доступно: <b>{money(data.get('available_balance'))} USDT</b>"
    )

    await api.send_message(chat_id, text, reply_markup=user_menu())


async def process_text(
    api: TelegramAPI,
    message: dict[str, Any],
) -> None:
    chat_id = int(message["chat"]["id"])
    user = message.get("from") or {}
    telegram_user_id = int(user["id"])
    text = str(message.get("text") or "").strip()

    if text in {"/start", "start"}:
        await show_start(api, chat_id, telegram_user_id)
        return

    if text == "❌ Отмена":
        db.clear_session(telegram_user_id, "user")
        await api.send_message(
            chat_id,
            "Действие отменено.",
            reply_markup=user_menu(),
        )
        return

    session = db.get_session(telegram_user_id, "user")

    if session:
        state = session.get("state")
        data = session.get("data") or {}

        if state == "awaiting_fastboot_id":
            fastboot_id = text.upper()

            check = db.rpc(
                "telegram_prepare_link",
                {
                    "p_fastboot_id": fastboot_id,
                    "p_telegram_user_id": telegram_user_id,
                },
            )

            if not check or not check.get("found"):
                await api.send_message(
                    chat_id,
                    "FASTBOOT ID не найден. Проверьте ID и попробуйте ещё раз.",
                )
                return

            db.set_session(
                telegram_user_id,
                "user",
                "awaiting_link_code",
                {"fastboot_id": fastboot_id},
            )

            await api.send_message(
                chat_id,
                (
                    "ID найден. Теперь введите шестизначный код привязки, "
                    "который создаётся в личном кабинете FASTBOOT."
                ),
            )
            return

        if state == "awaiting_link_code":
            result = db.rpc(
                "telegram_confirm_link",
                {
                    "p_fastboot_id": data.get("fastboot_id"),
                    "p_code": text,
                    "p_telegram_user_id": telegram_user_id,
                    "p_telegram_chat_id": chat_id,
                    "p_username": user.get("username"),
                    "p_first_name": user.get("first_name"),
                },
            )

            if not result or not result.get("success"):
                await api.send_message(
                    chat_id,
                    html.escape(str((result or {}).get("message") or "Код неверный.")),
                )
                return

            db.clear_session(telegram_user_id, "user")

            await api.send_message(
                chat_id,
                (
                    "<b>Аккаунт успешно привязан</b>\n\n"
                    f"FASTBOOT ID: <code>{html.escape(str(result.get('fastboot_id')))}</code>"
                ),
                reply_markup=user_menu(),
            )
            return

        if state == "deposit_amount":
            try:
                amount = float(text.replace(",", "."))
            except ValueError:
                await api.send_message(chat_id, "Введите сумму числом.")
                return

            if amount < settings.min_deposit:
                await api.send_message(
                    chat_id,
                    f"Минимальное пополнение — {settings.min_deposit:g} USDT.",
                )
                return

            db.set_session(
                telegram_user_id,
                "user",
                "deposit_txid",
                {"amount": amount},
            )
            await api.send_message(chat_id, "Отправьте TXID перевода.")
            return

        if state == "deposit_txid":
            result = db.rpc(
                "telegram_create_deposit_request",
                {
                    "p_telegram_user_id": telegram_user_id,
                    "p_amount": data.get("amount"),
                    "p_txid": text,
                },
            )
            db.clear_session(telegram_user_id, "user")
            await api.send_message(
                chat_id,
                (
                    "<b>Заявка на пополнение создана</b>\n"
                    f"Номер: <code>{html.escape(str(result))}</code>"
                ),
                reply_markup=user_menu(),
            )
            return

        if state == "withdraw_amount":
            try:
                amount = float(text.replace(",", "."))
            except ValueError:
                await api.send_message(chat_id, "Введите сумму числом.")
                return

            if amount < settings.min_withdrawal:
                await api.send_message(
                    chat_id,
                    f"Минимальный вывод — {settings.min_withdrawal:g} USDT.",
                )
                return

            db.set_session(
                telegram_user_id,
                "user",
                "withdraw_address",
                {"amount": amount},
            )
            await api.send_message(
                chat_id,
                "Отправьте адрес USDT TRC20, начинающийся с T.",
            )
            return

        if state == "withdraw_address":
            try:
                result = db.rpc(
                    "telegram_create_withdrawal_request",
                    {
                        "p_telegram_user_id": telegram_user_id,
                        "p_amount": data.get("amount"),
                        "p_wallet_address": text,
                    },
                )
            except Exception as error:
                await api.send_message(chat_id, html.escape(str(error)))
                return

            db.clear_session(telegram_user_id, "user")
            await api.send_message(
                chat_id,
                (
                    "<b>Заявка на вывод создана</b>\n"
                    f"Номер: <code>{html.escape(str(result))}</code>"
                ),
                reply_markup=user_menu(),
            )
            return

    linked = db.get_linked_account(telegram_user_id)

    if not linked:
        await show_start(api, chat_id, telegram_user_id)
        return

    handlers = {
        "💰 Баланс": show_balance,
        "🤖 AI-бот": show_ai,
        "📈 История сделок": show_trades,
        "💸 Вывести": show_withdraw,
        "👥 Рефералы": show_referrals,
    }

    if text == "💳 Пополнить":
        await show_deposit(api, chat_id)
        return

    if text == "⚙️ Настройки":
        await api.send_message(
            chat_id,
            "⚙️ Настройки уведомлений будут добавлены на следующем этапе.",
            reply_markup=user_menu(),
        )
        return

    handler = handlers.get(text)
    if handler:
        await handler(api, chat_id, telegram_user_id)
    else:
        await api.send_message(
            chat_id,
            "Выберите кнопку в меню.",
            reply_markup=user_menu(),
        )


async def process_callback(
    api: TelegramAPI,
    callback: dict[str, Any],
) -> None:
    callback_id = str(callback["id"])
    user = callback.get("from") or {}
    telegram_user_id = int(user["id"])
    message = callback.get("message") or {}
    chat_id = int(message["chat"]["id"])
    data = str(callback.get("data") or "")

    await api.answer_callback_query(callback_id)

    if data == "deposit:create":
        db.set_session(telegram_user_id, "user", "deposit_amount")
        await api.send_message(
            chat_id,
            f"Введите сумму пополнения от {settings.min_deposit:g} USDT.",
            reply_markup=cancel_keyboard(),
        )
        return

    if data == "withdraw:create":
        db.set_session(telegram_user_id, "user", "withdraw_amount")
        await api.send_message(
            chat_id,
            f"Введите сумму вывода от {settings.min_withdrawal:g} USDT.",
            reply_markup=cancel_keyboard(),
        )
