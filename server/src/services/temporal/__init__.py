from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.services.temporal.client import TemporalMicroserviceClient
    from src.services.temporal.worker import run_microservices_worker

__all__ = ["TemporalMicroserviceClient", "run_microservices_worker"]


def __getattr__(name: str) -> Any:
    if name == "TemporalMicroserviceClient":
        from src.services.temporal.client import TemporalMicroserviceClient
        return TemporalMicroserviceClient
    if name == "run_microservices_worker":
        from src.services.temporal.worker import run_microservices_worker
        return run_microservices_worker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")