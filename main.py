"""
1688 Telegram Bot — интерактивная версия.

При каждом запуске:
1. забирает новые сообщения/нажатия кнопок из Telegram и обрабатывает команды
   (/addquery, /removequery, /brand, /setbrand, /search и т.д.) — см. bot_commands.py;
2. выполняет плановый поиск по сохранённому списку запросов (с учётом бренда)
   и присылает новые подходящие товары.

Всё состояние (запросы, бренд, оффсет апдейтов, уже отправленные товары)
хранится в JSON-файлах в репозитории и коммитится обратно workflow'ом.
"""

import os
import sys
import json
import logging
from pathlib import Path

from providers.tmapi import Tmapi1688Provider
from telegram_client import TelegramClient
from state import load_state, save_state
import bot_commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("1688-bot")

SEEN_FILE = Path(__file__).parent / "seen_items.json"


def env(name: str, default=None, required: bool = False):
    val = os.environ.get(name)
    if not val:
        val = default
    if required and not val:
        log.error("Не задана обязательная переменная окружения: %s", name)
        sys.exit(1)
    return val


TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", required=True)
TMAPI_KEY = env("TMAPI_KEY", required=True)

# Необязательно: кнопки для /brand, через запятую
BRANDS_LIST = [b.strip() for b in env("BRANDS_LIST", "").split(",") if b.strip()]

# Пороги качества
MAX_PRICE_CNY = float(env("MAX_PRICE_CNY", "150"))
MIN_RATING = float(env("MIN_RATING", "4.6"))
MIN_REVIEWS = int(env("MIN_REVIEWS", "200"))
MAX_RESULTS_PER_QUERY = int(env("MAX_RESULTS_PER_QUERY", "5"))
TOP_PERCENT_CHEAPEST = float(env("TOP_PERCENT_CHEAPEST", "30"))


# ---------- seen items ----------

def load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen(seen: set):
    trimmed = list(seen)[-5000:]
    SEEN_FILE.write_text(json.dumps(trimmed, ensure_ascii=False), encoding="utf-8")


# ---------- форматирование и фильтрация ----------

def format_item_message(item: dict) -> str:
    title = item.get("title", "Без названия")
    price = item.get("price")
    rating = item.get("rating")
    reviews = item.get("reviews")
    url = item.get("url", "")
    img = item.get("image", "")

    lines = [f"🛒 <b>{title}</b>"]
    if price is not None:
        lines.append(f"💰 Цена: {price} ¥")
    if rating is not None:
        lines.append(f"⭐ Рейтинг: {rating}")
    if reviews is not None:
        lines.append(f"💬 Отзывы/продажи: {reviews}")
    if url:
        lines.append(f"🔗 {url}")
    if img:
        lines.append(img)
    return "\n".join(lines)


def passes_quality_bar(item: dict) -> bool:
    price = item.get("price")
    rating = item.get("rating")
    reviews = item.get("reviews")

    if price is None or price <= 0 or price > MAX_PRICE_CNY:
        return False
    if rating is not None and rating < MIN_RATING:
        return False
    if reviews is not None and reviews < MIN_REVIEWS:
        return False
    return True


def rank_and_trim(items: list) -> list:
    if not items:
        return []
    items_sorted = sorted(items, key=lambda x: x.get("price", float("inf")))
    keep_n = max(1, int(len(items_sorted) * TOP_PERCENT_CHEAPEST / 100))
    return items_sorted[:keep_n][:MAX_RESULTS_PER_QUERY]


# ---------- поиск ----------

def make_search_runner(provider: Tmapi1688Provider, client: TelegramClient, seen: set):
    """Возвращает функцию run_search(query) -> list, которая ищет, фильтрует,
    шлёт новые товары в Telegram и помечает их как отправленные."""

    def run_search(query: str) -> list:
        try:
            raw_items = provider.search(query, limit=50)
        except Exception as e:
            log.error("Ошибка поиска по запросу '%s': %s", query, e)
            return []

        good = [i for i in raw_items if passes_quality_bar(i)]
        picked = rank_and_trim(good)

        sent = []
        for item in picked:
            item_id = item.get("id") or item.get("url")
            if not item_id or item_id in seen:
                continue
            client.send_message(format_item_message(item))
            seen.add(item_id)
            sent.append(item)
        return sent

    return run_search


def main():
    provider = Tmapi1688Provider(api_key=TMAPI_KEY)
    client = TelegramClient(token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
    state = load_state()
    seen = load_seen()

    run_search = make_search_runner(provider, client, seen)

    # 1. обработать новые команды/кнопки из Telegram
    state = bot_commands.handle_updates(state, client, BRANDS_LIST, run_search)

    # 2. плановый поиск по сохранённому списку запросов
    queries = bot_commands.effective_queries(state)
    if not queries:
        log.info("Список запросов пуст — плановый поиск пропущен. Добавьте через /addquery в Telegram.")
    else:
        total_sent = 0
        for query in queries:
            log.info("Плановый поиск: %s", query)
            sent = run_search(query)
            total_sent += len(sent)
        log.info("Плановый поиск завершён, отправлено новых товаров: %d", total_sent)

    save_seen(seen)
    save_state(state)


if __name__ == "__main__":
    main()
