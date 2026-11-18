import uuid
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from typing import Dict, Optional

from sqlalchemy import func, select

from src.common.connectors.postgres.base import PostgresManager, get_postgres_manager
from src.common.connectors.postgres.models import ModelLimitRecord, TokenUsageRecord
from src.common.logging.logger import DebugLogger
from config.settings import settings

DATE_FORMAT = settings.DATE_FORMAT


class TokenRepo:
    def __init__(self, db_manager: Optional[PostgresManager] = None, logger: Optional[DebugLogger] = None):
        self.db_manager = db_manager or get_postgres_manager()
        self.logger = logger or DebugLogger(main_feature="DATABASE")
        self.logger.set_class_name(self.__class__.__name__)

    def save(self, user: str, input_tokens: int, output_tokens: int, llm_model: str, provider: str,
             label: str) -> None:
        timestamp = datetime.now(timezone.utc)
        with self.db_manager.session() as session:
            session.add(TokenUsageRecord(
                id=str(uuid.uuid4()),
                timestamp=timestamp,
                user=user or "UNDEFINED",
                input=input_tokens,
                output=output_tokens,
                total=input_tokens + output_tokens,
                model=llm_model,
                provider=provider,
                label=label,
            ))

    def get_total_tokens_usage_per_model(self, user_email: str) -> Dict:
        with self.db_manager.session() as session:
            totals = session.execute(
                select(
                    TokenUsageRecord.model,
                    TokenUsageRecord.provider,
                    func.sum(TokenUsageRecord.input + TokenUsageRecord.output),
                )
                .where(TokenUsageRecord.user == user_email)
                .group_by(TokenUsageRecord.model, TokenUsageRecord.provider)
            ).all()
        result = {}
        for model, provider, total in totals:
            result.setdefault(model, {})[provider] = {"tokens": int(total or 0)}
        return result

    def get_timeframe_total_token_usage_per_model(self, user_email: str, limits_info_per_model: dict) -> Dict:
        result = {}
        for model_name, providers in limits_info_per_model.items():
            for provider, limit in providers.items():
                period = limit.get("limit_reset_period")
                reset_value = limit.get("resetting_datetime")
                if not period or not reset_value:
                    continue
                reset_datetime = datetime.strptime(reset_value, DATE_FORMAT)
                start_datetime = datetime.strptime(
                    self.compute_date(period, reset_datetime, "sub"), DATE_FORMAT
                )
                start_utc = start_datetime.astimezone(timezone.utc)
                reset_utc = reset_datetime.astimezone(timezone.utc)
                with self.db_manager.session() as session:
                    total = session.scalar(
                        select(func.coalesce(func.sum(TokenUsageRecord.input + TokenUsageRecord.output), 0))
                        .where(
                            TokenUsageRecord.user == user_email,
                            TokenUsageRecord.model == model_name,
                            TokenUsageRecord.provider == provider,
                            TokenUsageRecord.timestamp >= start_utc,
                            TokenUsageRecord.timestamp <= reset_utc,
                        )
                    )
                result.setdefault(model_name, {})[provider] = {"tokens": int(total or 0)}
        return result

    def get_overall_tokens_usage_per_model(self, user_email: str, limit_info_models: Dict) -> Dict:
        total_usage = self.get_total_tokens_usage_per_model(user_email)
        timeframe_usage = self.get_timeframe_total_token_usage_per_model(user_email, limit_info_models)
        return {
            model_name: {
                provider: {
                    "tot_tokens": total_usage.get(model_name, {}).get(provider, {}).get("tokens", 0),
                    "tot_tokens_timeframe": timeframe_usage.get(model_name, {}).get(provider, {}).get("tokens", 0),
                }
                for provider in providers
            }
            for model_name, providers in limit_info_models.items()
        }

    def get_limits_info_per_model(self, user_email: str, models_info_dict: Dict) -> Dict:
        with self.db_manager.session() as session:
            records = session.scalars(
                select(ModelLimitRecord).where(ModelLimitRecord.user_email == user_email)
            ).all()
        limits = {}
        for row in records:
            limits.setdefault(row.model, {})[row.provider] = {
                    "id": row.id,
                    "tokens_limit": row.tokens_limit,
                    "limit_reset_period": row.limit_reset_period,
                    "resetting_datetime": row.resetting_datetime,
                }
        for model_data in models_info_dict.get("chat_models", []):
            provider = model_data["provider"]
            custom_name = model_data["custom_name"]
            model_config = models_info_dict["providers"][provider][custom_name]
            actual_model_name = model_config["actual_model_name"]
            if provider not in limits.get(actual_model_name, {}):
                limit = self.create_user_limits_info_per_model(user_email, models_info_dict, model_data)
                limits.setdefault(actual_model_name, {})[provider] = limit
        return limits

    def create_user_limits_info_per_model(self, user_email: str, models_info_dict: Dict,
                                          model_data: Dict[str, str]) -> Dict:
        provider = model_data["provider"]
        model_config = models_info_dict["providers"][provider][model_data["custom_name"]]
        limit = self._new_limit(model_config)
        with self.db_manager.session() as session:
            existing = session.scalar(select(ModelLimitRecord).where(
                ModelLimitRecord.user_email == user_email,
                ModelLimitRecord.provider == provider,
                ModelLimitRecord.model == model_config["actual_model_name"],
            ))
            if existing is not None:
                return {
                    "id": existing.id,
                    "tokens_limit": existing.tokens_limit,
                    "limit_reset_period": existing.limit_reset_period,
                    "resetting_datetime": existing.resetting_datetime,
                }
            session.add(ModelLimitRecord(
                    id=limit["id"],
                    user_email=user_email,
                    provider=provider,
                    model=model_config["actual_model_name"],
                    tokens_limit=limit["tokens_limit"],
                    limit_reset_period=limit["limit_reset_period"],
                    resetting_datetime=limit["resetting_datetime"],
                ))
        return limit

    def check_and_update_resetting_datetime(self, model_name: str, limit_info_models: Dict):
        model_limits = limit_info_models.get(model_name)
        if not model_limits:
            self.logger.warning(f"No limit info for model '{model_name}'.")
            return
        limit = next(iter(model_limits.values()))
        if datetime.strptime(limit["resetting_datetime"], DATE_FORMAT) <= datetime.now():
            self.update_resetting_datetime(limit)

    def update_resetting_datetime(self, model_data):
        current_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        reset_date = self.compute_date(model_data["limit_reset_period"], current_date, "add")
        with self.db_manager.session() as session:
            record = session.get(ModelLimitRecord, model_data["id"])
            if record is None:
                raise ValueError(f"Model limit {model_data['id']} was not found.")
            record.resetting_datetime = reset_date
        model_data["resetting_datetime"] = reset_date

    @staticmethod
    def _new_limit(model_config: Dict) -> Dict:
        current_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        period = model_config["limit_reset_period"]
        return {
            "id": str(uuid.uuid4()),
            "tokens_limit": model_config["default_tokens_limit"],
            "limit_reset_period": period,
            "resetting_datetime": TokenRepo.compute_date(period, current_date, "add"),
        }

    @staticmethod
    def compute_date(period: str, date_time: datetime, mode: str, _format: str = DATE_FORMAT):
        deltas = {
            "day": timedelta(days=1),
            "week": timedelta(weeks=1),
            "month": relativedelta(months=1),
            "year": relativedelta(years=1),
        }
        delta = deltas.get(period)
        if delta is None:
            raise ValueError(f"Unsupported token limit reset period: {period}")
        if mode not in {"add", "sub"}:
            raise ValueError(f"Unsupported date operation: {mode}")
        result = date_time + delta if mode == "add" else date_time - delta
        return result.strftime(_format)

    def config_log(self, user: Optional[str]) -> None:
        self.logger.set_user(user)
