from typing import Dict, Optional, Literal, List
from pydantic import BaseModel, Field
from dataclasses import dataclass

class Source(BaseModel):
    type: Literal["docs", "web", "provided", "produced"] = Field(description="- 'docs' for retrieved sources from the Neo4J database; "
                                                                             "- 'web' for sources retrieved using DDGS; "
                                                                             "- 'provided' for sources provided in input by the user; "
                                                                             "- 'produced' for sources produced by the Assistant during the current interaction.")    
    filename: str = Field(description="The name of the document or the web page.")
    text: Optional[str] = Field(default=None, description="The content of the Source.")
    chunk_number: Optional[int] = Field(default=1, description="Number of the chunk in the document.")
    reference_index: Optional[List[int]] = Field(default=None, description="Only for 'docs': where the Source starts and ends inside the document page (e.g. [start_index, stop_index]).")
    s3_bucket: Optional[str] = Field(default=None, description="Only for 'docs': bucket where the document is stored in S3.")
    s3_path: Optional[str] = Field(default=None, description="Only for 'docs': path to the document folder in S3.")
    s3_page: Optional[str] = Field(default=None, description="Only for 'docs': document markdown page name in S3.")
    uri: Optional[str] = Field(default=None, description="Direct link to the original file.")
    reference_id: Optional[int] = Field(default=None, description="The id referenced by the Assistant in the chat.")
    id: str = Field(description="- 'docs': node.id_ retrieved from the Neo4j; "
                                "- 'web': hash of the href or body of the webpage.")
    class ConfigDict:
        exclude_none = True # When converting to dict or JSON, exclude fields that were not explicitly set

class Metadata(BaseModel):
    input_tokens: int
    output_tokens: int
    llm_model: str
    chat_name: str | None

class Response(BaseModel):
    response: str
    sources: List[Source]
    metadata: Metadata
    recorded_notes: Dict[str, str] | None


@dataclass(frozen=True)
class AgentProgress:
    id: str
    phase: Literal["start", "complete", "error"]
    tool_name: str
    label: str
    message: str
    language: Literal["en", "it", "zh"]
    duration_ms: Optional[int] = None