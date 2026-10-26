"""Загрузка .env из корня репо: секреты не живут в коде.

Внешние (уже установленные) переменные окружения НЕ перезаписываются —
.env лишь задаёт значения по умолчанию для локального запуска.
"""

import os
from pathlib import Path

REPO = next(
    (
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / ".env.example").exists()  # якорь корня репо
    ),
    Path(__file__).resolve().parents[3],
)


def load_env() -> None:
    env_file = REPO / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def required(name: str) -> str:
    """Обязательная переменная; без неё — понятная ошибка вместо тихого фолбэка."""
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"Не задана переменная окружения {name}.\n"
            "Скопируйте .env.example → .env в корне репо и заполните значения "
            "(docs/user-guide.md §1). Секреты в коде не хранятся."
        )
    return value
