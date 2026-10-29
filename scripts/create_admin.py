r"""Create the first administrator (or another user) without seeding passwords.

Usage (from the repository root):

    .\.venv\Scripts\python.exe .\scripts\create_admin.py --email admin@example.com

The password is read from the ADMIN_PASSWORD environment variable when set,
otherwise from a hidden prompt. It is never written to logs or the database in
plain text.

The command is idempotent only in the sense that it refuses to overwrite an
existing account; use the API or a deliberate migration for password changes.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.auth import normalize_email, record_audit  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Login email")
    parser.add_argument(
        "--role",
        default="admin",
        choices=("admin", "operator", "viewer"),
        help="Role for the new account (default: admin)",
    )
    return parser.parse_args()


def read_password() -> str:
    from_env = os.environ.get("ADMIN_PASSWORD")
    if from_env:
        return from_env

    first = getpass.getpass("Password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise SystemExit("Passwords do not match")
    return first


def main() -> int:
    args = parse_args()

    try:
        email = validate_email(args.email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        print(f"Invalid email: {exc}", file=sys.stderr)
        return 2

    email = normalize_email(email)
    password = read_password()

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    with SessionLocal() as session:
        existing = session.scalar(
            select(User).where(func.lower(User.email) == email)
        )
        if existing is not None:
            print(f"User already exists: {email}", file=sys.stderr)
            return 1

        user = User(
            email=email,
            password_hash=password_hash,
            role=args.role,
        )
        session.add(user)
        session.flush()
        record_audit(
            session,
            action="USER_CREATED",
            entity_type="user",
            user_id=user.id,
            entity_id=str(user.id),
            detail={"role": args.role, "source": "create_admin_cli"},
        )
        session.commit()
        print(f"Created {args.role} user: {email} ({user.id})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
