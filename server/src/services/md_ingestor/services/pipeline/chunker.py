from typing import Any, List, Dict, Optional, Union, Iterable, Tuple
import os
import re
import time
import json
import asyncio
from copy import deepcopy
from llama_index.core.schema import BaseNode
from pathlib import Path
from llama_index.core.node_parser import SentenceSplitter
import tiktoken
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.core.utils import get_tqdm_iterable
from src.common.models.tokenizer import TokenCounter
from src.common.document_processing.utils.utils import merge_lists_without_empty
from src.common.errors import FileProcessingError
from src.common.document_processing.parser.table import TableHelper
from src.common.logging.logger import DebugLogger
from config.settings import settings

MODELS_INFO_DICT = settings.models_info.model_dump()
NUM_WORKERS = settings.system.num_workers
STORAGE_PATH = settings.STORAGE_PATH
CHUNK_SIZE = settings.CHUNK_SIZE
CHUNK_OVERLAP = settings.CHUNK_OVERLAP
DATE_FORMAT = settings.DATE_FORMAT


class FileChunker:
    """
    A class to handle chunking of document elements while performing cleaning, filtering, and sentence completion.
    """

    def __init__(self,
                 main_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                 helper_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                 table_manager: TableHelper,
                 logger: DebugLogger = None,
                 ) -> None:
        """
        Initializes the FileChunker with default configurations.
        """
        self.chunk_size: int = CHUNK_SIZE
        self.chunk_overlap: int = CHUNK_OVERLAP
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initializing Chunker...")
        self.table_manager = table_manager
        self.main_llm = main_llm
        self.helper_llm = helper_llm
        self.debug_folder = STORAGE_PATH / ".." / "debug"

        self.tokenizer = TokenCounter(provider=MODELS_INFO_DICT["doc_model"]["provider"],
                                      model_name=MODELS_INFO_DICT["doc_model"]["custom_name"])
        self.logger.success("Chunker ready.")


    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)
        self.table_manager.config_log(user)


    @DebugLogger.profile
    async def run_chunker(self,
                          md_pages: List[Dict[str, Any]],
                          filename: str,
                          process_tables: bool) -> Optional[List[Dict[str, Any]]]:
        """
        Executes the chunking pipeline on the provided elements.
        :param filename: Name of the file being processed.
        :param content_type: Content type.
        :param folder: the folder where it is stored the file in s3 if owner is not given
        :param uploaded_by: id of the user who uploaded the file, is not provided will be considered a system file.
        :param private: boolean indicating if the document is private.
        :return: A list of chunked and cleaned elements, or None if an error occurs.
        """
        self.logger.info(f"Chunking pipeline started for file: {filename}")
        try:
            elements = self.get_elements(md_pages=md_pages, process_tables=process_tables)
            if process_tables:
                elements = await self.descr_tables(elements=elements, filename=filename, max_workers=NUM_WORKERS)
            elements = self.tokenize(filename, md_pages, elements)
            elements = self.text_merger(elements)
            self.logger.success(f"Chunking pipeline finished for file: {filename}")
            return elements

        except Exception as e:
            raise FileProcessingError(str(e), filename, "ChunkingError")


    def write_to_file(self,
                      nodes,
                      filename: str) -> None:
        """
        Utility function for writing to disk intermediate steps if needed
        """
        if isinstance(nodes[0], BaseNode):
            elements_dict = [
                {"text": node.text,
                 "metadata": node.metadata}
                for node in nodes
            ]
        else:
            elements_dict = nodes

        json_elements = json.dumps(elements_dict, indent=2)

        # Split the filename and extension
        filename, _ = os.path.splitext(filename)

        file_path_storage = Path(self.debug_folder, filename + "_chunks.json")

        with open(file_path_storage, "w", encoding="utf-8") as file:
            file.write(json_elements)


    @DebugLogger.profile
    async def descr_tables(self,
                     elements: List[Dict[str, Any]],
                     filename: str,
                     header_rows: int = 10,
                     max_token_table: int = 4096,
                     max_workers: int = 5) -> List[Dict[str, Any]]:
        """
        Orchestrates the parallel processing of tables.
        """
        self.logger.info(f"Describing and splitting table pipeline started...")

        # Setup paths
        cache_dir = str(STORAGE_PATH / ".." / "debug" / "tables_debug")
        os.makedirs(cache_dir, exist_ok=True)

        sub_table_elements = []
        text_elements, table_elements = self.separate_elements(elements)
        indexed_tables = list(enumerate(table_elements))

        # Execute Parallel
        tasks = [
            self.table_manager.process_single_table(
                table_data=t,
                filename=filename,
                cache_dir=cache_dir,
                header_rows=header_rows,
                max_token_table=max_token_table,
                main_llm=self.main_llm,
                helper_llm=self.helper_llm
            ) for t in indexed_tables
        ]

        if tasks:
            results = await asyncio.gather(*tasks)
            for res in results:
                sub_table_elements.extend(res)

        self.logger.success(f"Pipeline ended.")

        all_chunks = merge_lists_without_empty(text_elements, sub_table_elements)
        return self.renumber_chunks(all_chunks)

    def markdown_chunker(self, markdown_text: str, process_tables: bool) -> List[Dict[str, Union[int, str]]]:
        """Splits a Markdown text into enumerated chunks based on headings and tables."""
        if not markdown_text or not markdown_text.strip():
            return []

        # Normalize the text to handle different newline conventions
        text = markdown_text.strip().replace('\r\n', '\n')

        # Define regex patterns for headings and tables
        heading_pattern = re.compile(r'^#+ .+', re.MULTILINE)
        table_pattern = re.compile(r"(\|.*\|\s?)+", re.MULTILINE)

        # Find all start and end points for chunks
        # 1. Find all table spans and store them to identify them later
        table_spans = {match.span() for match in table_pattern.finditer(text)}

        # 2. Collect all split points: document start/end, headings, and tables
        split_points = {0, len(text)}
        for match in heading_pattern.finditer(text):
            split_points.add(match.start())
        for start, end in table_spans:
            split_points.add(start)
            split_points.add(end)

        # Sort the split points to process the text in order
        sorted_points = sorted(list(split_points))

        # Create chunks by slicing the text between split points
        chunks_with_type = []
        for i in range(len(sorted_points) - 1):
            start = sorted_points[i]
            end = sorted_points[i + 1]
            content = text[start:end]
            if content.strip():
                # Determine the type of the chunk
                # If the chunk's span matches a known table span and 'process_tables' is True, it's a 'table'
                chunk_type = 'table' if (start, end) in table_spans and process_tables else 'text'

                chunks_with_type.append({'type': chunk_type,
                                         'content': content})

        # Enumerate the final list of chunks and add the chunk number
        final_chunks = []
        for i, chunk_data in enumerate(chunks_with_type, 1):
            chunk_data['chunk_number'] = i
            final_chunks.append(chunk_data)
        return final_chunks

    @DebugLogger.profile
    def get_elements(self, md_pages: List[Dict[str, Any]], process_tables: bool) -> List[Dict[str, Any]]:
        """
        Separate table and text elements from the input list and normalize them.
        :param md_pages: List of dictionaries containing "page_content" and "metadata".
        :return: A list of processed and renumbered document chunks.
        """
        all_processed_elements = []

        # Progress bar for page processing
        md_pages_queue: Iterable[int] = get_tqdm_iterable(
            range(len(md_pages)), True, "Chunking markdown..."
        )

        for index in md_pages_queue:
            doc = md_pages[index]
            page_content = doc.get("page_content", "")
            # Deepcopy base metadata once per page to avoid mutating the original input
            base_metadata = deepcopy(doc.get("metadata", {}))

            # Extract elements (text/tables) from markdown
            elements = self.markdown_chunker(markdown_text=page_content, process_tables=process_tables)

            for element in elements:
                # Create element-specific metadata starting from the page metadata
                element_type = element.get("type")
                chunk_metadata = base_metadata.copy() 
                chunk_metadata.update({
                    "type": element_type,
                    "chunk_number": element.get("chunk_number")
                })

                if element_type == "text":
                    all_processed_elements.append({
                        "text": element["content"],
                        "metadata": chunk_metadata
                    })

                elif element_type == "table":
                    table_content = element["content"]
                    normalized_table = self.table_manager.normalize_consecutive_empty_rows(table_content)
                    chunk_metadata.update({
                        "markdown_table": normalized_table,
                        "table_tokens": self.tokenizer.count(normalized_table)
                    })

                    index_start, index_end = self.get_reference_index_from_md(
                        filename=chunk_metadata["filename"],
                        chunk_text=table_content,
                        md_pages=md_pages,
                        page=chunk_metadata["page_number"]
                    )
                    chunk_metadata["index_in_doc"] = [index_start, index_end]

                    all_processed_elements.append({
                        "text": "",  # To be filled by table description logic later
                        "metadata": chunk_metadata
                    })

        reordered_list = self.renumber_chunks(all_processed_elements)
        return reordered_list

    @staticmethod
    def renumber_chunks(chunk_list: List[Dict[str, Any]]) \
            -> List[Dict[str, Any]]:
        """Sorts a list of dictionaries based on 'page_number' and 'chunk_number'
        and then renumbers the 'chunk_number' sequentially."""
        # 1. Sort the list in-place first by 'page_number', then by 'chunk_number'.
        chunk_list.sort(key=lambda x: (x['metadata']['page_number'], x['metadata'].get('chunk_number', 1)))
        # 2. Renumber the chunks.
        for i, item in enumerate(chunk_list, 1):
            item['metadata']['chunk_number'] = i
        return chunk_list


    @staticmethod
    def separate_elements(chunks: List[Dict[str, Any]]) \
            -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Separate elements in text and table elements"""
        table_elements = []
        text_elements = []
        for element in chunks:
            if element["metadata"]['type'] == "text":
                text_elements.append(element)
            elif element["metadata"]['type'] == "table":
                table_elements.append(element)
        return text_elements, table_elements


    def get_reference_index_from_md(self, md_pages: List[Dict[str, Any]], chunk_text: str, filename: str, page: str) -> List[int]:
        """
        Get start and end index of a chunk inside a document page.
        """
        filename_source = filename.split('.')[0] + f'_page{page}.md'

        try:
            #TODO: manage index for excel files
            md_document = next((doc for doc in md_pages if doc["metadata"]["s3_page"] == filename_source), None)

            if not md_document:
                return [0, 0]

            file_text = md_document["page_content"].strip().lower()
            chunk_text = chunk_text.strip().lower()

            start = file_text.find(chunk_text)
            if start != -1:
                end = start + len(chunk_text)
                index = [start, end]
                return index
        except Exception as e:
            self.logger.error(f"Error getting index from MD: {e}", exc_info=True)
            self.logger.warning(f"Source could not be indexed in {filename_source}.")
        return [0, 0]


    def tokenize(self,
                 filename: str,
                 md_pages: List[Dict[str, Any]],
                 chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Splits the content of chunks into sentences using SentenceSplitter."""
        sentence_splitter = SentenceSplitter(chunk_size=self.chunk_size,
                                             tokenizer=tiktoken.encoding_for_model(self.main_llm.model).encode,
                                             chunk_overlap=self.chunk_overlap,
                                             include_prev_next_rel=False,
                                             include_metadata=False)

        new_chunks = []
        for chunk in chunks:
            raw_text = chunk.get("text", "").strip()
            if not isinstance(raw_text, str):
                raise FileProcessingError("Cannot split no text elements!", filename, "ChunkingError")

            # Split the content into sentences
            sentences = sentence_splitter.split_text(raw_text)

            # Create a new chunk for each sentence
            for sentence in sentences:
                new_metadata = deepcopy(chunk["metadata"])
                new_metadata["tokens"] = self.tokenizer.count(sentence)

                if new_metadata["type"] == "text":
                    start, end = self.get_reference_index_from_md(
                        md_pages=md_pages,
                        chunk_text=sentence,
                        filename=new_metadata["filename"],
                        page=new_metadata["page_number"]
                    )
                    new_metadata["index_in_doc"] = [start, end]

                new_chunks.append({
                    "text": sentence,
                    "metadata": new_metadata
                })      
                
        final_chunks = []
        for i, chunk_data in enumerate(new_chunks, 1):
            chunk_data["metadata"]['chunk_number'] = i
            final_chunks.append(chunk_data)

        return final_chunks


    def text_merger(self, chunks: List[Dict[str, Any]], token_limit: int = 256) -> List[Dict[str, Any]]:
        """Merges consecutive text-typed chunks if their combined token count is below a limit."""
        if not chunks:
            return []

        processed_chunks = []
        i = 0
        while i < len(chunks):
            current_chunk = deepcopy(chunks[i])

            # If the element is not a text chunk, just append it and move on.
            if current_chunk["metadata"]["type"] != "text":
                processed_chunks.append(current_chunk)
                i += 1
                continue

            # Look ahead to the next chunks to see if they can be merged.
            j = i + 1
            while j < len(chunks):
                next_chunk = deepcopy(chunks[j])
                merged_text = current_chunk["text"] + " " + next_chunk["text"]
                merged_text_tokens = self.tokenizer.count(merged_text)

                if (
                    next_chunk["metadata"]["type"] == "text"
                    and merged_text_tokens <= token_limit
                    and current_chunk["metadata"].get("page_number") == next_chunk["metadata"].get("page_number")
                ):
                    current_chunk["text"] = merged_text
                    current_chunk["metadata"]["tokens"] = deepcopy(merged_text_tokens)
                    j += 1
                else:
                    # Stop merging if the next chunk is not text or exceeds the token limit.
                    break

            processed_chunks.append(current_chunk)
            i = j

        # re-number all chunks in the processed list to ensure correct sequential order.
        for new_index, chunk in enumerate(processed_chunks, 1):
            chunk["metadata"]["chunk_number"] = new_index

        return processed_chunks