"""Command-line admin tasks.

Usage:
    python -m app.cli create-user <email> <password>
"""

import argparse
import asyncio
import contextlib
import sys

from fastapi_users.exceptions import UserAlreadyExists

from app.db import async_session_maker
from app.schemas.user import UserCreate
from app.users import get_user_db, get_user_manager


async def create_user(email: str, password: str) -> None:
    async with async_session_maker() as session:
        user_db_gen = get_user_db(session)
        user_db = await user_db_gen.__anext__()
        manager_gen = get_user_manager(user_db)
        manager = await manager_gen.__anext__()
        try:
            user = await manager.create(
                UserCreate(email=email, password=password, is_active=True, is_superuser=True)
            )
            print(f"Created user: {user.email}")
        except UserAlreadyExists:
            print(f"User already exists: {email}", file=sys.stderr)
            sys.exit(1)
        finally:
            with contextlib.suppress(StopAsyncIteration):
                await manager_gen.__anext__()
            with contextlib.suppress(StopAsyncIteration):
                await user_db_gen.__anext__()


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    cu = sub.add_parser("create-user", help="Create an active superuser")
    cu.add_argument("email")
    cu.add_argument("password")
    args = parser.parse_args()

    if args.command == "create-user":
        asyncio.run(create_user(args.email, args.password))


if __name__ == "__main__":
    main()
