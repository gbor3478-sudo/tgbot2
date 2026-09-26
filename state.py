"""Простое JSON-хранилище состояния бота: список запросов, выбранный бренд,
offset для Telegram getUpdates (чтобы не обрабатывать одни и те же сообщения дважды).

Файл коммитится обратно в репозиторий GitHub Actions'ом — так состояние
переживает между запусками workflow (сервера с постоянной памятью у нас нет).
"""

import json
from pathlib import Path

STATE_FILE = Path(__file__).parent / "state.json"

DEFAULT_STATE = {
    "update_offset": 0,   # id последнего обработанного Telegram-апдейта
    "brand": None,        # текущий выбранный бренд (или None)
    "queries": [],         # список активных поисковых запросов (строки)
}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            merged = {**DEFAULT_STATE, **data}
            return merged
        except Exception:
            pass
    return dict(DEFAULT_STATE)


def save_state(state: dict):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
