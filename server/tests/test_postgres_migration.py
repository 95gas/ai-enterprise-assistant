from scripts.migrate_elasticsearch_to_postgres import record_for_table


def test_legacy_user_mapping_preserves_identity_and_uses_configured_defaults():
    record = record_for_table(
        "users",
        "person@example.com",
        {"email": "person@example.com", "groups": ["research"]},
        user_defaults={
            "tot_token_limit": 25000,
            "tot_limit_reset_period": "week",
            "expiring_date_trial": "2100/12/31 00:00:00",
        },
    )

    assert record["id"] == "person@example.com"
    assert record["groups"] == ["research"]
    assert record["tot_token_limit"] == 25000
    assert record["tot_limit_reset_period"] == "week"


def test_legacy_token_mapping_keeps_ids_and_usage_metadata():
    record = record_for_table(
        "token_usage",
        "legacy-token-id",
        {
            "timestamp": "2026/01/02 03:04:05",
            "user": "person@example.com",
            "input": 7,
            "output": 11,
            "model": "model-a",
            "provider": "openai",
            "label": "CHAT",
        },
    )

    assert record["id"] == "legacy-token-id"
    assert record["total"] == 18
    assert record["model"] == "model-a"
    assert record["timestamp"].year == 2026
