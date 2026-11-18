from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.common.logging.logger import DebugLogger
from config.settings import settings
from src.common.connectors.postgres.models import Base


class PostgresManager:
    def __init__(self, engine=None, logger: Optional[DebugLogger] = None):
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DATABASE")
        self.engine = engine or create_engine(settings.postgres.url, pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self):
        with self._session_factory.begin() as session:
            yield session

    def config_log(self, user: Optional[str]) -> None:
        self.logger.set_user(user)
        self.logger.set_class_name(self.__class__.__name__)
        self.logger.set_main_feature("DATABASE")


_default_manager = None


def get_postgres_manager() -> PostgresManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = PostgresManager()
    return _default_manager
