#!/usr/bin/env python
"""Выпуск per-role JWT для Cube REST API — RBAC-демо (docs/cube-rbac.md).

    uv run python scripts/make-cube-token.py --group admin
    uv run python scripts/make-cube-token.py --group user --region AFRICA --ttl 900

Секрет берётся из CUBEJS_API_SECRET (.env). Группа и регион попадают ТОЛЬКО
в подписанные claims — на stdout только сам токен (удобно для $(...)).
"""

import argparse
import sys

from harness.env import load_env, required
from harness.tokens import mint_cube_token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True, help="группа RBAC: admin | user | произвольная")
    parser.add_argument(
        "--region", default="", help="регион клиента для группы user (напр. AFRICA)"
    )
    parser.add_argument(
        "--ttl", type=int, default=600, help="время жизни токена, секунд (default 600)"
    )
    args = parser.parse_args()

    load_env()
    claims = {"groups": [args.group]}
    if args.region:
        claims["region"] = args.region
    token = mint_cube_token(required("CUBEJS_API_SECRET"), claims, ttl_seconds=args.ttl)
    print(token)
    print(f"claims: {claims}, ttl={args.ttl}s"[:120], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
