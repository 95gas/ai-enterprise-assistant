import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.common.connectors.postgres.base import PostgresManager
from src.common.connectors.postgres.chat import ChatRepo
from src.common.connectors.postgres.models import Base
from src.common.connectors.postgres.token import TokenRepo
from src.common.connectors.postgres.user import UserRepo
from src.schema.user import User, UserPermissions


@pytest.fixture
def db_manager():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return PostgresManager(engine=engine)


def test_user_repository_saves_and_loads_user(db_manager):
    user = User(
        id="person@example.com",
        password="hashed",
        email="person@example.com",
        name="Person",
        groups=["research"],
        domain="example",
        permissions=UserPermissions(doc_search=True),
        last_login="2026/01/01 00:00:00",
        tot_token_limit=5000,
        tot_limit_reset_period="day",
        expiring_date_trial="2100/12/31 00:00:00",
    )
    repository = UserRepo(db_manager)

    repository.save(user)

    loaded = repository.get("person@example.com")
    assert loaded.email == user.email
    assert loaded.groups == ["research"]
    assert loaded.permissions.doc_search is True
    assert loaded.tot_token_limit == 5000


def test_chat_repository_enforces_owner_on_read_and_delete(db_manager):
    repository = ChatRepo(db_manager)
    created = repository.add({
        "user": "owner@example.com",
        "chat_name": "A chat",
        "conversation": [{"role": "user", "content": "question"}],
        "creation_date": "2026/01/01 00:00:00",
        "last_edit": "2026/01/01 00:00:00",
    })

    assert repository.get_all("owner@example.com")[0]["_id"] == created["_id"]
    assert repository.get("owner@example.com", created["_id"])["messages"] == [
        {"role": "user", "content": "question"}
    ]
    assert repository.delete("other@example.com", created["_id"]) == {"deleted": 0}
    with pytest.raises(ValueError):
        repository.get("other@example.com", created["_id"])


def test_token_usage_and_model_limits_are_persisted(db_manager):
    repository = TokenRepo(db_manager)
    repository.save("person@example.com", 3, 5, "model-a", "openai", "CHAT")
    models = {
        "chat_models": [{"provider": "openai", "custom_name": "default"}],
        "providers": {
            "openai": {
                "default": {
                    "actual_model_name": "model-a",
                    "default_tokens_limit": 100,
                    "limit_reset_period": "day",
                }
            }
        },
    }

    limits = repository.get_limits_info_per_model("person@example.com", models)
    usage = repository.get_overall_tokens_usage_per_model("person@example.com", limits)

    assert limits["model-a"]["openai"]["tokens_limit"] == 100
    assert usage["model-a"]["openai"]["tot_tokens"] == 8
    assert usage["model-a"]["openai"]["tot_tokens_timeframe"] == 8
