import os
from typing import Optional

from src.services.chat.temporal import temporal_enabled
from src.services.temporal.activities import (
    extract_document_activity,
    ingest_document_activity,
    delete_document_activity,
)
from src.services.temporal.workflows import ALL_WORKFLOWS


async def run_microservices_worker(
    target: Optional[str] = None,
    namespace: Optional[str] = None,
    task_queue: Optional[str] = None,
) -> None:
    """Run the microservices Temporal worker executing extraction, ingestion, and deletion activities."""
    if not temporal_enabled():
        raise RuntimeError("Temporal orchestration is disabled.")

    try:
        from temporalio import activity
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError as exc:
        raise RuntimeError("The Temporal Python SDK is required.") from exc

    server_target = target or os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    client_namespace = namespace or os.getenv("TEMPORAL_NAMESPACE", "default")
    queue = task_queue or os.getenv("TEMPORAL_MICROSERVICES_TASK_QUEUE", "ask-microservices")

    client = await Client.connect(server_target, namespace=client_namespace)

    @activity.defn(name="extract_document_activity")
    async def extract_activity(payload: dict) -> dict:
        return await extract_document_activity(payload)

    @activity.defn(name="ingest_document_activity")
    async def ingest_activity(payload: dict) -> dict:
        return await ingest_document_activity(payload)

    @activity.defn(name="delete_document_activity")
    async def delete_activity(payload: dict) -> dict:
        return await delete_document_activity(payload)

    worker = Worker(
        client,
        task_queue=queue,
        workflows=ALL_WORKFLOWS,
        activities=[extract_activity, ingest_activity, delete_activity],
    )

    print(f"Starting Temporal microservices worker on queue '{queue}' connecting to '{server_target}'...")
    await worker.run()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_microservices_worker())
