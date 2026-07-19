def user_menu() -> dict:
    return {
        "keyboard": [
            [{"text": "💰 Баланс"}, {"text": "🤖 AI-бот"}],
            [{"text": "📈 История сделок"}],
            [{"text": "💳 Пополнить"}, {"text": "💸 Вывести"}],
            [{"text": "👥 Рефералы"}, {"text": "⚙️ Настройки"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def admin_menu() -> dict:
    return {
        "keyboard": [
            [{"text": "📊 Общая статистика"}],
            [{"text": "👤 Пользователи"}, {"text": "🤖 AI-боты"}],
            [{"text": "💳 Пополнения"}, {"text": "💸 Выводы"}],
            [{"text": "📈 Торговля"}, {"text": "💰 Финансы"}],
            [{"text": "⚙️ Настройки"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def cancel_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "❌ Отмена"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def notification_settings_keyboard(settings: dict) -> dict:
    def mark(enabled: bool) -> str:
        return "✅" if enabled else "❌"

    return {
        "inline_keyboard": [
            [{
                "text": f"{mark(settings.get('trade_notifications', True))} AI-сделки",
                "callback_data": "settings:trade",
            }],
            [{
                "text": f"{mark(settings.get('funding_notifications', True))} Пополнения и выводы",
                "callback_data": "settings:funding",
            }],
            [{
                "text": f"{mark(settings.get('referral_notifications', True))} Рефералы",
                "callback_data": "settings:referral",
            }],
            [{
                "text": f"{mark(settings.get('daily_report', True))} Ежедневный отчёт",
                "callback_data": "settings:daily",
            }],
            [{
                "text": "🔄 Обновить",
                "callback_data": "settings:refresh",
            }],
        ]
    }
