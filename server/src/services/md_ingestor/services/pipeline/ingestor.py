import os, json, re
from pathlib import Path
from flask import Response
from datetime import datetime, timezone
from pathvalidate import sanitize_filepath
from typing import List, Any, Dict, Union, Optional, Callable
from llama_index.core.schema import MetadataMode, BaseNode, TextNode

from src.common.schema.documents import DocumentToIngest, DocumentToDelete, ProcessingConfig
from src.services.md_ingestor.services.pipeline.chunker import FileChunker
from src.services.md_ingestor.services.pipeline.embedder import Embedder
from src.common.document_processing.services.llm_service import LLMService
# from src.core.knowledge.graph.entities import MetadataExtraction
from src.common.document_processing.utils.storage import StorageManager
from src.common.connectors.neo4j.manager import Neo4jDBManager
from src.common.document_processing.parser.table import TableHelper
from src.common.connectors.postgres.base import PostgresManager
from src.knowledge.vector.manager import VectorManager
from src.knowledge.graph.manager import GraphManager
from src.common.connectors.s3.manager import S3DBManager
from src.common.utils.validator import FileManager
from src.common.models.manager import ModelManager
from src.common.errors import FileProcessingError
from src.common.logging.logger import DebugLogger
from config.settings import settings

MODELS_INFO_DICT = settings.models_info.model_dump()
NUM_WORKERS = settings.system.num_workers
STORAGE_PATH = settings.STORAGE_PATH
DATE_FORMAT = settings.DATE_FORMAT
DEVICE = settings.system.device
THEME = settings.theme


class DocIngestor:
    """
    Encapsulates the document ingestion process, including partitioning, embedding, and storage.
    """

    def __init__(
            self,
            model_manager: ModelManager,
            device: Optional[str] = DEVICE,
            vector_manager: Optional[VectorManager] = None,
            graph_manager: Optional[GraphManager] = None,
            db_manager: Optional[PostgresManager] = None,
            db_manager_neo4j: Optional[Neo4jDBManager] = None,
            db_manager_s3: Optional[S3DBManager] = None,
            storage_manager: Optional[StorageManager] = None,
            file_manager: Optional[FileManager] = None,
            chunker: Optional[FileChunker] = None,
            embedder: Optional[Embedder] = None,
            logger: Optional[DebugLogger] = None,
            output_path: Optional[Path] = None,
    ) -> None:
        """
        Initialize the DocumentIngestor.
        :param model_manager: Instance of modelManager for handling the llms.
        :param vector_manager: Instance of VectorManager for handling vector storage.
        :param graph_manager: Instance of GraphManager for handling graph storage.
        :param storage_manager: Optional custom StorageManager instance.
        :param file_manager: Optional custom FileManager instance.
        :param post_processor: Optional custom PostProcessor instance.
        :param chunker: Optional custom FileChunker instance.
        :param embedder: Optional custom Embedder instance.
        :param device: Device used for embedding operations.
        :param logger: Optional custom logger.
        """
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initializing ingestor pipeline...")

        self.db_manager_neo4j = db_manager_neo4j
        self.db_manager_s3 = db_manager_s3
        self.vector_manager = vector_manager
        self.graph_manager = graph_manager
        self.storage_path = Path(STORAGE_PATH)
        self.main_llm = model_manager.get_model(model_data=MODELS_INFO_DICT["doc_model"])
        self.logger.info("Loading LLMs helpers...")
        self.helper_llm = model_manager.get_model(model_data=MODELS_INFO_DICT["helper_model"])
        self.helper_vllm = model_manager.get_model(model_data=MODELS_INFO_DICT["vision_model"])
        self.logger.success("LLMs helpers ready.")

        # Initialize dependencies with defaults if not provided
        self.storage_manager = storage_manager or StorageManager(storage_path=self.storage_path)
        self.file_manager = file_manager or FileManager()

        llm_doc_service = LLMService(db_manager=db_manager)
        table_manager = TableHelper(llm_doc_service=llm_doc_service)

        self.chunker = chunker or FileChunker(
            main_llm=self.main_llm,
            helper_llm=self.helper_llm,
            table_manager=table_manager
        )
        self.embedder = embedder or Embedder(
            embedder_model=model_manager.get_model(model_data=MODELS_INFO_DICT["embedder_model"]),
            provider=MODELS_INFO_DICT["embedder_model"]["provider"],
            device=device,
            db_manager=db_manager
        )
        self.storage_manager.setup_storage_directories()
        self.output_path = output_path
        self.logger.success("Ingestor pipeline initialized successfully.")

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)
        self.chunker.config_log(user)
        self.embedder.config_log(user)
        self.storage_manager.config_log(user)
        self.file_manager.config_log(user)

    def change_storage_path(self, path: str) -> None:
        """
        Change the storage path for the ingestor.
        :param path: New storage path.
        """
        self.storage_path = Path(path)
        self.logger.info(f"Storage path updated to: {path}")

    def allowed_file(self, filename: str) -> bool:
        """
        Check if the file extension is allowed.
        :param filename: File name to check.
        :return: True if the file is allowed, otherwise False.
        """
        return self.file_manager.allowed_file(filename)

    def _upload_markdown_to_s3(self, item: DocumentToIngest) -> None:
        """
        Uploads markdown pages associated with a document to S3 and updates their S3 paths.

        :param item: The Document object containing markdown pages to upload.
        """
        pages_payload = []
        for p in item.markdown_pages:
            if os.path.exists(p.filepath):
                with open(p.filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                pages_payload.append({
                    "page_name": os.path.basename(p.filepath),
                    "page_content": content,
                    "metadata": {}
                })
            else:
                self.logger.warning(f"File {p.filepath} not found for S3 upload.")
                raise FileNotFoundError(str(p.filepath))

        try:
            s3_results = self.db_manager_s3.upload_markdowns(
                filename=item.filename,
                markdowns=pages_payload,
                s3_bucket=item.s3_bucket,
                s3_path=item.s3_path
            )
            # Update S3 references in the MarkdownPage objects
            for i, res in enumerate(s3_results):
                item.markdown_pages[i].s3_page = res.get("metadata", {}).get("s3_page")
            self.logger.success(f"Successfully uploaded {len(pages_payload)} pages to S3 for document: {item.og_filename}")
            return 
        except Exception as e:
            self.logger.error(f"Failed to upload document {item.filename} pages to S3: {e}")
            raise e

    async def ingest_batch(self,
                           docs_to_ingest: List[DocumentToIngest],
                           progress_callback: Optional[Callable[[str], None]] = None,
                           progress_filename: Optional[Callable[[str], None]] = None) -> List[Dict[str, DocumentToIngest | DocumentToDelete | Response]]:
        """
        Process multiple files with associated metadata.
        :param files_with_metadata: List of DocumentToIngest.
        :param progress_callback: Optional callback to report progress updates.
        :param progress_filename: Optional callback to report current file processing.
        :return: List of responses for each file processed.
        """
        responses = []
        for file in docs_to_ingest:
            # Initialize curr_file so it exists if an exception occurs before the page loop
            try:
                self._upload_markdown_to_s3(file)
                await self._ingest_document(file=file,
                                            progress_callback=progress_callback,
                                            progress_filename=progress_filename)
                responses.append({
                    "file": file,
                    "response": Response(status=200)
                })
            except Exception as e:
                self.logger.error(f"Error processing file '{file.og_filename}': {e}")
                responses.append({
                    "file": DocumentToDelete(
                        filename=file.filename, 
                        s3_bucket=file.s3_bucket, 
                        s3_path=file.s3_path, 
                        og_filename=file.og_filename, 
                        source_filepath=file.source_filepath,
                    ),
                    "response": Response(status=500)
                })
        return responses

    async def _ingest_document(self,
                               file: DocumentToIngest,
                               progress_callback: Optional[Callable[[str], None]] = None,
                               progress_filename: Optional[Callable[[str], None]] = None) -> None | Exception:
        self.logger.info(f"Processing file {file.og_filename}...")
        upload_datetime = datetime.now().strftime(DATE_FORMAT)
        try:
            for page in file.markdown_pages:
                if not Path(page.filepath).exists():
                    raise FileNotFoundError(f"File not found: {page.filepath}")

                await self._run_ingest(file=file,
                                       page_path=Path(page.filepath),
                                       s3_page=page.s3_page,
                                       upload_datetime=upload_datetime,
                                       progress_callback=progress_callback,
                                       progress_filename=progress_filename)
            return
        except Exception as e:
            self.logger.error(f"Error processing file '{file.filename}': {e}")
            raise e

    @DebugLogger.profile
    async def _run_ingest(self,
                          file: DocumentToIngest,
                          page_path: Path,
                          upload_datetime: str,
                          s3_page: str,
                          progress_callback: Optional[Callable[[str], None]] = None,
                          progress_filename: Optional[Callable[[str], None]] = None) -> None | Exception:
        """
        Run the ingestion pipeline for a file.
        :param file_path: Path to the file to process.
        :param filename: Name of the file to process.
        :param groups: Policies to associate with the file.
        :param content_type: Content type of the file to process.
        :param progress_callback: Optional callback to report progress updates.
        :param progress_filename: Optional callback to report current file processing.
        :return: Flask Response indicating success or failure.
        """
        self.logger.info(f"Starting ingestion pipeline for page: {os.path.basename(page_path)}")
        if progress_callback:
            progress_callback(f"Starting processing for '{file.filename}'...")
        try:
            elements = await self._process_file(page_path=page_path,
                                                upload_datetime=upload_datetime,
                                                filename=file.filename,
                                                visibility_groups=file.visibility_groups,
                                                content_type=file.content_type,
                                                uploaded_by=file.uploaded_by,
                                                og_last_modified=file.og_last_modified,
                                                og_filename=file.og_filename,
                                                og_uri=file.og_uri,
                                                s3_bucket=file.s3_bucket,
                                                s3_path=file.s3_path,
                                                s3_page=s3_page,
                                                processing=file.processing,
                                                progress_callback=progress_callback)

            if not self.vector_manager:
                self._handle_json_output(elements=elements, filename=file.filename)
            else:
                # Insert nodes into vector storage
                if progress_callback:
                    progress_callback(f"Indexing {file.filename} in vector store...")
                self._handle_vector_storage(elements=elements, filename=file.filename)
                if progress_filename:
                    progress_filename(f"{file.filename}")
                # Insert nodes into graph storage
                # self._handle_graph_storage(elements=elements, s3_bucket=file.s3_bucket, s3_path=file.s3_path, filename=file.filename)
            return 
        except Exception as e:
            self.logger.error(f"Error processing file: {file.filename}: {e}")
            raise e

    async def delete_documents_from_kb(self, documents: List[DocumentToDelete]) -> Dict[str, List[str]]:
        """
        Deletes a batch of documents from S3 and Neo4j.
        :param documents: List of Document models
        :return: Dictionary with lists of successfully deleted and failed filenames.
        """
        self.logger.info(f"Starting batch deletion of {len(documents)} documents.")
        success_list = []
        failed_list = []

        for doc in documents:
            filename = doc.filename
            s3_path = doc.s3_path
            s3_bucket = doc.s3_bucket

            if not filename:
                self.logger.warning("Skipping deletion item with no filename.")
                continue

            try:
                failure = False
                # Delete from S3
                try:
                    self.db_manager_s3.delete_markdowns(s3_bucket=s3_bucket, s3_path=s3_path, filename=filename)
                    self.logger.info(f"Deleted '{filename}' from S3.")
                except Exception as e:
                    self.logger.warning(f"Could not delete '{filename}' from S3: {e}")
                    failure = True

                # Delete from Neo4j
                try:
                    self.db_manager_neo4j.delete_document(s3_bucket=s3_bucket, s3_path=s3_path, filename=filename)
                    self.logger.info(f"Deleted '{filename}' from Neo4j.")
                except Exception as e:
                    self.logger.warning(f"Could not delete '{filename}' from Neo4j: {e}")
                    raise e
                
                if doc.source_filepath and doc.source_filepath.exists():
                    os.remove(doc.source_filepath)

                if failure:
                    failed_list.append(filename)
                else:
                    success_list.append(filename)
            except Exception as e:
                self.logger.error(f"Error deleting document from databases. Document: {str(doc.model_dump())} {str(e)}")
                failed_list.append(filename)

        self.logger.info(f"Batch deletion complete. Success: {len(success_list)}, Failed: {len(failed_list)}")
        return {"deleted": success_list, "failed": failed_list}

    def _handle_json_output(self, elements: List[Dict[str, Any]], filename: str) -> None:
        """
        Saves the processed elements directly to a JSON file.
        """
        self.logger.info(f"Vector manager not configured. Saving processed elements to JSON for '{filename}'.")
        self.write_to_file(nodes=elements, output_path=self.output_path, filename=filename)
        self.logger.success(f"Successfully saved elements for '{filename}' to {self.output_path / filename}.json")

    def _handle_graph_storage(self, elements: List[Dict[str, Any]], s3_bucket: str, s3_path: str, filename: str) -> None:
        """
        Converts elements to nodes and stores them in the graph database.

        :param elements: The list of processed elements from the document.
        :param filename: The name of the source document, used as an identifier.
        """
        try:
            self.logger.info(f"Storing nodes for '{filename}' in the graph storage...")
            nodes_graph_store = self.elements_to_nodes(elements=elements, filename=filename, embedding=False)

            # Insert the nodes into the graph manager
            self.graph_manager.insert_nodes(nodes_graph_store, filename)
            self.logger.success(f"Successfully stored nodes for '{filename}' in the graph storage.")

        except Exception as e:
            self.logger.error(f"Failed to store '{filename}' in graph storage. Attempting rollback from vector DB.")
            self.db_manager_neo4j.delete_document(s3_bucket=s3_bucket, s3_path=s3_path, filename=filename)
            raise e

    def _handle_vector_storage(self, elements: List[Dict[str, Any]], filename: str) -> None:
        """
        Converts elements to nodes and inserts them into the vector store.
        """
        # Convert elements to nodes suitable for the vector store
        nodes = self.elements_to_nodes(elements=elements, filename=filename, embedding=True)

        # Save nodes to a file for debugging purposes
        debug_path = self.output_path or self.storage_path.parent / "debug" / "chunks"
        self.write_to_file(nodes=nodes, output_path=debug_path, filename=filename)

        # Insert the processed nodes into the vector database
        self.logger.info(f"Inserting {len(nodes)} nodes for '{filename}' into vector store...")
        self.vector_manager.insert_nodes(nodes, filename)
        self.logger.success(f"Successfully stored nodes for '{filename}' in vector store.")

    async def _process_file(self,
                            page_path: Path,
                            filename: str,
                            visibility_groups: List[str],
                            content_type: str,
                            upload_datetime: str,
                            og_last_modified: str,
                            og_filename: str,
                            s3_bucket: str,
                            s3_path: str,
                            s3_page: str,
                            uploaded_by: str,
                            og_uri: str | None,
                            processing: ProcessingConfig,
                            progress_callback: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
        """
        Processes a single file through partitioning, cleaning, embedding, and visibility_groups addition.
        :param file_path: Path to the file.
        :param filename: Name of the file.
        :param visibility_groups: List of visibility_groups to apply.
        :param content_type: the mimetype of the file.
        :param progress_callback: Optional callback for progress updates.
        :return: Processed elements.
        """
        try:
            if progress_callback:
                progress_callback(f"Extracting content from \"{filename}\"...")

            with open(page_path, "r", encoding="utf8") as f:
                content = f.read()

            page_number = 1
            match = re.search(r'_page(\d+)\.md', s3_page)
            if match:
                page_number = int(match.group(1))
            else:
                raise RuntimeError(f"Page number not detected: {str(page_path)}")

            input_doc = [
                {"page_content": content,
                 "metadata":
                     {"page_number": page_number,
                      "filename": filename,
                      "visibility_groups": visibility_groups,
                      "filetype": content_type,
                      "upload_datetime": upload_datetime,
                      "uploaded_by": uploaded_by,
                      "s3_bucket": s3_bucket,
                      "s3_path": s3_path,
                      "s3_page": s3_page,
                      "og_last_modified": og_last_modified,
                      "og_filename": og_filename,
                      "og_uri": og_uri,
                      "processing": str(processing.model_dump(mode='json'))
            }}]
            if progress_callback:
                progress_callback(f"Chunking content for \"{og_filename}\"...")
            elements = await self.chunker.run_chunker(md_pages=input_doc, filename=og_filename, process_tables=processing.tables)
            if progress_callback:
                progress_callback(f"Generating embeddings for \"{og_filename}\"...")
            elements = await self.embedder.run_embedder(elements, filename=og_filename, max_workers=NUM_WORKERS)
            if progress_callback:
                progress_callback(f"Finalizing processing for \"{og_filename}\"...")
            self.logger.info("Cleaning up temporary files...")

            return elements

        except FileProcessingError as e:
            self.logger.error(
                f"An error of type {e.error_type} occurred during processing file {e.filename}. The cause of exception is the following: {e.message}",
                exc_info=True)
            raise e

    @staticmethod
    def write_to_file(nodes: Union[List[BaseNode], List[Dict[str, Any]]],
                      output_path: Path,
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

        # create folder if it doesn't exist
        if not os.path.exists(output_path):
            os.makedirs(output_path)

        file_path_storage = Path(output_path, filename + "_chunks.json")

        with open(file_path_storage, "w", encoding="utf-8") as file:
            file.write(json_elements)

    def elements_to_nodes(self,
                          elements: List[Dict[str, Any]],
                          filename: str,
                          embedding: bool
                          ) -> List[TextNode]:
        """
        Convert elements into a list of TextNode objects.
        :param elements: List of elements to convert.
        :param filename: the filename to which the elements belong to.
        :param embedding: Whether to include embeddings in the nodes.
        :return: List of TextNode objects.
        """
        try:
            return self._elements_to_nodes(elements=elements, filename=filename, embedding=embedding)
        except FileProcessingError as e:
            self.logger.error(
                f"An error of type {e.error_type} occurred during processing file {e.filename}. The cause of exception is the following: {e.message}",
                exc_info=True)
            raise

    @staticmethod
    def _elements_to_nodes(elements: List[Dict[str, Any]], filename: str, embedding: bool) -> List[TextNode]:
        """
        Helper for converting elements into a list of TextNode objects.
        :param elements: List of elements to convert.
        :param embedding: Whether to include embeddings in the nodes.
        :return: List of TextNode objects.
        """
        try:
            nodes = [
                TextNode(
                    text=item["text"],
                    embedding=item["embeddings"] if embedding else None,
                    metadata=item["metadata"],
                    metadata_seperator="\n",
                    metadata_template="{key}: {value}",
                    text_template="{metadata_str}\nContent:{content}",
                )
                for item in elements
            ]
            return nodes
        except Exception as e:
            raise FileProcessingError(str(e), filename, "TextNodesConvertionError")

    def check_what_llm_embedder_see(self, node: BaseNode) -> None:
        """
        Logs what metadata are visible to the LLM and embedder for a given node.
        :param node: Sample node for inspection.
        """
        self.logger.debug(f"LLM sees: \n{node.get_content(metadata_mode=MetadataMode.LLM)}")
        self.logger.debug(f"Embedding model sees: \n{node.get_content(metadata_mode=MetadataMode.EMBED)}")
