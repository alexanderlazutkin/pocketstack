"""Стресс-тест Cube REST /load (Stage 7, шаг 5): конкурентный доступ к пулу.

Запуск: uv run python scripts/cube_stress.py [N] [CONCURRENCY] [URL]
Проверяет: все запросы 200, тела ответов ИДЕНТИЧНЫ (консистентность пула коннектов
— «плавающие» ошибки инициализации ATTACH/SET проявились бы как 500/разные ответы).
Стандартная библиотека, без зависимостей.
"""

import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:4000"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
CONCURRENCY = int(sys.argv[2]) if len(sys.argv) > 2 else 30

QUERY = {
    "measures": ["sales.revenue", "sales.orders_count"],
    "dimensions": ["sales.customer_region"],
    "order": {"sales.revenue": "desc"},
}


def one(i: int) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{URL}/cubejs-api/v1/load",
        data=json.dumps({"query": QUERY}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
    results = list(pool.map(one, range(N)))

codes = [c for c, _ in results]
# Сравниваем только data: lastUpdatedTime/requestId легитимно уникальны per request
datas = {json.dumps(json.loads(b).get("data"), sort_keys=True) for c, b in results if c == 200}
errors = [b for c, b in results if c != 200]

print(f"запросов: {N}, конкурентность: {CONCURRENCY}")
print("коды:", {c: codes.count(c) for c in set(codes)})
print(f"уникальных data: {len(datas)} (ожидается 1)")
if errors:
    print("ПРИМЕР ОШИБКИ:", errors[0][:300])
    sys.exit(1)
if len(datas) != 1:
    print("FAIL: data расходятся — плавающая неконсистентность пула коннектов")
    sys.exit(1)
print("OK: все 200, data идентичны")
