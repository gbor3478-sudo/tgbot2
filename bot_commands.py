"""Обработка входящих сообщений и нажатий на кнопки от пользователя.

Команды:
  /start, /help          — подсказка
  /addquery <текст>      — добавить запрос в постоянный список
  /removequery <номер>   — убрать запрос по номеру из /queries
  /queries               — показать текущий список запросов и бренд
  /addbrand <текст>      — добавить свой бренд в список для кнопок /brand
  /removebrand <номер>   — убрать бренд по номеру из /brands
  /brands                — показать сохранённые бренды
  /brand                 — показать кнопки с брендами (свои + из BRANDS_LIST) для выбора
  /setbrand <текст>      — задать бренд вручную, не добавляя его в сохранённые
  /clearbrand            — сбросить бренд (искать без привязки к бренду)
  /search <текст>        — разовый поиск прямо сейчас, без сохранения в список

Бренд, если задан, подставляется в начало каждого запроса при поиске
(например бренд "Nike" + запрос "кроссовки" → ищем "Nike кроссовки").
"""

import logging

log = logging.getLogger("1688-bot.commands")

BRAND_ICONS = ["🏷️", "⭐", "💎", "🔥", "✨", "🎯", "🚀", "🛍️", "👑", "💠"]

HELP_TEXT = (
    "Я ищу товары на 1688.com по вашим запросам.\n\n"
    "<b>Команды:</b>\n"
    "/addquery &lt;текст&gt; — добавить запрос в постоянный поиск\n"
    "/removequery &lt;номер&gt; — убрать запрос (номер из /queries)\n"
    "/queries — показать список запросов и текущий бренд\n"
    "/addbrand &lt;текст&gt; — добавить свой бренд (появится кнопкой в /brand)\n"
    "/removebrand &lt;номер&gt; — убрать бренд (номер из /brands)\n"
    "/brands — показать сохранённые бренды\n"
    "/brand — выбрать бренд кнопками с иконками\n"
    "/setbrand &lt;текст&gt; — разовый бренд текстом, не сохраняя в список\n"
    "/clearbrand — искать без привязки к бренду\n"
    "/search &lt;текст&gt; — разовый поиск прямо сейчас"
)


def effective_queries(state: dict) -> list:
    """Список запросов с учётом текущего бренда."""
    brand = state.get("brand")
    queries = state.get("queries", [])
    if not brand:
        return list(queries)
    return [f"{brand} {q}" for q in queries]


def combined_brands(state: dict, brands_list: list) -> list:
    """Свои сохранённые бренды (/addbrand) + бренды из secret BRANDS_LIST, без дублей."""
    own = state.get("brands", [])
    seen = set()
    result = []
    for b in list(own) + list(brands_list):
        if b not in seen:
            seen.add(b)
            result.append(b)
    return result


def handle_updates(state: dict, client, brands_list: list, run_search_fn, poll_timeout: int = 0):
    """
    Забирает новые апдейты из Telegram, обрабатывает команды, обновляет state.
    run_search_fn(query: str) -> list[dict]  — функция мгновенного поиска для /search.
    poll_timeout — сколько секунд ждать новых сообщений (long polling Telegram).
    0 — вернуться сразу, если сообщений нет (для разового запуска).
    Возвращает обновлённый state.
    """
    updates = client.get_updates(offset=state.get("update_offset", 0) + 1, timeout=poll_timeout)

    for update in updates:
        state["update_offset"] = max(state.get("update_offset", 0), update["update_id"])

        try:
            if "callback_query" in update:
                _handle_callback(update["callback_query"], state, client)
                continue

            message = update.get("message") or update.get("edited_message")
            if not message:
                continue
            text = (message.get("text") or "").strip()
            if not text:
                client.send_message(
                    "Я понимаю только текстовые команды. Наберите /help, чтобы увидеть список."
                )
                continue

            _handle_text_command(text, state, client, brands_list, run_search_fn)

        except Exception as e:
            log.exception("Ошибка при обработке апдейта %s: %s", update.get("update_id"), e)
            try:
                client.send_message(
                    f"⚠️ Произошла ошибка при обработке вашего сообщения: {e}\n"
                    "Попробуйте ещё раз или наберите /help."
                )
            except Exception:
                pass

    return state


def _handle_callback(callback, state: dict, client):
    data = callback.get("data", "")
    cq_id = callback["id"]

    if data.startswith("brand:"):
        chosen = data[len("brand:"):]
        if chosen == "__none__":
            state["brand"] = None
            client.answer_callback_query(cq_id, "Бренд сброшен")
            client.send_message("Бренд сброшен — ищу без привязки к бренду.")
        else:
            state["brand"] = chosen
            client.answer_callback_query(cq_id, f"Бренд: {chosen}")
            client.send_message(f"Бренд установлен: <b>{chosen}</b>")
    else:
        client.answer_callback_query(cq_id)


KNOWN_COMMANDS = (
    "/start", "/help", "/addquery", "/removequery", "/queries",
    "/addbrand", "/removebrand", "/brands",
    "/brand", "/setbrand", "/clearbrand", "/search",
)


def _handle_text_command(text: str, state: dict, client, brands_list: list, run_search_fn):
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        client.send_message(HELP_TEXT)

    elif cmd == "/addquery":
        if not arg:
            client.send_message(
                "❗️ Не хватает текста запроса.\n"
                "Формат: /addquery &lt;что искать&gt;\n"
                "Пример: /addquery термос"
            )
            return
        state.setdefault("queries", [])
        if arg in state["queries"]:
            client.send_message(f"⚠️ Запрос «{arg}» уже есть в списке (см. /queries).")
        else:
            state["queries"].append(arg)
            client.send_message(f"✅ Добавлено: <b>{arg}</b>")

    elif cmd == "/removequery":
        queries = state.get("queries", [])
        if not queries:
            client.send_message("⚠️ Список запросов пуст — удалять нечего. Добавьте: /addquery термос")
            return
        if not arg:
            client.send_message(
                "❗️ Не хватает номера.\n"
                "Формат: /removequery &lt;номер&gt;\n"
                f"Посмотреть номера: /queries (сейчас их {len(queries)})"
            )
            return
        if not arg.isdigit():
            client.send_message(f"❗️ «{arg}» — это не число. Нужен номер из списка /queries, например: /removequery 2")
            return
        n = int(arg)
        if not (1 <= n <= len(queries)):
            client.send_message(f"❗️ Номера {n} нет в списке — доступны от 1 до {len(queries)} (см. /queries).")
            return
        removed = queries.pop(n - 1)
        client.send_message(f"✅ Убрано: <b>{removed}</b>")

    elif cmd == "/queries":
        queries = state.get("queries", [])
        brand = state.get("brand")
        lines = [f"Бренд: <b>{brand or '— не задан —'}</b>", ""]
        if queries:
            lines.append("Запросы:")
            lines += [f"{i+1}. {q}" for i, q in enumerate(queries)]
        else:
            lines.append("Список запросов пуст. Добавьте: /addquery термос")
        client.send_message("\n".join(lines))

    elif cmd == "/addbrand":
        if not arg:
            client.send_message(
                "❗️ Не хватает названия бренда.\n"
                "Формат: /addbrand &lt;бренд&gt;\n"
                "Пример: /addbrand Nike"
            )
            return
        state.setdefault("brands", [])
        if arg in state["brands"]:
            client.send_message(f"⚠️ Бренд «{arg}» уже сохранён (см. /brands).")
        else:
            state["brands"].append(arg)
            client.send_message(f"✅ Бренд добавлен: <b>{arg}</b> — теперь он есть в /brand")

    elif cmd == "/removebrand":
        brands = state.get("brands", [])
        if not brands:
            client.send_message("⚠️ Список сохранённых брендов пуст. Добавьте: /addbrand Nike")
            return
        if not arg:
            client.send_message(
                "❗️ Не хватает номера.\n"
                "Формат: /removebrand &lt;номер&gt;\n"
                f"Посмотреть номера: /brands (сейчас их {len(brands)})"
            )
            return
        if not arg.isdigit():
            client.send_message(f"❗️ «{arg}» — это не число. Нужен номер из списка /brands, например: /removebrand 2")
            return
        n = int(arg)
        if not (1 <= n <= len(brands)):
            client.send_message(f"❗️ Номера {n} нет в списке — доступны от 1 до {len(brands)} (см. /brands).")
            return
        removed = brands.pop(n - 1)
        if state.get("brand") == removed:
            state["brand"] = None
        client.send_message(f"✅ Убран бренд: <b>{removed}</b>")

    elif cmd == "/brands":
        brands = state.get("brands", [])
        current = state.get("brand")
        lines = [f"Текущий бренд: <b>{current or '— не задан —'}</b>", ""]
        if brands:
            lines.append("Сохранённые бренды:")
            lines += [f"{i+1}. {b}" for i, b in enumerate(brands)]
        else:
            lines.append("Сохранённых брендов пока нет. Добавьте: /addbrand Nike")
        client.send_message("\n".join(lines))

    elif cmd == "/brand":
        brands = combined_brands(state, brands_list)
        if not brands:
            client.send_message(
                "⚠️ Брендов пока нет.\n"
                "Добавьте свой: /addbrand Nike\n"
                "Или задайте разовый текстом: /setbrand Nike"
            )
            return
        buttons = [
            (f"{BRAND_ICONS[i % len(BRAND_ICONS)]} {b}", f"brand:{b}")
            for i, b in enumerate(brands)
        ]
        buttons.append(("🚫 Без бренда", "brand:__none__"))
        markup = client.build_keyboard(buttons, columns=2)
        client.send_message("Выберите бренд:", reply_markup=markup)

    elif cmd == "/setbrand":
        if not arg:
            client.send_message(
                "❗️ Не хватает названия бренда.\n"
                "Формат: /setbrand &lt;бренд&gt;\n"
                "Пример: /setbrand Nike"
            )
            return
        state["brand"] = arg
        client.send_message(f"✅ Бренд установлен: <b>{arg}</b>")

    elif cmd == "/clearbrand":
        if not state.get("brand"):
            client.send_message("ℹ️ Бренд и так не задан.")
            return
        state["brand"] = None
        client.send_message("✅ Бренд сброшен — ищу без привязки к бренду.")

    elif cmd == "/search":
        if not arg:
            client.send_message(
                "❗️ Не хватает текста запроса.\n"
                "Формат: /search &lt;что искать&gt;\n"
                "Пример: /search термос"
            )
            return
        brand = state.get("brand")
        full_query = f"{brand} {arg}" if brand else arg
        client.send_message(f"🔎 Ищу: <b>{full_query}</b> …")
        try:
            results = run_search_fn(full_query)
        except Exception as e:
            log.error("Ошибка разового поиска: %s", e)
            client.send_message(f"⚠️ Не получилось выполнить поиск: {e}")
            return
        if not results:
            client.send_message(
                "😕 Ничего подходящего не нашлось под текущие пороги качества "
                "(цена/рейтинг/отзывы) — попробуйте другой запрос."
            )

    elif cmd.startswith("/"):
        client.send_message(
            f"❓ Не знаю команду «{cmd}».\n"
            f"Доступные команды: {', '.join(KNOWN_COMMANDS)}.\n"
            "Подробности — /help."
        )

    else:
        client.send_message(
            f"❓ Не поняла сообщение «{text}» — это не похоже на команду.\n"
            "Все команды начинаются со слэша, например /addquery термос.\n"
            "Список команд — /help."
        )

Плюс маленькая правка в state.py — добавьте поле "brands": [] в DEFAULT_STATE:

python
DEFAULT_STATE = {
    "update_offset": 0,   # id последнего обработанного Telegram-апдейта
    "brand": None,         # текущий выбранный бренд (или None)
    "brands": [],           # свои сохранённые бренды, добавленные через /addbrand
    "queries": [],          # список активных поисковых запросов (строки)
}
