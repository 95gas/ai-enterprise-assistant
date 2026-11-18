from pydantic import BaseModel, Field
from typing import Optional, Literal
from pathlib import Path
from typing import List


class ProcessingConfig(BaseModel):
    method: Literal["fast", "full"] = Field(default="full", description="Processing method to use.")
    images: bool = Field(default=True, description="Whether to extract images or not.")
    tables: bool = Field(default=True, description="Whether to extract tables or not.")

class MarkdownPage(BaseModel):
    filepath: Optional[str] = None
    s3_page: Optional[str] = Field(default=None, description="Name of the page document in S3.") 

class DocumentToProcess(BaseModel):
    filename: str = Field(description="Name the document is going to be stored with (sanitized).")
    visibility_groups: List[str] = Field(description="The groups that are going to have access to the document.")
    processing: Optional[ProcessingConfig] = Field(default=ProcessingConfig(), description="Processing settings.")
    content_type: str = Field(description="The MIME type of the document.")
    uploaded_by: str = Field(description="Name of who/what executed the upload.") 
    s3_bucket: Literal["users", "shared", "system"] = Field(description="Name of the bucket in S3 where the document is stored.") 
    s3_path: str = Field(description="Path in S3 where the document is stored (does not contain 'bucket' nor '/markdown/' folder).")
    og_last_modified: str = Field(description="Datetime generated string (DATE_FORMAT) when the original document was last modified.") 
    og_filename: str = Field(description="Filename of the original document.")
    og_uri: Optional[str | None] = Field(default=None, description="If present, redirects to the original document (e.g. link to SharePoint file).")
    source_filepath: Path = Field(description="Path to the original file.")

class DocumentToIngest(DocumentToProcess):
    markdown_pages: List[MarkdownPage]

class DocumentToDelete(BaseModel):
    filename: str = Field(description="Name the document is stored with (sanitized).")
    s3_bucket: Literal["users", "shared", "system"] = Field(description="Name of the bucket in S3 where the document is stored.") 
    s3_path: str = Field(description="Path in S3 where the document is stored (does not contain 'bucket' nor '/markdown/' folder).")
    og_filename: Optional[str] = Field(description="Filename of the original document.")
    source_filepath: Optional[Path | None] = Field(default=None, description="Path to the original file.")