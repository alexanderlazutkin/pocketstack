"""Выпуск JWT для Cube REST API: HS256 на CUBEJS_API_SECRET, только stdlib.

Claims токена становятся securityContext запроса: например
``{"groups": ["user"], "region": "AFRICA"}`` → contextToGroups в cube.js
назначает группу, access_policy в модели режет меры и строки
(docs/cube-rbac.md). Токены короткоживущие (exp), секрет не покидает .env.
"""

import base64
import hashlib
import hmac
import json
import time


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def mint_cube_token(secret: str, claims: dict, ttl_seconds: int = 600) -> str:
    """Подписать HS256-JWT: произвольные claims + стандартные iat/exp."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {**claims, "iat": now, "exp": now + int(ttl_seconds)}
    signing_input = b".".join(
        [
            _b64url(json.dumps(header, separators=(",", ":")).encode()),
            _b64url(json.dumps(payload, separators=(",", ":")).encode()),
        ]
    )
    signature = _b64url(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return (signing_input + b"." + signature).decode()


def verify_cube_token(secret: str, token: str) -> dict:
    """Проверить подпись и вернуть claims (exp НЕ проверяется — только roundtrip-тесты)."""
    head_b64, payload_b64, sig_b64 = token.split(".")

    def _pad(chunk: str) -> bytes:
        return base64.urlsafe_b64decode(chunk + "=" * (-len(chunk) % 4))

    expected = hmac.new(
        secret.encode(), f"{head_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected, _pad(sig_b64)):
        raise ValueError("подпись JWT не сходится")
    return json.loads(_pad(payload_b64))
