"""Обработка входящих сообщений и нажатий на кнопки от пользователя.

Команды:
  /start, /help          — подсказка
  /addquery <текст>      — добавить запрос в постоянный список
  /removequery <номер>   — убрать запрос по номеру из /queries
  /queries               — показать текущий список запросов и бренд
  /brand                 — показать кнопки с брендами (из BRANDS_LIST) для выбора
  /setbrand <текст>      — задать бренд вручную (если своего варианта нет в кнопках)
  /clearbrand            — сбросить бренд (искать без привязки к бренду)
  /search <текст>        — разовый поиск прямо сейчас, без сохранения в список

Бренд, если задан, подставляется в начало каждого запроса при поиске
(например бренд "Nike" + запрос "кроссовки" → ищем "Nike кроссовки").
"""

import logging

log = logging.getLogger("1688-bot.commands")

HELP_TEXT = (
    "Я ищу товары на 1688.com по вашим запросам.\n\n"
    "<b>Команды:</b>\n"
    "/addquery &lt;текст&gt; — добавить запрос в постоянный поиск\n"
    "/removequery &lt;номер&gt; — убрать запрос (номер из /queries)\n"
    "/queries — показать список запросов и текущий бренд\n"
    "/brand — выбрать бренд кнопками\n"
    "/setbrand &lt;текст&gt; — задать свой бренд текстом\n"
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

def handle_updates(state: dict, client, brands_list: list, run_search_fn, poll_timeout: int = 0):
    """
    Забирает новые апдейты из Telegram, обрабатывает команды, обновляет state.
    run_search_fn(query: str) -> list[dict]  — функция мгновенного поиска для /search.
    poll_timeout — сколько секунд ждать новых сообщений (long polling Telegram).
    0 — вернуться сразу, если сообщений нет (для разового запуска).
    Возвращает обновлённый state.
    """
    updates = client.get_updates(offset=state.get("update_offset", 0) + 1, timeout=poll_timeout)


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


def _handle_text_command(text: str, state: dict, client, brands_list: list, run_search_fn):
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        client.send_message(HELP_TEXT)

    elif cmd == "/addquery":
        if not arg:
            client.send_message("Укажите, что искать: /addquery термос")
            return
        state.setdefault("queries", [])
        if arg in state["queries"]:
            client.send_message("Такой запрос уже есть в списке.")
        else:
            state["queries"].append(arg)
            client.send_message(f"Добавлено: <b>{arg}</b>")

    elif cmd == "/removequery":
        queries = state.get("queries", [])
        if not arg.isdigit() or not (1 <= int(arg) <= len(queries)):
            client.send_message("Укажите номер из списка /queries, например: /removequery 2")
            return
        removed = queries.pop(int(arg) - 1)
        client.send_message(f"Убрано: <b>{removed}</b>")

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

    elif cmd == "/brand":
        if not brands_list:
            client.send_message(
                "Список брендов для кнопок не настроен (secret BRANDS_LIST).\n"
                "Задайте бренд текстом: /setbrand Nike"
            )
            return
        buttons = [(b, f"brand:{b}") for b in brands_list]
        buttons.append(("Без бренда", "brand:__none__"))
        markup = client.build_keyboard(buttons, columns=2)
        client.send_message("Выберите бренд:", reply_markup=markup)

    elif cmd == "/setbrand":
        if not arg:
            client.send_message("Укажите бренд: /setbrand Nike")
            return
        state["brand"] = arg
        client.send_message(f"Бренд установлен: <b>{arg}</b>")

    elif cmd == "/clearbrand":
        state["brand"] = None
        client.send_message("Бренд сброшен — ищу без привязки к бренду.")

    elif cmd == "/search":
        if not arg:
            client.send_message("Укажите, что искать: /search термос")
            return
        brand = state.get("brand")
        full_query = f"{brand} {arg}" if brand else arg
        client.send_message(f"Ищу: <b>{full_query}</b> …")
        try:
            results = run_search_fn(full_query)
        except Exception as e:
            log.error("Ошибка разового поиска: %s", e)
            client.send_message("Не получилось выполнить поиск, попробуйте позже.")
            return
        if not results:
            client.send_message("Ничего подходящего не нашлось под текущие пороги качества.")

    else:
        client.send_message("Не знаю такую команду. Наберите /help.")
