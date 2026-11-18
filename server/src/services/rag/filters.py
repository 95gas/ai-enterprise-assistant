from typing import Dict, List, Optional, Set, Tuple


def build_start_query(
    groups: Optional[List[str]],
    selected_documents: Optional[List[str]],
    excluded_ids: Set[str],
    selected_chunk_numbers: Optional[List[int]],
    selected_page_numbers: Optional[List[int]],
) -> Tuple[str, Dict[str, List]]:
    """Build the parameterized visibility and selection filter for Neo4j."""
    parameters: Dict[str, List] = {"groups": groups}
    query = (
        "MATCH (node) "
        "WHERE ANY(visibility_groups IN node.visibility_groups "
        "WHERE visibility_groups IN $groups) "
    )
    filters = (
        ("selected_documents", selected_documents,
         "AND ANY(filename IN node.filename WHERE filename IN $selected_documents) "),
        ("excluded_ids", sorted(excluded_ids),
         "AND ANY(id IN node.id WHERE NOT id IN $excluded_ids) "),
        ("chunk_numbers", selected_chunk_numbers,
         "AND ANY(chunk_number IN node.chunk_number WHERE chunk_number IN $chunk_numbers) "),
        ("page_numbers", selected_page_numbers,
         "AND ANY(page_number IN node.page_number WHERE page_number IN $page_numbers) "),
    )
    for parameter, values, clause in filters:
        if values:
            parameters[parameter] = values
            query += clause
    return query, parameters
