"""Create or reset a local test account. This script refuses production mode."""

import argparse
import re

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.security import hash_password


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identifier", required=True, help="Test email address or phone number")
    parser.add_argument("--password", required=True, help="At least 8 characters")
    parser.add_argument("--name", default="KAI 测试用户")
    return parser.parse_args()


def main() -> None:
    if settings.APP_ENV.casefold() == "production":
        raise SystemExit("Refusing to create a test user in production")
    args = parse_args()
    if len(args.password) < 8:
        raise SystemExit("Password must contain at least 8 characters")

    identifier = args.identifier.strip()
    is_email = "@" in identifier
    if is_email:
        identifier = identifier.casefold()
    else:
        identifier = re.sub(r"[\s()-]", "", identifier)
        if not re.fullmatch(r"\+?[0-9]{6,20}", identifier):
            raise SystemExit("Invalid phone number")

    with SessionLocal() as db:
        query = User.email == identifier if is_email else User.phone == identifier
        user = db.query(User).filter(query).first()
        if user is None:
            user = User(
                display_name=args.name.strip(),
                email=identifier if is_email else None,
                email_verified=False,
                phone=identifier if not is_email else None,
                phone_verified=False,
                role="personal",
                status="active",
            )
            db.add(user)
        user.display_name = args.name.strip()
        user.password_hash = hash_password(args.password)
        user.status = "active"
        db.commit()
        db.refresh(user)
        print(f"Test user ready: id={user.id}, identifier={identifier}")


if __name__ == "__main__":
    main()
