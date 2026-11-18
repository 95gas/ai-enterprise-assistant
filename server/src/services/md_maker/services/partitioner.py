from pathlib import Path
from typing import IO, Any, List, Union, Optional
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.openai import OpenAI
from src.common.document_processing.parser.table import TableHelper
from src.common.document_processing.services.llm_service import LLMService
from src.common.utils.validator import FileManager
from src.services.md_maker.services.utils.language_detector import PdfLanguageDetector
from src.services.md_maker.services.memory.manager import MemoryManager
from src.common.errors import FileProcessingError
from src.services.md_maker.services.parser.pdf import PDFHelper
from src.services.md_maker.services.parser.office import OfficeHelper
from src.services.md_maker.services.parser.generic import GeneralFileTypeHelper
from src.common.logging.logger import DebugLogger
from config.settings import settings

STORAGE_PATH = settings.STORAGE_PATH


class FilePartitioner:
    """
    Orchestrates the partitioning pipeline by validating, processing, and partitioning files.
    """
    def __init__(self,
                 main_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                 helper_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                 lang_detector: PdfLanguageDetector,
                 table_manager: TableHelper,
                 llm_doc_service: LLMService,
                 logger: DebugLogger = None) -> None:
        """
        Initializes the FilePartitioner with necessary components and logging.
        """
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initializing FilePartitioner...")
        self.file_validator = FileManager()
        self.memory_manager = MemoryManager()
        self.pdf_processor = PDFHelper(main_llm=main_llm,
                                       helper_llm=helper_llm,
                                       lang_detector=lang_detector,
                                       table_manager=table_manager,
                                       llm_doc_service=llm_doc_service,
                                       )
        self.office_processor = OfficeHelper(main_llm=main_llm,
                                             helper_llm=helper_llm,
                                             table_manager=table_manager,
                                             lang_detector=lang_detector,
                                             llm_doc_service=llm_doc_service,
                                             pdf_processor=self.pdf_processor
                                             )
        self.general_processor = GeneralFileTypeHelper(main_llm=main_llm,
                                                       helper_llm=helper_llm,
                                                       table_helper=table_manager,
                                                       llm_doc_service=llm_doc_service)
        self.cache_dir = STORAGE_PATH / ".." / "markdowns"
        self.logger.success("FilePartitioner ready.")

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)
        self.file_validator.config_log(user)
        self.memory_manager.config_log(user)
        self.pdf_processor.config_log(user)
        self.office_processor.config_log(user)
        self.general_processor.config_log(user)

    @DebugLogger.profile
    async def run_extraction(
            self,
            file_path: Path,
            filename: str,
            images: bool,
            tables: bool,
            file_content_type: Optional[str] = None,
    ) -> list[dict]:
        """
        Executes the text extraction pipeline for the given file.
        :param file_path: path of the file to process.
        :param filename: Name of the file being processed.
        :param file_content_type: MIME type of the file.
        :param folder: the folder where it is stored the file in s3 if owner is not given
        :param owner: id of the user owner of the file, is not provided will be considered a system file.
        :return: List of dictionaries containing the markdown pages of the file.
        """
        self.logger.info(f"Starting text extraction pipeline for file: {filename}")

        try:
            md_pages = await self.get_markdown(file_path,
                                               filename,
                                               images,
                                               tables,
                                               file_content_type
                                               )

            self.logger.success(f"Text extraction pipeline completed for file: {filename}")
            return md_pages
        except Exception as e:
            self.logger.error(f"Text extraction pipeline encountered an error for file: {filename}", exc_info=True)
            raise FileProcessingError(str(e), filename, "PartitioningError")

    async def get_markdown(self,
                     file_path: Union[str, Path],
                     filename: str,
                     images: Optional[bool] = None,
                     tables: Optional[bool] = None,
                     file_content_type: Optional[str] = None,
                     ) \
            -> List[dict]:
        """
        Convert the given file in markdown.
        :param file_path: path of the file to convert.
        :param filename: Name of the file being processed.
        :param file_content_type: MIME type of the file.
        :return: List of dictionaries containing the markdown pages of the file.
        """

        self.logger.info("Converting file to markdown...")

        # pdf file
        if file_content_type == "application/pdf":
            return await self.pdf_processor.get_markdown_pdf(full_path=str(file_path), filename=filename, images=images, tables=tables)

        # excel file
        elif (file_content_type == "application/vnd.ms-excel"
              or file_content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
            return await self.office_processor.get_markdown_excel(full_path=file_path, filename=filename)

        # word file
        elif (file_content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              or file_content_type == "application/msword"):
            return await self.office_processor.get_markdown_word_office(full_path=file_path, filename=filename, images=images, tables=tables)

        # csv file
        elif file_content_type == "text/csv":
            return await self.office_processor.get_markdown_csv(full_path=file_path, filename=filename)

        # ppt file
        elif (file_content_type == "application/vnd.ms-powerpoint"
              or file_content_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"):
            return await self.office_processor.get_markdown_ppt(full_path=file_path, filename=filename)

        # xml file
        elif file_content_type == "text/xml":
            return await self.office_processor.get_markdown_xml(full_path=file_path, filename=filename)

        # txt and markdown file
        elif file_content_type in ["text/plain", "application/octet-stream", "text/markdown"]:
            return await self.office_processor.get_markdown_text(full_path=file_path, filename=filename)

        # eml file
        elif file_content_type == "message/rfc822":
            return await self.general_processor.get_markdown_email(full_path=file_path, filename=filename)

        # image file
        elif file_content_type == "image/jpeg":
            return await self.general_processor.get_markdown_image(full_path=file_path, filename=filename)

        # audio file
        elif file_content_type in ["audio/mpeg", "video/mp4"]:
            return await self.general_processor.get_markdown_audio(full_path=file_path, filename=filename,
                                                                   file_content_type=file_content_type)

        else:
            self.logger.error(f"Type file '{file_content_type}' not supported!")
            raise NotImplementedError

    @staticmethod
    def _normalize_languages(languages: Optional[Union[str, List[str]]]) -> List[str]:
        """
        Normalizes the input languages into a list of strings.
        :param languages: Input languages as a string or list.
        :return: Normalized list of languages.
        """
        if isinstance(languages, str):
            return [languages]
        return languages or ["eng"]
