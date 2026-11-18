import os
import asyncio
from typing import Any, Dict
import httpx

from src.services.authentication.jwt_manager import jwt_manager
from config.settings import settings

MD_MAKER_URL = os.getenv("MD_MAKER_URL", "http://localhost:8005")
MD_INGESTOR_URL = os.getenv("MD_INGESTOR_URL", "http://localhost:8006")
TASK_TTL = settings.microservices.task_ttl


async def _poll_task_status(target_url: str, endpoint: str, payload: Dict[str, Any], user: str) -> Dict[str, Any]:
    """Helper to submit a task to a microservice and poll until complete with Temporal heartbeats."""
    token = jwt_manager.generate_jwt(user=user, issuer="temporal_orchestrator")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=TASK_TTL) as client:
        # Submit
        submission_url = f"{target_url}{endpoint}"
        submit_resp = await client.post(submission_url, json=payload, headers=headers)
        if submit_resp.status_code != 202:
            raise RuntimeError(f"Microservice submission failed ({submit_resp.status_code}): {submit_resp.text}")

        task_data = submit_resp.json()
        task_id = task_data.get("task_id")
        if not task_id:
            raise RuntimeError(f"Missing task_id in microservice response: {task_data}")

        # Poll
        try:
            from temporalio import activity
            in_temporal = True
        except ImportError:
            in_temporal = False

        while True:
            await asyncio.sleep(3)
            if in_temporal:
                activity.heartbeat(f"Polling task {task_id}")

            try:
                status_resp = await client.get(f"{target_url}/tasks/{task_id}", headers=headers)
            except httpx.RequestError:
                continue

            if status_resp.status_code != 200:
                continue

            data = status_resp.json()
            status = data.get("status")

            if status == "COMPLETED":
                return data.get("result", {})
            elif status == "FAILED":
                err = data.get("error", "Unknown remote microservice error")
                raise RuntimeError(f"Remote microservice task failed: {err}")


async def extract_document_activity(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Temporal activity for extracting Markdown from documents via md_maker."""
    user = payload.get("user", "system")
    mode = payload.get("mode", "full")
    docs_to_process = payload.get("docs_to_process", [])
    sub_payload = {"docs_to_process": docs_to_process}
    endpoint = f"/execute/{mode}"

    return await _poll_task_status(
        target_url=MD_MAKER_URL,
        endpoint=endpoint,
        payload=sub_payload,
        user=user,
    )


async def ingest_document_activity(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Temporal activity for chunking, embedding, and indexing documents via md_ingestor."""
    user = payload.get("user", "system")
    docs_to_ingest = payload.get("docs_to_ingest", [])
    sub_payload = {"docs_to_ingest": docs_to_ingest}

    return await _poll_task_status(
        target_url=MD_INGESTOR_URL,
        endpoint="/execute",
        payload=sub_payload,
        user=user,
    )


async def delete_document_activity(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Temporal activity for deleting document chunks and files via md_ingestor."""
    user = payload.get("user", "system")
    docs_to_delete = payload.get("docs_to_delete", [])
    sub_payload = {"docs_to_delete": docs_to_delete}

    return await _poll_task_status(
        target_url=MD_INGESTOR_URL,
        endpoint="/execute/batch_delete",
        payload=sub_payload,
        user=user,
    )
