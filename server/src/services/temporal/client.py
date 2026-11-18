import os
import uuid
from typing import Any, Dict, Optional

from src.services.chat.temporal import temporal_enabled
from src.services.temporal.workflows import (
    DocumentIngestionWorkflow,
    DocumentBatchDeleteWorkflow,
    DocumentExtractionWorkflow,
)


class TemporalMicroserviceClient:
    """Client to trigger and manage microservice orchestration workflows on Temporal."""

    def __init__(
        self,
        target: Optional[str] = None,
        namespace: Optional[str] = None,
        task_queue: Optional[str] = None,
    ) -> None:
        self.target = target or os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
        self.namespace = namespace or os.getenv("TEMPORAL_NAMESPACE", "default")
        self.task_queue = task_queue or os.getenv("TEMPORAL_MICROSERVICES_TASK_QUEUE", "ask-microservices")

    async def _get_client(self):
        if not temporal_enabled():
            raise RuntimeError("Temporal orchestration is disabled. Set TEMPORAL_ENABLED=true to enable.")
        try:
            from temporalio.client import Client
        except ImportError as exc:
            raise RuntimeError("The Temporal Python SDK is required.") from exc

        return await Client.connect(self.target, namespace=self.namespace)

    async def execute_document_ingestion(
        self,
        docs_to_process: list,
        user: str = "system",
        mode: str = "full",
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs the full ingestion workflow and waits for completion."""
        client = await self._get_client()
        wf_id = workflow_id or f"ingest-{uuid.uuid4()}"
        payload = {
            "docs_to_process": docs_to_process,
            "user": user,
            "mode": mode,
        }

        return await client.execute_workflow(
            DocumentIngestionWorkflow.run,
            payload,
            id=wf_id,
            task_queue=self.task_queue,
        )

    async def execute_batch_delete(
        self,
        docs_to_delete: list,
        user: str = "system",
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs the batch delete workflow and waits for completion."""
        client = await self._get_client()
        wf_id = workflow_id or f"delete-{uuid.uuid4()}"
        payload = {
            "docs_to_delete": docs_to_delete,
            "user": user,
        }

        return await client.execute_workflow(
            DocumentBatchDeleteWorkflow.run,
            payload,
            id=wf_id,
            task_queue=self.task_queue,
        )

    async def execute_extraction(
        self,
        docs_to_process: list,
        user: str = "system",
        mode: str = "full",
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs extraction workflow and waits for completion."""
        client = await self._get_client()
        wf_id = workflow_id or f"extract-{uuid.uuid4()}"
        payload = {
            "docs_to_process": docs_to_process,
            "user": user,
            "mode": mode,
        }

        return await client.execute_workflow(
            DocumentExtractionWorkflow.run,
            payload,
            id=wf_id,
            task_queue=self.task_queue,
        )
