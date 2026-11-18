from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_, select

from src.common.connectors.postgres.base import PostgresManager, get_postgres_manager
from src.common.connectors.postgres.models import UserRecord
from src.common.logging.logger import DebugLogger
from src.schema.user import User, UserPermissions
from config.settings import settings


class UserRepo:
    def __init__(self, db_manager: Optional[PostgresManager] = None):
        self.db_manager = db_manager or get_postgres_manager()
        self.logger = DebugLogger(class_name=self.__class__.__name__, main_feature="DATABASE")

    def get(self, user_id: str) -> User:
        with self.db_manager.session() as session:
            record = session.scalar(select(UserRecord).where(
                or_(UserRecord.id == user_id, UserRecord.email == user_id)
            ))
            if record is None:
                from src.services.authentication.errors import UserNotFoundError
                raise UserNotFoundError(f"User {user_id} not found in the database.")

            defaults = settings.credentials.default_values
            data = {
                "id": record.id,
                "password": record.password or "",
                "email": record.email,
                "name": record.name or "",
                "groups": record.groups or [],
                "domain": record.domain or "",
                "permissions": record.permissions or {},
                "last_login": datetime.now(timezone.utc).strftime(settings.DATE_FORMAT),
                "tot_token_limit": record.tot_token_limit if record.tot_token_limit is not None else defaults.tot_token_limit,
                "tot_limit_reset_period": record.tot_limit_reset_period or defaults.tot_limit_reset_period,
                "expiring_date_trial": record.expiring_date_trial or defaults.expiring_date_trial,
            }
        return User(
            id=data["id"],
            password=data["password"],
            email=data["email"],
            name=data["name"],
            groups=data["groups"],
            domain=data["domain"],
            permissions=UserPermissions(**data["permissions"]),
            last_login=data["last_login"],
            tot_token_limit=int(data["tot_token_limit"]),
            tot_limit_reset_period=data["tot_limit_reset_period"],
            expiring_date_trial=data["expiring_date_trial"],
        )

    def save(self, user: User) -> None:
        with self.db_manager.session() as session:
            record = session.scalar(select(UserRecord).where(
                or_(UserRecord.id == user.id, UserRecord.email == user.email)
            ))
            if record is None:
                record = UserRecord(id=user.id, email=user.email)
                session.add(record)
            record.id = user.id
            record.email = user.email
            record.password = user.password or ""
            record.name = user.name
            record.groups = list(user.groups or [])
            record.domain = user.domain
            record.permissions = user.permissions.model_dump()
            record.last_login = user.last_login
            record.tot_token_limit = user.tot_token_limit
            record.tot_limit_reset_period = user.tot_limit_reset_period
            record.expiring_date_trial = user.expiring_date_trial

    def delete(self, user_id: str) -> None:
        with self.db_manager.session() as session:
            record = session.scalar(select(UserRecord).where(
                or_(UserRecord.id == user_id, UserRecord.email == user_id)
            ))
            if record is not None:
                session.delete(record)
                self.logger.warning(f"User {user_id} deleted from PostgreSQL.")

    def config_log(self, user: Optional[str]) -> None:
        self.logger.set_user(user)
