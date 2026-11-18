import os
import io
import pandas as pd
import csv
import base64
import tqdm
from multiprocessing.pool import ThreadPool
from pathlib import Path
from pathvalidate import sanitize_filepath
from typing import IO, Any, List, Sequence, Iterable, Union, Optional, Iterator
from pdf2image import convert_from_path
from src.common.logging.logger import DebugLogger
from src.common.document_processing.parser.table import TableHelper
from src.common.document_processing.services.llm_service import LLMService
from src.common.document_processing.utils.utils import delete_dir_content, write_md_file, convert_file_to_pdf
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama
from xlsx2html import xlsx2html
from xls2xlsx import XLS2XLSX
from src.common.prompt_manager import PromptManager
from src.services.md_maker.services.utils.language_detector import PdfLanguageDetector
from src.services.md_maker.services.parser.pdf import PDFHelper
from src.services.md_maker.schemas.schemas import SlideDescription
from config.settings import settings

STORAGE_PATH = settings.STORAGE_PATH
NUM_WORKERS = settings.system.num_workers


class OfficeHelper:
    """Handles the different steps of the Office family doc (xlsx, docx, csv and xml) processing for conversion to markdown."""

    def __init__(self,
                 main_llm: Union[OpenAI, AzureOpenAI, Ollama],
                 helper_llm: Union[OpenAI, AzureOpenAI, Ollama],
                 lang_detector: PdfLanguageDetector,
                 pdf_processor: PDFHelper,
                 table_manager: TableHelper,
                 llm_doc_service: LLMService,
                 logger: Optional[DebugLogger] = None,
                 max_retry: int = 5,
                 ):
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initializing office helper...")
        self.cache_dir =  STORAGE_PATH / "docs_tmp"
        self.deployment_azure = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        self.max_retry = max_retry
        self.counter = 0
        self.main_llm = main_llm
        self.helper_llm = helper_llm
        self.llm_doc_service = llm_doc_service
        self.slide_describer = SlideDescriber(self.llm_doc_service)
        self.table_manager = table_manager
        self.pdf_processor = pdf_processor
        self.lang_detector = lang_detector
        self.logger.success("Office helper ready.")

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the username
        """
        self.logger.set_user(user)
        self.llm_doc_service.config_log(user)
        self.lang_detector.config_log(user)
        self.slide_describer.config_log(user)
        self.logger.set_class_name(self.__class__.__name__)
        self.logger.set_main_feature("DOC")

    @DebugLogger.profile
    async def get_markdown_excel(
            self,
            full_path: str,
            filename: str,
    ) -> List[dict]:
        """
        Convert an Excel file in Markdown format.
        :param full_path: path of the file
        :param filename: filename of the file
        :return: the list of markdown sheets of the input file
        """

        self.logger.info(f"Processing excel file '{filename}'")

        cache_dir = str(self.cache_dir / "excel")
        os.makedirs(cache_dir, exist_ok=True)
        try:
            # convert xls to xlsx
            _filename, file_extension = os.path.splitext(full_path)
            if file_extension == ".xls":
                x2x = XLS2XLSX(str(full_path))
                _filename = os.path.basename(filename) + ".xlsx"
                full_path = cache_dir + "/" + _filename
                x2x.to_xlsx(full_path)
            sheets_dict = pd.read_excel(full_path, engine="openpyxl", sheet_name=None, index_col=0, header=None,
                                        keep_default_na=False)
            results = []
            for _sheet_name, df in sheets_dict.items():
                sheet_name = sanitize_filepath(_sheet_name)
                self.logger.info(f"Processing excel sheet '{sheet_name}'")

                buf = io.BytesIO()
                df.to_excel(buf, header=False)
                buf.seek(0)

                _filename = cache_dir + f'/{sheet_name}.html'
                _filename = sanitize_filepath(_filename)
                xlsx2html(buf, _filename)

                html = pd.read_html(_filename, index_col=0, header=0, keep_default_na=False)

                if html: # skip empty sheets
                    md = html[0].to_markdown(tablefmt="github")
                    md = self.table_manager.normalize_pandas_header(md, html[0])

                    results.append(
                        {"page_content": md,
                         "metadata":
                             {"filename": filename,
                              "page_number": sheet_name
                              }
                         }
                    )
            delete_dir_content(cache_dir)
            return results

        except Exception as e:
            self.logger.error(f"Failed to get markdown: {str(e)}")
            delete_dir_content(cache_dir)
            raise e


    @DebugLogger.profile
    async def get_markdown_csv(
            self,
            full_path: str,
            filename: str,
    ) -> list[dict]:
        """
        Convert a csv file in Markdown format.
        :param full_path: path of the file
        :param filename: filename of the file
        :return: the list of markdown pages of the input file
        """

        self.logger.info(f"CSV processor started for '{filename}'")

        # detect delimiter
        with open(full_path, 'r', encoding="utf8") as csvfile:
            dialect = csv.Sniffer().sniff(csvfile.readline())
            sep = dialect.delimiter

        df = pd.read_csv(full_path, sep=sep, on_bad_lines='skip')
        df = df.replace('\n', '<br>', regex=True)
        md = df.to_markdown(tablefmt="github", index=False)
        return [
            {"page_content": md,
             "metadata":
                 {"filename": filename}
             }
        ]

    @DebugLogger.profile
    async def get_markdown_word_office(
            self,
            full_path: str,
            filename: str,
            images: bool,
            tables: bool
    ) -> List[dict]:
        """
        Convert a docx file in Markdown format.
        :param full_path: path of the file
        :param filename: filename of the file
        :return: the list of markdown pages of the input file
        """

        self.logger.info(f"WordOffice processor started for '{filename}'")
        tmp_folder = self.cache_dir / "word"
        os.makedirs(tmp_folder, exist_ok=True)
        try:
            # convert docs to pdf
            convert_file_to_pdf(full_path, str(tmp_folder))
        except FileNotFoundError:
            self.logger.error(f"Failed to find file: '{full_path}'", exc_info=True)
            delete_dir_content(tmp_folder)
            raise FileNotFoundError("Cannot run 'soffice'")
        except Exception as e:
            self.logger.error(f"Failed to use 'soffice' command: {str(e)}", exc_info=True)
            delete_dir_content(tmp_folder)
            raise e
        try:
            _filename = filename.split(".")[0] + ".pdf"
            path_pdf = tmp_folder / _filename
            return await self.pdf_processor.get_markdown_pdf(full_path=str(path_pdf),
                                                       filename=filename,
                                                       images=images,
                                                       tables=tables)
        except Exception as e:
            self.logger.error(f"Failed to get markdown: {str(e)}", exc_info=True)
            delete_dir_content(tmp_folder)
            raise e


    @DebugLogger.profile
    async def get_markdown_ppt(self,
                         full_path: str,
                         filename: str = "",
                         ) -> List[dict]:
        """
        Convert a ppt file in Markdown format.
        :param full_path: path of the file
        :param filename: filename of the file
        :return: the list of markdown slides of the input file
        """

        self.logger.info(f"PPTOffice processor started for '{filename}'")

        cache_dir = self.cache_dir / "ppt"
        os.makedirs(cache_dir, exist_ok=True)

        cache_dir_img = cache_dir / "img"
        os.makedirs(cache_dir_img, exist_ok=True)

        try:
            # convert ppt to PDF
            self.logger.info("Converting PPT file to PDF...")
            convert_file_to_pdf(full_path, str(cache_dir))

            # convert PDF to images
            self.logger.info("Converting PDF file to images...")
            _text, _ = os.path.splitext(filename)
            _filename = _text + ".pdf"
            path_pdf = cache_dir / _filename
            images = convert_from_path(path_pdf)

            # save an image using extension
            for num, img in enumerate(images):
                file_to_save = cache_dir_img / f"{num}.jpg"
                img.save(file_to_save)
            self.logger.success("PDF file converted into images successfully.")

            # Describe slides
            results = await self.slide_describer.describe_imgs_from_dir(cache_dir_img, self.main_llm, self.helper_llm)

            out = [
                {"page_content": result["text"],
                 "metadata":
                         {"filename": filename,
                          "page_number": index + 1
                          #"image_slide" :  result["image"]
                          }
                     } for index, result in enumerate(results) ]

            delete_dir_content(cache_dir)
            return out

        except Exception as e:
            self.logger.error(f"Failed to convert PPT file to PDF: {str(e)}")
            delete_dir_content(cache_dir)
            raise e


    @DebugLogger.profile
    async def get_markdown_xml(self,
                         full_path: str,
                         filename: str = "",
                         ) -> list[dict]:
        """
        Convert a xml file in Markdown format.
        :param full_path: path of the file
        :param filename: filename of the file
        :return: the list of markdown pages of the input file
        """
        self.logger.info(f"Xml processor started for '{filename}'")
        df = pd.read_xml(Path(full_path))
        df = df.replace('\n', '<br>', regex=True)
        md = df.to_markdown(tablefmt="github", index=False)
        return [
            {"page_content": md,
             "metadata":
                 {"filename": filename}
             }
        ]


    @DebugLogger.profile
    async def get_markdown_text(self,
                          full_path: str,
                          filename: str = "",
                          ) -> list[dict]:
        """
        Convert a text file to Markdown format.
        :param full_path: path of the file
        :param filename: filename of the file
        :return: the list of markdown pages of the input file
        """
        self.logger.info(f"Txt/md processor started for '{filename}'")
        with open(full_path, "r", encoding="utf8") as f:
            content = f.read()
        return [
            {"page_content": content,
             "metadata":
                 {"filename": filename}
             }
        ]


class SlideDescriber:

    def __init__(self, llm_doc_service):
        self.logger = DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.llm_doc_service = llm_doc_service
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, "..", "prompts")
        self.prompt_manager = PromptManager(prompts_folder= prompt_path)


    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the username
        """
        self.logger.set_user(user)

    @staticmethod
    def encode_image(image_path) -> str:
        """
        Encode the image in base64.
        :param image_path: The path of the image.
        :return: The base64 encoding of the image
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    @staticmethod
    def _process_single_slide(img_filename, dir_path, prompt, llm_doc_service, main_llm, helper_llm):
        """
        Worker function to process a single slide image.
        """
        image_path = os.path.join(dir_path, img_filename)
        base64_image = SlideDescriber.encode_image(image_path)

        descr = llm_doc_service.descr_img(
            prompt=prompt,
            main_llm=main_llm,
            helper_llm=helper_llm,
            image_path=image_path,
            label="SLIDE_DESCRIPTION",
            output_cls = SlideDescription
        )

        return {"text": descr, "image": base64_image}

    async def describe_imgs_from_dir(self,
                               dir_path: str,
                               main_llm: Union[OpenAI, AzureOpenAI, Ollama],
                               helper_llm: Optional[Union[OpenAI, AzureOpenAI, Ollama]] = None
                               ) -> List[dict]:
        """
        Describe all the images contained in a folder using multiprocessing.
        :param dir_path: The folder where the images are.
        :param main_llm: The main llm to use
        :param helper_llm: The llm to use in case of rate limit error
        :return: A list containing the text description of each image in the folder.
        """
        self.logger.info("Describing images...")

        prompt = self.prompt_manager.get_prompt("SLIDE_DESCR").format()

        # Get list of images
        imgs = os.listdir(dir_path)

        # Prepare arguments for the workers
        tasks = [
            (filename, dir_path, prompt, self.llm_doc_service, main_llm, helper_llm)
            for filename in imgs
        ]

        with ThreadPool(processes=NUM_WORKERS) as pool:
            result_iterator = pool.starmap(self._process_single_slide, tasks)
            results = list(tqdm.tqdm(result_iterator, total=len(imgs), desc="Describing slides..."))

        return results