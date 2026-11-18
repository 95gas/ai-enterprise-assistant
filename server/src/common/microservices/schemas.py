from typing import Optional
from pydantic import BaseModel, Field
from typing import Optional, Generic, TypeVar


InputT = TypeVar('InputT', bound=BaseModel)
OutputT = TypeVar('OutputT', bound=BaseModel)


class TaskSubmission(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel, Generic[OutputT]):
    task_id: str
    status: str
    created_at: str
    result: Optional[OutputT] = None
    error: Optional[str] = None