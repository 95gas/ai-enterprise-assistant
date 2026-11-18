import argparse
from datetime import datetime, timezone
from getpass import getpass

from src.services.authentication.hashing import PasswordHasher
from src.common.connectors.postgres.base import get_postgres_manager
from src.common.connectors.postgres.user import UserRepo
from config.settings import settings
from src.schema.user import User, UserPermissions


def main():
    parser = argparse.ArgumentParser(description="Create or update a PostgreSQL-backed application user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--domain", default="")
    parser.add_argument("--groups", default="")
    args = parser.parse_args()

    password = getpass("Password: ")
    if not password:
        raise ValueError("Password cannot be empty.")
    defaults = settings.credentials.default_values
    user = User(
        id=args.email,
        password=password, #PasswordHasher.hash_password(password),
        email=args.email,
        name=args.name,
        groups=[group.strip() for group in args.groups.split(",") if group.strip()],
        domain=args.domain,
        permissions=UserPermissions(),
        last_login=datetime.now(timezone.utc).strftime(settings.DATE_FORMAT),
        tot_token_limit=defaults.tot_token_limit,
        tot_limit_reset_period=defaults.tot_limit_reset_period,
        expiring_date_trial=defaults.expiring_date_trial,
    )
    manager = get_postgres_manager()
    manager.initialize()
    UserRepo(manager).save(user)
    print(f"User {args.email} created or updated.")


if __name__ == "__main__":
    main()
