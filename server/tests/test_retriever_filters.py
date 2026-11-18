from src.services.rag.filters import build_start_query


def test_start_query_binds_every_filter_as_a_parameter():
    query, parameters = build_start_query(
        groups=["research"],
        selected_documents=["report.pdf"],
        excluded_ids={"chunk-1"},
        selected_chunk_numbers=[2],
        selected_page_numbers=[3],
    )

    assert "$groups" in query
    assert "$selected_documents" in query
    assert "$excluded_ids" in query
    assert "$chunk_numbers" in query
    assert "$page_numbers" in query
    assert "IN page_numbers" not in query
    assert parameters == {
        "groups": ["research"],
        "selected_documents": ["report.pdf"],
        "excluded_ids": ["chunk-1"],
        "chunk_numbers": [2],
        "page_numbers": [3],
    }


def test_start_query_omits_unset_optional_filters():
    query, parameters = build_start_query(
        groups=["research"],
        selected_documents=None,
        excluded_ids=set(),
        selected_chunk_numbers=None,
        selected_page_numbers=None,
    )

    assert parameters == {"groups": ["research"]}
    assert "$selected_documents" not in query
    assert "$excluded_ids" not in query
    assert "$chunk_numbers" not in query
    assert "$page_numbers" not in query
