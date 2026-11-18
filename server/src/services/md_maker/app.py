import os
import docx
from pptx import Presentation
import fitz  # PyMuPDF
import pytesseract
import uuid
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from pathvalidate import sanitize_filepath
from pdf2image import convert_from_path
from fastapi import Request, BackgroundTasks, HTTPException

from src.common.logging.logger import DebugLogger
from src.common.microservices.base import Microservice
from src.common.microservices.schemas import TaskSubmission, TaskStatusResponse
from src.common.schema.documents import DocumentToIngest, MarkdownPage, DocumentToDelete
from src.common.models.manager import ModelManager
from src.common.connectors.postgres.base import PostgresManager
from src.services.md_maker.services.partitioner import FilePartitioner
from src.services.md_maker.services.utils.language_detector import PdfLanguageDetector
from src.common.document_processing.parser.table import TableHelper
from src.common.document_processing.services.llm_service import LLMService
from src.common.errors import FileProcessingError
from src.services.md_maker.schemas.schemas import InputData, OutputData
from src.common.document_processing.utils.utils import convert_file_to_pdf
from src.services.authentication.jwt_manager import jwt_manager
from config.settings import settings

MODELS_INFO_DICT = settings.models_info.model_dump()
DATE_FORMAT = settings.DATE_FORMAT


class MdMaker(Microservice[InputData, OutputData]):
    """
    Microservice for Markdown Creation.
    Exposes two endpoints:
    - POST /execute/fast : For quick text extraction (OCR/PDF text)
    - POST /execute/full : For full pipeline extraction (LLM, Layout Analysis, Tables)
    """

    def __init__(self):
        super().__init__(input_model=InputData, output_model=OutputData)

        self.logger = DebugLogger(class_name=self.__class__.__name__,
                                  main_feature="DOC",
                                  user="undefined")

        self.logger.info("Initializing Text Extraction Engine...")
        self.db_manager = PostgresManager()
        self.db_manager.initialize()
        self.model_manager = ModelManager()

        # Load Models
        self.main_llm = self.model_manager.get_model(model_data=MODELS_INFO_DICT["doc_model"])
        self.helper_llm = self.model_manager.get_model(model_data=MODELS_INFO_DICT["helper_model"])
        self.helper_vllm = self.model_manager.get_model(model_data=MODELS_INFO_DICT["vision_model"])

        # Load Services
        llm_doc_service = LLMService(db_manager=self.db_manager)
        table_manager = TableHelper(llm_doc_service=llm_doc_service)
        lang_detector = PdfLanguageDetector(vllm=self.main_llm,
                                            llm_doc_service=llm_doc_service)

        # Initialize Partitioner
        self.partition_engine = FilePartitioner(
            main_llm=self.main_llm,
            helper_llm=self.helper_vllm,
            lang_detector=lang_detector,
            table_manager=table_manager,
            llm_doc_service=llm_doc_service,
        )
        self.logger.success("Dependencies initialized.")

    def _register_routes(self):
        """
        Override standard route registration to provide /execute/fast and /execute/full.
        """

        # --- FAST Endpoint ---
        async def execute_fast_wrapper(
                request: Request,
                background_tasks: BackgroundTasks,
                body: InputData
        ):
            return await self._handle_execution_dispatch(request, background_tasks, body, mode="fast")

        self.app.add_api_route(
            "/execute/fast",
            execute_fast_wrapper,
            methods=["POST"],
            response_model=TaskSubmission,
            status_code=202,
            name="Execute Fast Extraction"
        )

        # --- FULL Endpoint ---
        async def execute_full_wrapper(
                request: Request,
                background_tasks: BackgroundTasks,
                body: InputData
        ):
            return await self._handle_execution_dispatch(request, background_tasks, body, mode="full")

        self.app.add_api_route(
            "/execute/full",
            execute_full_wrapper,
            methods=["POST"],
            response_model=TaskSubmission,
            status_code=202,
            name="Execute Full Extraction"
        )

        # --- STATUS Endpoint ---
        async def status_wrapper(request: Request, task_id: str):
            return await self._handle_get_status(request, task_id)

        self.app.add_api_route(
            "/tasks/{task_id}",
            status_wrapper,
            methods=["GET"],
            response_model=TaskStatusResponse[OutputData],
            name="Get Task Status"
        )

    async def _handle_execution_dispatch(self, request: Request, background_tasks: BackgroundTasks, body: InputData,
                                         mode: str):
        """
        Custom execution handler that accepts a 'mode' (fast/full) and dispatches accordingly.
        """
        try:
            user = jwt_manager.authenticate_request(request)
            self.logger.set_user(user)

            task_id = str(uuid.uuid4())
            task_data = {
                "task_id": task_id,
                "status": self.STATUS_PENDING,
                "result": None,
                "error": None,
                "created_at": datetime.now(timezone.utc).strftime(DATE_FORMAT),
                "user": user,
                "mode": mode  # Store mode for debugging/tracking
            }

            await self._save_task(task_id=task_id, data=task_data)

            # Add specific dispatch handler to background tasks
            background_tasks.add_task(self._background_handler_dispatch, task_id, body, user, mode)
            self.logger.info(f"Task {task_id} ({mode}) queued for user {user}")

            return TaskSubmission(task_id=task_id,
                                  status=self.STATUS_PENDING,
                                  message=f"Task ({mode}) submitted successfully.")
        except HTTPException as e:
            raise e
        except Exception as e:
            self.logger.error(f"Init error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _background_handler_dispatch(self, task_id: str, input_data: InputData, user: str, mode: str):
        """
        Dispatches the background work to the correct processing method.
        """
        try:
            await self._update_task_status(task_id=task_id, status=self.STATUS_PROCESSING)

            if mode == "fast":
                result = await self.process_request_fast(input_data, user, task_id)
            elif mode == "full":
                result = await self.process_request_full(input_data, user, task_id)
            else:
                raise ValueError(f"Unknown mode: {mode}")

            await self._update_task_result(task_id=task_id, result=result, status=self.STATUS_COMPLETED)
            self.logger.success(f"Task {task_id} completed.")

        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {e}")
            await self._update_task_error(task_id=task_id, error_msg=str(e), status=self.STATUS_FAILED)

    async def process_request(self, input_data: InputData, user: str, task_id: str) -> OutputData:
        raise NotImplementedError("Use specific process_request_fast or process_request_full")

    # =================================================================================================
    # --- LOGIC: FAST EXTRACTION ---
    # =================================================================================================
    async def process_request_fast(self, input_data: InputData, user: str, task_id: str) -> OutputData:
        self.logger.info(f"Starting FAST execution of task '{task_id}' requested by user '{user}'.")
        start_time = datetime.now()
        docs_to_process = input_data.docs_to_process
        md_folder_output = Path(input_data.md_output_path)

        docs_success_list = []
        docs_failed_list = []

        if not docs_to_process:
            self.logger.error("No documents to process.")

        for doc in docs_to_process:
            try:
                tmp_file = doc.source_filepath

                md_pages = await self._process_file_fast(tmp_file, doc.filename)

                output_path = md_folder_output / sanitize_filepath(doc.filename.split('.')[0])
                md_list = [md_pages[i]["page_content"] for i in range(len(md_pages))]

                pages_filepath = self._save_markdown_files(output_path, md_list, doc.filename)
                self.logger.success(f"Markdown created for file '{doc.filename}'.")

                docs_success_list.append(DocumentToIngest(
                    **doc.model_dump(),
                    markdown_pages=[MarkdownPage(filepath=fp) for fp in pages_filepath],
                ))
            except Exception as e:
                self.logger.error(f"Error processing file '{doc.filename}': {e}")
                docs_failed_list.append(DocumentToDelete(
                    filename=doc.filename,
                    s3_bucket=doc.s3_bucket,
                    s3_path=doc.s3_path,
                    og_filename=doc.og_filename,
                    source_filepath=doc.source_filepath
                ))

        return OutputData(docs_to_ingest=docs_success_list,
                          docs_to_delete=docs_failed_list,
                          processing_time=(datetime.now() - start_time).total_seconds(),
                          timestamp=datetime.now(timezone.utc).strftime(DATE_FORMAT))


    async def _process_file_fast(self, file_path: str, filename: str) -> List[dict]:
        self.logger.info(f"Starting fast text extraction pipeline for file: {filename}")

        ext = os.path.splitext(filename)[1].lower()

        legacy_office = ['.doc', '.ppt']
        excel_extensions = ['.xlsx', '.xls']

        try:
            # --- 1. EXCEL (Use Pandas via OfficeHelper) ---
            if ext in excel_extensions:
                self.logger.info(f"Using Excel Fast Processor for {filename}")
                return await self.partition_engine.office_processor.get_markdown_excel(str(file_path), filename)

            # --- 2. MODERN OFFICE (.docx, .pptx) - DIRECT EXTRACTION ---
            elif ext == '.docx':
                self.logger.info(f"Using Direct DOCX Processor for {filename}")
                return await self._extract_text_docx(file_path, filename)

            elif ext == '.pptx':
                self.logger.info(f"Using Direct PPTX Processor for {filename}")
                return await self._extract_text_pptx(file_path, filename)

            # --- 3. LEGACY OFFICE (.doc, .ppt) - CONVERT TO PDF ---
            elif ext in legacy_office:
                self.logger.info(f"Converting legacy file {filename} to PDF for extraction...")
                with tempfile.TemporaryDirectory() as temp_dir:
                    convert_file_to_pdf(file_path, temp_dir)
                    pdf_files = [f for f in os.listdir(temp_dir) if f.lower().endswith('.pdf')]
                    if not pdf_files:
                        raise FileProcessingError("PDF conversion failed: No PDF created", filename, "ConversionError")
                    temp_pdf_path = os.path.join(temp_dir, pdf_files[0])
                    return await self._extract_text_fast(temp_pdf_path, filename)

            # --- 4. PDF (Direct Extraction) ---
            elif ext == '.pdf':
                return await self._extract_text_fast(str(file_path), filename)

            else:
                raise FileProcessingError(f"Unsupported file type for fast extraction: {ext}", filename,
                                          "ValidationError")

        except Exception as e:
            self.logger.error(f"Fast text extraction error: {filename}. Error: {str(e)}", exc_info=True)
            raise FileProcessingError(str(e), filename, "PartitioningError")

    @staticmethod
    async def _extract_text_docx(file_path: str, filename: str) -> List[dict]:
        """Extract text from DOCX directly using python-docx."""
        try:
            doc = docx.Document(file_path)
            # Combine paragraphs into one text block
            full_text = []
            for para in doc.paragraphs:
                if para.text.strip():
                    full_text.append(para.text)

            # Extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = [cell.text for cell in row.cells]
                    full_text.append(" | ".join(row_text))

            content = "\n\n".join(full_text)
            return [{"page_content": content, "metadata": {"filename": filename, "page_number": 1}}]
        except Exception as e:
            raise FileProcessingError(f"DOCX extraction failed: {str(e)}", filename, "ParsingError")

    @staticmethod
    async def _extract_text_pptx(file_path: str, filename: str) -> List[dict]:
        """Extract text from PPTX directly using python-pptx."""
        try:
            prs = Presentation(file_path)
            slides_content = []

            for i, slide in enumerate(prs.slides):
                slide_text = []

                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_text.append(shape.text)

                if slide_text:
                    content = "\n".join(slide_text)
                    slides_content.append({
                        "page_content": content,
                        "metadata": {"filename": filename, "page_number": i + 1}
                    })

            if not slides_content:
                # Return at least one empty page if no text found
                return [{"page_content": "", "metadata": {"filename": filename, "page_number": 1}}]

            return slides_content
        except Exception as e:
            raise FileProcessingError(f"PPTX extraction failed: {str(e)}", filename, "ParsingError")

    async def _extract_text_fast(self, pdf_path: str, filename: str) -> List[dict]: # {'page_content': str, 'metadata': {'filename': str, 'page_number': int}}
        """Extract text from a PDF efficiently, using OCR only if needed."""
        results = []
        ocr_needed = False

        # Step 1: Try direct extraction using PyMuPDF (fitz)
        try:
            with fitz.open(pdf_path) as doc:
                for index, page in enumerate(doc):
                    text = page.get_text("text")
                    if text.strip():
                        results.append({
                            "page_content": text,
                            "metadata": {"filename": filename, "page_number": index + 1}
                        })
                    else:
                        ocr_needed = True  # empty page found

                # If most pages have text, skip OCR and return direct results
                if not ocr_needed or (len(doc) > 0 and len(results) > (len(doc) * 0.8)):
                    return results
        except Exception as e:
            self.logger.warning(f"Direct extraction failed or incomplete for {filename}: {e}. Falling back to OCR.")

        # Step 2: OCR pipeline for image PDFs (fallback)
        self.logger.info(f"Performing OCR for {filename}...")
        ocr_results = []
        try:
            images = convert_from_path(pdf_path, dpi=300)
            with tempfile.TemporaryDirectory() as temp_dir:
                for i, image in enumerate(images):
                    # OCR logic using Pytesseract
                    ocr_text = pytesseract.image_to_string(image)
                    ocr_results.append({
                        "page_content": ocr_text,
                        "metadata": {"filename": filename, "page_number": i + 1}
                    })
        except Exception as e:
            self.logger.error(f"OCR failed for {filename}: {e}")
            raise e

        return ocr_results

    # =================================================================================================
    # --- LOGIC: FULL EXTRACTION ---
    # =================================================================================================
    async def process_request_full(self, input_data: InputData, user: str, task_id: str) -> OutputData:
        self.logger.info(f"Starting FULL execution of task '{task_id}' requested by user '{user}'.")
        start_time = datetime.now()
        docs_to_process = input_data.docs_to_process
        md_folder_output = Path(input_data.md_output_path)

        docs_success_list = []
        docs_failed_list = []

        if not docs_to_process:
            self.logger.error("No documents to process.")

        for doc in docs_to_process:
            try:
                tmp_file = doc.source_filepath

                md_pages = await self.partition_engine.run_extraction(
                    tmp_file,
                    doc.filename,
                    doc.processing.images,
                    doc.processing.tables,
                    doc.content_type
                ) # PDF -> {'page_content': str, 'metadata': {'filename': str, 'page_number': int}}

                output_path = md_folder_output / sanitize_filepath(doc.filename.split('.')[0])
                md_list = [md_pages[i]["page_content"] for i in range(len(md_pages))]

                pages_filepath = self._save_markdown_files(output_path, md_list, doc.filename)

                self.logger.success(f"Markdown created for file '{doc.filename}'.")

                docs_success_list.append(DocumentToIngest(
                    **doc.model_dump(),
                    markdown_pages=[MarkdownPage(filepath=fp) for fp in pages_filepath],
                ))
            except Exception as e:
                self.logger.error(f"Error processing file '{doc.filename}': {e}")
                docs_failed_list.append(DocumentToDelete(
                    filename=doc.filename,
                    s3_bucket=doc.s3_bucket,
                    s3_path=doc.s3_path,
                    og_filename=doc.og_filename,
                    source_filepath=doc.source_filepath
                ))

        return OutputData(docs_to_ingest=docs_success_list,
                          docs_to_delete=docs_failed_list,
                          processing_time=(datetime.now() - start_time).total_seconds(),
                          timestamp=datetime.now(timezone.utc).strftime(DATE_FORMAT))

    # =================================================================================================
    # --- UTILS ---
    # =================================================================================================
    @staticmethod
    def _save_markdown_files(output_path: Path, markdowns: list, base_name: str) -> list[str]:
        """
        Saves a list of markdown pages strings into a specific directory.
        """
        folder = output_path
        folder.mkdir(parents=True, exist_ok=True)

        results = []
        for i, content in enumerate(markdowns):
            file_name = sanitize_filepath(f"{base_name.split('.')[0]}_page{i+1}.md")
            file_path = folder / file_name
            file_path.write_text(content, encoding='utf-8')
            results.append(str(file_path))

        return results


microservice = MdMaker()
app = microservice.app