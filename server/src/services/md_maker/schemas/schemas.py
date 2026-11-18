from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path

from src.common.schema.documents import DocumentToProcess, DocumentToIngest, DocumentToDelete
from config.settings import settings

STORAGE_MARKDOWN = settings.STORAGE_MARKDOWN


class InputData(BaseModel):
    docs_to_process: List[DocumentToProcess] = Field(description="List of original documents' metadata to be processed.")
    md_output_path: Optional[str] = Field(default=STORAGE_MARKDOWN, description="Path where the Markdown version of the processed documents is going to be stored.")

class OutputData(BaseModel):
    docs_to_ingest: List[DocumentToIngest | None] = Field(description="The list of processed documents to be ingested.")
    docs_to_delete: List[DocumentToDelete | None] = Field(description="The list of 'source_path' of documents that failed to be processed.")
    processing_time: float
    timestamp: str

class SlideDescription(BaseModel):
    slide_description: str = Field(description="The detailed description of the presentation slide.")

class LanguageCode(BaseModel):
    main_language: str