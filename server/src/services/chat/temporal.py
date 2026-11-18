import os
from datetime import timedelta
from typing import Any, Awaitable, Callable, Dict


def temporal_enabled() -> bool:
    return os.getenv("TEMPORAL_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _agent_loop_workflow_type():
    from temporalio import workflow
    from temporalio.common import RetryPolicy

    @workflow.defn(name="ask-agent-loop")
    class AgentLoopWorkflow:
        @workflow.run
        async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            max_steps = min(max(int(payload.get("max_steps", 1)), 1), 20)
            state = payload.get("state", {})
            task = payload.get("task", "")
            for step_index in range(max_steps):
                result = await workflow.execute_activity(
                    "execute_agent_step",
                    {
                        "task": task,
                        "state": state,
                        "step_index": step_index,
                    },
                    start_to_close_timeout=timedelta(
                        seconds=int(os.getenv("TEMPORAL_ACTIVITY_TIMEOUT_SECONDS", "300"))
                    ),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                if not isinstance(result, dict):
                    raise TypeError("Agent step activities must return an object.")
                state = result.get("state", state)
                if result.get("done") is True:
                    return result
                task = result.get("next_task", task)
            raise RuntimeError("The durable agent loop reached its step limit.")

    return AgentLoopWorkflow


class TemporalAgentLoopClient:
    """Starts durable agent loops on a configured Temporal task queue."""

    def __init__(
        self,
        target: str = None,
        namespace: str = None,
        task_queue: str = None,
    ) -> None:
        self.target = target or os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
        self.namespace = namespace or os.getenv("TEMPORAL_NAMESPACE", "default")
        self.task_queue = task_queue or os.getenv("TEMPORAL_TASK_QUEUE", "ask-agent-loops")

    async def start(self, payload: Dict[str, Any], workflow_id: str):
        if not temporal_enabled():
            raise RuntimeError("Temporal orchestration is disabled.")
        if not workflow_id:
            raise ValueError("A stable workflow_id is required.")

        try:
            from temporalio.client import Client
        except ImportError as exc:
            raise RuntimeError("The Temporal Python SDK is required.") from exc

        client = await Client.connect(self.target, namespace=self.namespace)
        return await client.start_workflow(
            _agent_loop_workflow_type().run,
            payload,
            id=workflow_id,
            task_queue=self.task_queue,
        )


async def run_agent_loop_worker(
    execute_agent_step: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
) -> None:
    """Run a worker with an injected, independently testable agent-step activity."""
    try:
        from temporalio import activity
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError as exc:
        raise RuntimeError("The Temporal Python SDK is required.") from exc

    @activity.defn(name="execute_agent_step")
    async def execute_step(payload: Dict[str, Any]) -> Dict[str, Any]:
        return await execute_agent_step(payload)

    client = await Client.connect(
        os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
    )
    worker = Worker(
        client,
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "ask-agent-loops"),
        workflows=[_agent_loop_workflow_type()],
        activities=[execute_step],
    )
    await worker.run()
