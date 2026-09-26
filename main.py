"""
1688 Telegram Bot
Ищет товары на 1688.com через провайдера данных, фильтрует по цене/качеству/отзывам
и присылает подборку в Telegram.

Запуск: python main.py
Настройки — через переменные окружения (см. README.md).
"""

import os
import sys
import json
import logging
from pathlib import Path

import requests

from providers.tmapi import Tmapi1688Provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("1688-bot")

STATE_FILE = Path(__file__).parent / "seen_items.json"


# ---------- Конфиг из переменных окружения ----------

def env(name: str, default=None, required: bool = False):
    val = os.environ.get(name, default)
    if required and not val:
        log.error("Не задана обязательная переменная окружения: %s", name)
        sys.exit(1)
    return val


TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", required=True)
TMAPI_KEY = env("TMAPI_KEY", required=True)

# Что искать. Можно задать несколько запросов через ';'
SEARCH_QUERIES = [q.strip() for q in env("SEARCH_QUERIES", "").split(";") if q.strip()]

# Пороги качества — разумные значения по умолчанию, можно переопределить в secrets/env
MAX_PRICE_CNY = float(env("MAX_PRICE_CNY", "150"))          # максимальная цена в юанях
MIN_RATING = float(env("MIN_RATING", "4.6"))                 # мин. рейтинг магазина/товара (из 5)
MIN_REVIEWS = int(env("MIN_REVIEWS", "200"))                 # мин. число отзывов/продаж
MAX_RESULTS_PER_QUERY = int(env("MAX_RESULTS_PER_QUERY", "5"))
TOP_PERCENT_CHEAPEST = float(env("TOP_PERCENT_CHEAPEST", "30"))  # оставляем самые дешёвые X% из отфильтрованных


# ---------- Хранение уже отправленных товаров (чтобы не дублировать) ----------

def load_seen() -> set:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen(seen: set):
    # ограничиваем размер файла, чтобы не рос бесконечно
    trimmed = list(seen)[-5000:]
    STATE_FILE.write_text(json.dumps(trimmed, ensure_ascii=False), encoding="utf-8")


# ---------- Telegram ----------

def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    if not resp.ok:
        log.error("Ошибка отправки в Telegram: %s %s", resp.status_code, resp.text)


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
        # ссылку на картинку просто добавляем отдельной строкой —
        # Telegram сам покажет превью, если разрешено
        lines.append(img)
    return "\n".join(lines)


# ---------- Фильтрация ----------

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
    """Из прошедших порог качества берём самые дешёвые TOP_PERCENT_CHEAPEST%."""
    if not items:
        return []
    items_sorted = sorted(items, key=lambda x: x.get("price", float("inf")))
    keep_n = max(1, int(len(items_sorted) * TOP_PERCENT_CHEAPEST / 100))
    return items_sorted[:keep_n][:MAX_RESULTS_PER_QUERY]


# ---------- Основной цикл ----------

def main():
    if not SEARCH_QUERIES:
        log.error(
            "SEARCH_QUERIES пуст. Задайте, что искать, например: "
            "'спортивная сумка;термос;наушники' в secrets/переменных окружения."
        )
        sys.exit(1)

    provider = Tmapi1688Provider(api_key=TMAPI_KEY)
    seen = load_seen()
    total_sent = 0

    for query in SEARCH_QUERIES:
        log.info("Ищу: %s", query)
        try:
            raw_items = provider.search(query, limit=50)
        except Exception as e:
            log.error("Ошибка поиска по запросу '%s': %s", query, e)
            continue

        good = [i for i in raw_items if passes_quality_bar(i)]
        picked = rank_and_trim(good)

        for item in picked:
            item_id = item.get("id") or item.get("url")
            if not item_id or item_id in seen:
                continue
            send_telegram_message(format_item_message(item))
            seen.add(item_id)
            total_sent += 1

    save_seen(seen)
    log.info("Готово. Отправлено новых товаров: %d", total_sent)


if __name__ == "__main__":
    main()
