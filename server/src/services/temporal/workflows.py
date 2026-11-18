from datetime import timedelta
from typing import Any, Dict
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import os

    ACTIVITY_TIMEOUT = timedelta(
        seconds=int(os.getenv("TEMPORAL_ACTIVITY_TIMEOUT_SECONDS", "900"))
    )

DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=3,
)

@workflow.defn(name="document-ingestion-workflow")
class DocumentIngestionWorkflow:
    """
    Coordinates full end-to-end document ingestion:
    1. Extract Markdown from raw files (md_maker).
    2. Delete previous versions or failed artifacts if required.
    3. Chunk, embed, and index into Neo4j and S3 (md_ingestor).
    """

    @workflow.run
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user = payload.get("user", "system")
        docs_to_process = payload.get("docs_to_process", [])

        results: Dict[str, Any] = {
            "status": "COMPLETED",
            "extracted": [],
            "extraction_failed": [],
            "docs_succeeded": [],
            "docs_failed": [],
            "docs_deleted": [],
        }

        # Extract each configured mode separately; a single upload can mix fast and full processing.
        extraction_results = []
        default_mode = payload.get("mode", "full")
        for doc in docs_to_process:
            mode = (doc.get("processing") or {}).get("method", default_mode)
            if mode not in {"fast", "full"}:
                raise ValueError(f"Unsupported extraction mode: {mode}")

        for mode in ("fast", "full"):
            batch = [
                doc
                for doc in docs_to_process
                if (doc.get("processing") or {}).get("method", default_mode) == mode
            ]
            if not batch:
                continue
            extraction_results.append(
                await workflow.execute_activity(
                    "extract_document_activity",
                    {
                        "docs_to_process": batch,
                        "mode": mode,
                        "user": user,
                    },
                    start_to_close_timeout=ACTIVITY_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )
            )

        docs_to_ingest = [
            doc
            for result in extraction_results
            for doc in result.get("docs_to_ingest", [])
        ]
        docs_to_delete = [
            doc
            for result in extraction_results
            for doc in result.get("docs_to_delete", [])
        ]
        results["extracted"] = docs_to_ingest
        results["extraction_failed"] = docs_to_delete

        # Step 2: Handle deletions if specified
        if docs_to_delete:
            delete_result = await workflow.execute_activity(
                "delete_document_activity",
                {
                    "docs_to_delete": docs_to_delete,
                    "user": user,
                },
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            results["docs_deleted"].extend(delete_result.get("docs_succeeded", []))

        # Step 3: Ingest extracted markdown
        if docs_to_ingest:
            ingest_result = await workflow.execute_activity(
                "ingest_document_activity",
                {
                    "docs_to_ingest": docs_to_ingest,
                    "user": user,
                },
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            results["docs_succeeded"].extend(ingest_result.get("docs_succeeded", []))
            results["docs_failed"].extend(ingest_result.get("docs_failed", []))

        return results


@workflow.defn(name="document-batch-delete-workflow")
class DocumentBatchDeleteWorkflow:
    """Coordinates batch deletion of documents across Neo4j and S3."""

    @workflow.run
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user = payload.get("user", "system")
        docs_to_delete = payload.get("docs_to_delete", [])

        return await workflow.execute_activity(
            "delete_document_activity",
            {
                "docs_to_delete": docs_to_delete,
                "user": user,
            },
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY_POLICY,
        )


@workflow.defn(name="document-extraction-workflow")
class DocumentExtractionWorkflow:
    """Coordinates standalone document extraction."""

    @workflow.run
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user = payload.get("user", "system")
        mode = payload.get("mode", "full")
        docs_to_process = payload.get("docs_to_process", [])

        return await workflow.execute_activity(
            "extract_document_activity",
            {
                "docs_to_process": docs_to_process,
                "mode": mode,
                "user": user,
            },
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY_POLICY,
        )


ALL_WORKFLOWS = [
    DocumentIngestionWorkflow,
    DocumentBatchDeleteWorkflow,
    DocumentExtractionWorkflow,
]
