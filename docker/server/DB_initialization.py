from src.common.connectors.postgres.base import get_postgres_manager


if __name__ == "__main__":
    get_postgres_manager().initialize()
