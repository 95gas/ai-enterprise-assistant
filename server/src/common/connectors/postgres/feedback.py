import json
import uuid
from typing import Any, Dict

from src.common.connectors.postgres.base import PostgresManager, get_postgres_manager
from src.common.connectors.postgres.models import FeedbackRecord
from src.common.logging.logger import DebugLogger


class FeedbackRepo:
    def __init__(self, db_manager: PostgresManager = None):
        self.db_manager = db_manager or get_postgres_manager()
        self.logger = DebugLogger(class_name=self.__class__.__name__, main_feature="DATABASE")

    def save(self, chat_id: str, feedback: Dict[str, Any]) -> str:
        feedback["chat_id"] = chat_id
        feedback_id = str(uuid.uuid4())
        with self.db_manager.session() as session:
            session.add(FeedbackRecord(
                id=feedback_id,
                chat_id=chat_id,
                user_email=feedback.get("user_email", ""),
                timestamp=feedback.get("timestamp", ""),
                data=feedback,
            ))
        return json.dumps({"result": "created", "_id": feedback_id})

    def config_log(self, user: str) -> None:
        self.logger.set_user(user)
