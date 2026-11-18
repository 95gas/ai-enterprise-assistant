from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password: Mapped[str] = mapped_column(Text, default="")
    name: Mapped[str] = mapped_column(String(255), default="")
    groups: Mapped[list] = mapped_column(JSON, default=list)
    domain: Mapped[str] = mapped_column(String(255), default="")
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    last_login: Mapped[str] = mapped_column(Text, default="")
    tot_token_limit: Mapped[int] = mapped_column(Integer, default=0)
    tot_limit_reset_period: Mapped[str] = mapped_column(String(32), default="day")
    expiring_date_trial: Mapped[str] = mapped_column(Text, default="")


class ChatRecord(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_email: Mapped[str] = mapped_column(String(320), index=True)
    chat_name: Mapped[str] = mapped_column(Text, default="")
    conversation: Mapped[list] = mapped_column(JSON, default=list)
    creation_date: Mapped[str] = mapped_column(Text, default="")
    last_edit: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (Index("ix_chats_user_last_edit", "user_email", "last_edit"),)


class FeedbackRecord(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(255), index=True)
    user_email: Mapped[str] = mapped_column(String(320), default="", index=True)
    timestamp: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class TokenUsageRecord(Base):
    __tablename__ = "token_usage"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user: Mapped[str] = mapped_column(String(320), index=True)
    input: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(255), index=True)
    provider: Mapped[str] = mapped_column(String(100), index=True)
    label: Mapped[str] = mapped_column(String(255), default="", index=True)


class ModelLimitRecord(Base):
    __tablename__ = "model_limits"
    __table_args__ = (UniqueConstraint("user_email", "provider", "model", name="uq_model_limit_user_provider_model"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_email: Mapped[str] = mapped_column(String(320), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    tokens_limit: Mapped[int] = mapped_column(Integer)
    limit_reset_period: Mapped[str] = mapped_column(String(32))
    resetting_datetime: Mapped[str] = mapped_column(Text)
