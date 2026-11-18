from pydantic import BaseModel, Field
from typing import List, Optional

from src.common.schema.documents import DocumentToIngest, DocumentToDelete
from config.settings import settings

STORAGE_MARKDOWN = settings.STORAGE_MARKDOWN


class InputData(BaseModel):
    docs_to_ingest: Optional[List[DocumentToIngest]] = Field(default=[], description="List of original documents' metadata to be ingested.")
    docs_to_delete: Optional[List[DocumentToDelete]] = Field(default=[], description="List of documents' metadata to be deleted.")

class OutputData(BaseModel):
    docs_succeeded: List[str] = Field(description="The list of 'og_filename' of successfully processed documents.")
    docs_failed: List[str] = Field(description="The list of 'og_filename' of failed documents.")
    processing_time: float
    timestamp: str