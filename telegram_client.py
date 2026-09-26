"""Минимальная обёртка над Telegram Bot API: получение апдейтов, отправка
сообщений и инлайн-кнопок, ответ на нажатие кнопки.
"""

import json
import logging
import requests

log = logging.getLogger("1688-bot.telegram")


class TelegramClient:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id)
        self.base = f"https://api.telegram.org/bot{token}"

    def get_updates(self, offset: int, timeout: int = 0) -> list:
        resp = requests.get(
            f"{self.base}/getUpdates",
            params={"offset": offset, "timeout": timeout},
            timeout=timeout + 15,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])

    def send_message(self, text: str, reply_markup: dict = None):
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        resp = requests.post(f"{self.base}/sendMessage", data=payload, timeout=20)
        if not resp.ok:
            log.error("sendMessage failed: %s %s", resp.status_code, resp.text)
        return resp

    def answer_callback_query(self, callback_query_id: str, text: str = ""):
        resp = requests.post(
            f"{self.base}/answerCallbackQuery",
            data={"callback_query_id": callback_query_id, "text": text},
            timeout=20,
        )
        if not resp.ok:
            log.error("answerCallbackQuery failed: %s %s", resp.status_code, resp.text)
        return resp

    def build_keyboard(self, buttons: list, columns: int = 2) -> dict:
        """buttons: список (label, callback_data). Возвращает inline_keyboard markup."""
        rows = []
        row = []
        for label, data in buttons:
            row.append({"text": label, "callback_data": data})
            if len(row) == columns:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return {"inline_keyboard": rows}
