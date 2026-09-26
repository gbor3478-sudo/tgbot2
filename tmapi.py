"""
Провайдер данных с 1688.com через TMAPI (https://www.tmapi.top).

ВАЖНО: TMAPI — сторонний коммерческий сервис, который агрегирует данные
с 1688/Taobao/Alibaba и отдаёт их через REST API. Нужен свой API-ключ
(есть бесплатный пробный тариф) — зарегистрируйтесь на их сайте и
положите ключ в переменную окружения TMAPI_KEY / secret в GitHub.

Точные названия полей в ответе могут отличаться в зависимости от версии
их API — при первом запуске стоит вывести raw-ответ в лог (см. метод
search, debug=True) и при необходимости поправить _normalize_item под
актуальную схему из их документации.

Если решите использовать другого провайдера (Superbuy Open API,
CSSBuy API и т.п.) — просто напишите свой класс с тем же интерфейсом
(метод search(query, limit) -> list[dict]) и замените импорт в main.py.
"""

import logging
import requests

log = logging.getLogger("1688-bot.tmapi")

BASE_URL = "https://api.tmapi.top"  # см. https://tmapi.top/docs/start


class Tmapi1688Provider:
    def __init__(self, api_key: str, base_url: str = BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def search(self, query: str, limit: int = 50, debug: bool = False) -> list:
        """
        Возвращает список товаров в нормализованном виде:
        {id, title, price (float, CNY), rating (float|None), reviews (int|None),
         url, image}
        """
        # TMAPI передаёт ключ в заголовке "apikey" (не в query-параметре) —
        # см. https://console.tmapi.io/account/api-keys и раздел "Security Auth"
        # в документации любого их эндпоинта. Путь ниже — под 1688 item_search;
        # сверьте точное название пути в разделе "1688" на tmapi.top/docs,
        # если ваш тариф использует другое название.
        endpoint = f"{self.base_url}/1688/item_search"
        headers = {"apikey": self.api_key}
        params = {
            "keyword": query,
            "page": 1,
            "page_size": limit,
        }

        resp = requests.get(endpoint, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if debug:
            log.info("RAW RESPONSE: %s", data)

        raw_items = (
            data.get("data", {}).get("items")
            or data.get("result", {}).get("items")
            or data.get("items")
            or []
        )

        return [self._normalize_item(raw) for raw in raw_items if raw]

    @staticmethod
    def _normalize_item(raw: dict) -> dict:
        # Поля ниже — типичные названия у агрегаторов 1688-данных.
        # Поправьте под реальный ответ TMAPI, если что-то не совпадает.
        price = raw.get("price") or raw.get("promotionPrice") or raw.get("minPrice")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None

        rating = raw.get("sellerRating") or raw.get("rating") or raw.get("score")
        try:
            rating = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating = None

        reviews = raw.get("monthSold") or raw.get("sales") or raw.get("reviewCount")
        try:
            reviews = int(reviews) if reviews is not None else None
        except (TypeError, ValueError):
            reviews = None

        return {
            "id": raw.get("itemId") or raw.get("id") or raw.get("num_iid"),
            "title": raw.get("title") or raw.get("subject"),
            "price": price,
            "rating": rating,
            "reviews": reviews,
            "url": raw.get("detailUrl") or raw.get("url"),
            "image": raw.get("image") or raw.get("picUrl") or raw.get("pic_url"),
        }
