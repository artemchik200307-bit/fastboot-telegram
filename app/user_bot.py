from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from app import db
from app.config import settings
from app.keyboards import cancel_keyboard, notification_settings_keyboard, user_menu
from app.telegram_api import TelegramAPI


def money(value: Any) -> str:
    return f"{float(value or 0):,.2f}".replace(",", " ")


MENU_TEXTS = {
    "💰 Баланс",
    "🤖 AI-бот",
    "📈 История сделок",
    "💳 Пополнить",
    "💸 Вывести",
    "👥 Рефералы",
    "⚙️ Настройки",
}

MENU_COMMANDS = {
    "/menu", "/balance", "/ai", "/trades", "/deposit",
    "/withdraw", "/referrals", "/settings", "/unlink",
}

CANCEL_TEXTS = {"❌ Отмена", "/cancel"}


def date_only(value: Any) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime(
            "%d.%m.%Y"
        )
    except ValueError:
        return str(value)[:10]



def safe_get_linked_account(telegram_user_id: int) -> dict[str, Any] | None:
    try:
        result = db.get_linked_account(telegram_user_id)
        return result if isinstance(result, dict) else None
    except Exception as error:
        print(f"get_linked_account error: {error}")
        return None


def safe_get_session(
    telegram_user_id: int,
    bot_kind: str,
) -> dict[str, Any] | None:
    try:
        result = db.get_session(telegram_user_id, bot_kind)
        return result if isinstance(result, dict) else None
    except Exception as error:
        print(f"get_session error: {error}")
        return None


def safe_set_session(
    telegram_user_id: int,
    bot_kind: str,
    state: str,
    data: dict[str, Any] | None = None,
) -> bool:
    try:
        db.set_session(
            telegram_user_id,
            bot_kind,
            state,
            data or {},
        )
        return True
    except Exception as error:
        print(f"set_session error: {error}")
        return False


def safe_clear_session(
    telegram_user_id: int,
    bot_kind: str,
) -> None:
    try:
        db.clear_session(telegram_user_id, bot_kind)
    except Exception as error:
        print(f"clear_session error: {error}")


async def show_start(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    linked = safe_get_linked_account(telegram_user_id)

    if linked:
        await api.send_message(
            chat_id,
            "<b>FASTBOOT</b>\n\nАккаунт подключён. Выберите нужный раздел.",
            reply_markup=user_menu(),
        )
        return

    safe_set_session(telegram_user_id, "user", "awaiting_fastboot_id")

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



async def show_notification_settings(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    data = db.rpc(
        "telegram_get_notification_settings",
        {"p_telegram_user_id": telegram_user_id},
    ) or {}

    text = (
        "<b>⚙️ Настройки уведомлений</b>\n\n"
        "Выберите категории сообщений, которые хотите получать.\n"
        "Изменения применяются сразу."
    )

    await api.send_message(
        chat_id,
        text,
        reply_markup=notification_settings_keyboard(data),
    )


async def show_home(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    data = db.rpc(
        "telegram_get_dashboard",
        {"p_telegram_user_id": telegram_user_id},
    ) or {}

    text = (
        "<b>FASTBOOT</b>\n\n"
        f"Основной счёт: <b>{money(data.get('spot_balance'))} USDT</b>\n"
        f"AI Bot: <b>{money(data.get('bot_balance'))} USDT</b>\n"
        f"Терминал: <b>{money(data.get('trading_balance'))} USDT</b>\n"
        f"Доступно к выводу: <b>{money(data.get('withdraw_available'))} USDT</b>\n\n"
        "Выберите нужный раздел."
    )

    await api.send_message(
        chat_id,
        text,
        reply_markup=user_menu(),
    )


async def unlink_telegram_account(
    api: TelegramAPI,
    chat_id: int,
    telegram_user_id: int,
) -> None:
    result = db.rpc(
        "telegram_unlink_account",
        {"p_telegram_user_id": telegram_user_id},
    ) or {}

    safe_clear_session(telegram_user_id, "user")

    await api.send_message(
        chat_id,
        html.escape(str(result.get("message") or "Telegram отключён.")),
        reply_markup={"remove_keyboard": True},
    )


async def process_text(
    api: TelegramAPI,
    message: dict[str, Any],
) -> None:
    chat_id = int(message["chat"]["id"])
    user = message.get("from") or {}
    telegram_user_id = int(user["id"])
    text = str(message.get("text") or "").strip()

    if text in {"/start", "start"}:
        safe_clear_session(telegram_user_id, "user")
        await show_start(api, chat_id, telegram_user_id)
        return

    if text in CANCEL_TEXTS:
        safe_clear_session(telegram_user_id, "user")
        await api.send_message(
            chat_id,
            "Действие отменено.",
            reply_markup=user_menu(),
        )
        return

    # Главное меню всегда важнее текущего шага диалога.
    if text in MENU_TEXTS or text in MENU_COMMANDS:
        safe_clear_session(telegram_user_id, "user")
        linked = safe_get_linked_account(telegram_user_id)

        if not linked:
            await show_start(api, chat_id, telegram_user_id)
            return

        if text in {"💰 Баланс", "/balance"}:
            await show_balance(api, chat_id, telegram_user_id)
            return
        if text in {"🤖 AI-бот", "/ai"}:
            await show_ai(api, chat_id, telegram_user_id)
            return
        if text in {"📈 История сделок", "/trades"}:
            await show_trades(api, chat_id, telegram_user_id)
            return
        if text in {"💳 Пополнить", "/deposit"}:
            await show_deposit(api, chat_id)
            return
        if text in {"💸 Вывести", "/withdraw"}:
            await show_withdraw(api, chat_id, telegram_user_id)
            return
        if text in {"👥 Рефералы", "/referrals"}:
            await show_referrals(api, chat_id, telegram_user_id)
            return
        if text in {"⚙️ Настройки", "/settings"}:
            await show_notification_settings(api, chat_id, telegram_user_id)
            return
        if text == "/menu":
            await show_home(api, chat_id, telegram_user_id)
            return
        if text == "/unlink":
            await unlink_telegram_account(api, chat_id, telegram_user_id)
            return

    session = safe_get_session(telegram_user_id, "user")

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

            safe_set_session(
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

            safe_clear_session(telegram_user_id, "user")

            await api.send_message(
                chat_id,
                (
                    "<b>Аккаунт успешно привязан</b>\n\n"
                    f"FASTBOOT ID: <code>{html.escape(str(result.get('fastboot_id')))}</code>"
                ),
                reply_markup=user_menu(),
            )

            await show_home(
                api,
                chat_id,
                telegram_user_id,
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

            safe_set_session(
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
            safe_clear_session(telegram_user_id, "user")
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

            safe_set_session(
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
                safe_clear_session(telegram_user_id, "user")
                error_text = str(error)

                if "Некорректный TRC20 адрес" in error_text:
                    message_text = (
                        "Некорректный адрес USDT TRC20.\n\n"
                        "Нажмите «Вывести» и создайте заявку заново."
                    )
                elif "Следующий вывод доступен" in error_text:
                    match = re.search(
                        r"Следующий вывод доступен\s+\d{2}\.\d{2}\.\d{4}",
                        error_text,
                    )
                    message_text = match.group(0) if match else "Следующий вывод пока недоступен."
                elif "Недостаточно средств" in error_text:
                    message_text = "Недостаточно средств на основном счёте."
                elif "активная заявка" in error_text.lower():
                    message_text = "У вас уже есть активная заявка на вывод."
                else:
                    message_text = "Не удалось создать заявку на вывод."

                await api.send_message(
                    chat_id,
                    message_text,
                    reply_markup=user_menu(),
                )
                return

            safe_clear_session(telegram_user_id, "user")
            await api.send_message(
                chat_id,
                (
                    "<b>Заявка на вывод создана</b>\n"
                    f"Номер: <code>{html.escape(str(result))}</code>"
                ),
                reply_markup=user_menu(),
            )
            return

    linked = safe_get_linked_account(telegram_user_id)

    if not linked:
        await show_start(api, chat_id, telegram_user_id)
        return

    handlers = {
        "💰 Баланс": show_balance,
        "/balance": show_balance,
        "🤖 AI-бот": show_ai,
        "/ai": show_ai,
        "📈 История сделок": show_trades,
        "/trades": show_trades,
        "💸 Вывести": show_withdraw,
        "/withdraw": show_withdraw,
        "👥 Рефералы": show_referrals,
        "/referrals": show_referrals,
    }

    if text in {"💳 Пополнить", "/deposit"}:
        await show_deposit(api, chat_id)
        return

    if text in {"⚙️ Настройки", "/settings"}:
        await show_notification_settings(
            api,
            chat_id,
            telegram_user_id,
        )
        return

    if text == "/menu":
        await show_home(api, chat_id, telegram_user_id)
        return

    if text == "/unlink":
        await unlink_telegram_account(
            api,
            chat_id,
            telegram_user_id,
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
        safe_set_session(telegram_user_id, "user", "deposit_amount")
        await api.send_message(
            chat_id,
            f"Введите сумму пополнения от {settings.min_deposit:g} USDT.",
            reply_markup=cancel_keyboard(),
        )
        return

    if data == "withdraw:create":
        safe_set_session(telegram_user_id, "user", "withdraw_amount")
        await api.send_message(
            chat_id,
            f"Введите сумму вывода от {settings.min_withdrawal:g} USDT.",
            reply_markup=cancel_keyboard(),
        )

        return

    if data.startswith("settings:"):
        action = data.split(":", 1)[1]

        if action == "refresh":
            await show_notification_settings(
                api,
                chat_id,
                telegram_user_id,
            )
            return

        field_map = {
            "trade": "trade_notifications",
            "funding": "funding_notifications",
            "referral": "referral_notifications",
            "daily": "daily_report",
        }

        field = field_map.get(action)
        if not field:
            return

        current = db.rpc(
            "telegram_get_notification_settings",
            {"p_telegram_user_id": telegram_user_id},
        ) or {}

        db.rpc(
            "telegram_update_notification_setting",
            {
                "p_telegram_user_id": telegram_user_id,
                "p_setting": field,
                "p_enabled": not bool(current.get(field, True)),
            },
        )

        await show_notification_settings(
            api,
            chat_id,
            telegram_user_id,
        )
