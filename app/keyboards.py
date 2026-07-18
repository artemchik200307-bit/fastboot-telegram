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
