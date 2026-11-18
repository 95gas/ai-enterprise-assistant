import uuid
from typing import Any, Dict, List

from sqlalchemy import select

from src.common.connectors.postgres.base import PostgresManager, get_postgres_manager
from src.common.connectors.postgres.models import ChatRecord
from src.common.logging.logger import DebugLogger


class ChatRepo:
    def __init__(self, db_manager: PostgresManager = None):
        self.db_manager = db_manager or get_postgres_manager()
        self.logger = DebugLogger(class_name=self.__class__.__name__, main_feature="DATABASE")

    def get_all(self, user_email: str) -> List[Dict[str, Any]]:
        with self.db_manager.session() as session:
            records = session.scalars(
                select(ChatRecord).where(ChatRecord.user_email == user_email)
                .order_by(ChatRecord.last_edit.desc())
            ).all()
            return [{"_id": row.id, "_source": self._to_dict(row)} for row in records]

    def save(self, chat_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.db_manager.session() as session:
            record = session.get(ChatRecord, chat_id)
            if record is None:
                raise ValueError(f"No conversation found for chat_id: {chat_id}")
            for key in ("conversation", "chat_name", "last_edit"):
                if key in payload:
                    setattr(record, key, payload[key])
        return {"result": "updated", "_id": chat_id}

    def get(self, user_email: str, chat_id: str = None) -> Dict[str, Any]:
        with self.db_manager.session() as session:
            record = session.scalar(select(ChatRecord).where(
                ChatRecord.user_email == user_email,
                ChatRecord.id == chat_id,
            ))
            if record is None:
                raise ValueError(f"No conversation found for chat_id: {chat_id}")
            result = self._to_dict(record)
        return {
            "id": record.id,
            "name": result["chat_name"],
            "messages": result["conversation"],
            "creation_date": result["creation_date"],
            "last_edit": result["last_edit"],
        }

    def add(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        chat_id = str(uuid.uuid4())
        with self.db_manager.session() as session:
            session.add(ChatRecord(
                id=chat_id,
                user_email=payload["user"],
                chat_name=payload.get("chat_name") or "",
                conversation=payload.get("conversation") or [],
                creation_date=payload.get("creation_date", ""),
                last_edit=payload.get("last_edit", ""),
            ))
        return {"result": "created", "_id": chat_id}

    def delete(self, user: str, chat_id: str) -> Dict[str, Any]:
        with self.db_manager.session() as session:
            record = session.scalar(select(ChatRecord).where(
                ChatRecord.id == chat_id,
                ChatRecord.user_email == user,
            ))
            if record is None:
                return {"deleted": 0}
            session.delete(record)
        return {"deleted": 1}

    @staticmethod
    def _to_dict(record: ChatRecord) -> Dict[str, Any]:
        return {
            "user": record.user_email,
            "chat_name": record.chat_name,
            "conversation": record.conversation or [],
            "creation_date": record.creation_date,
            "last_edit": record.last_edit,
        }

    def config_log(self, user: str) -> None:
        self.logger.set_user(user)
