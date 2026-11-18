import os, io , re, time, random, concurrent.futures
from pathlib import Path
import PIL
import asyncio
from PIL import Image
import pandas as pd
from typing import List, Dict, Iterable, Sequence, Tuple, Union, Optional, Iterator
from pypdf import PdfReader, PdfWriter, PageObject
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.config.parser import ConfigParser
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.core.utils import get_tqdm_iterable
from src.common.logging.logger import DebugLogger
from src.common.document_processing.parser.table import TableHelper
from src.common.document_processing.services.llm_service import LLMService
from src.common.prompt_manager import PromptManager
from src.services.md_maker.services.utils.language_detector import PdfLanguageDetector
from config.settings import settings

STORAGE_PATH = settings.STORAGE_PATH
NUM_WORKERS = settings.system.num_workers


class PDFHelper:
    """Handles the different steps of the PDF doc processing for conversion to markdown."""

    def __init__(self,
                 main_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                 lang_detector: PdfLanguageDetector,
                 llm_doc_service: LLMService,
                 table_manager: TableHelper,
                 logger: Optional[DebugLogger] = None,
                 helper_llm: Optional[Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI]]=None
                 ):
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")

        self.logger.info("Initializing PDFHelper...")
        self.table_manager = table_manager
        self.main_llm = main_llm
        self.helper_llm = helper_llm
        self.lang_detector = lang_detector
        self.llm_doc_service = llm_doc_service
        self.image_describer = ImageHandler(self.llm_doc_service, self.main_llm, self.helper_llm)
        self.cache_dir = STORAGE_PATH / ".." / "debug" / "pdf_debug"
        self.tmp_doc_dir = STORAGE_PATH
        os.makedirs(self.tmp_doc_dir, exist_ok=True)
        os.makedirs( self.cache_dir, exist_ok=True)
        self.logger.success("PDFHelper ready")


    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)
        self.llm_doc_service.config_log(user)
        self.table_manager.config_log(user)
        self.lang_detector.config_log(user)
        self.image_describer.config_log(user)
        self.logger.set_class_name(self.__class__.__name__)
        self.logger.set_main_feature("DOC")


    @DebugLogger.profile
    async def get_markdown_pdf(
            self,
            full_path: str,
            filename: str,
            images: bool,
            tables: bool
    ) -> List[dict]:
        """
        Convert the pdf in markdown format.
        :param full_path: path of the pdf file
        :param filename: filename of the pdf file
        :return: the list of markdown pages of the input pdf
        """

        self.logger.info("Processing PDF file...")
        try:
            lang = await self.lang_detector.detect_pdf_language(full_path)
        except Exception as e:
            self.logger.warning(f"Could not detect the language of the pdf file: {e}")
            lang = None

        md_pages = await self.process_pdf(full_path=full_path,
                                          filename=filename,
                                          languages=lang,
                                          img=images,
                                          table=tables)

        return md_pages


    async def process_pdf(
            self,
            full_path: str,
            filename: str,
            img: bool,
            table: bool,
            languages: Optional[Union[str, List[str]]] = None
    ) -> List[dict]:
        """
        Convert a textual pdf in markdown format.
        :param full_path: path of the pdf file
        :param filename: filename of the pdf file
        :param languages: language of the pdf file
        :return: the list of markdown pages of the input pdf
        """

        self.logger.info("Run the pdf pipeline...")

        if not img:
            self.logger.info("Skipping images...")
        
        config = {
            "output_format": "markdown",
            "paginate_output": True,
            "disable_image_extraction": img,
            "languages": languages if isinstance(languages, Union[str, None]) else ",".join(languages),
        }
        doc_md, images = "", {}
        batches = self.create_batches_of_pages(full_path=full_path)
        for i, batch_str in enumerate(batches, 1):
            self.logger.info(f"Processing batch #{i}/{len(batches)} [{batch_str}]...")
            config["page_range"] = batch_str
        
            config_parser = ConfigParser(config)
            converter = PdfConverter(
                config=config_parser.generate_config_dict(),
                artifact_dict=create_model_dict(),
                processor_list=config_parser.get_processors(),
                renderer=config_parser.get_renderer(),
                llm_service=config_parser.get_llm_service()
            )
            rendered = converter(full_path)

            if img:
                batch_doc_md, _, batch_images = text_from_rendered(rendered)
                images.update(batch_images)
            else:
                batch_doc_md, _, _ = text_from_rendered(rendered)

            doc_md += batch_doc_md

        doc_page_md = re.split(r'\{\d+\}-{48}\n\n|\n\n\{\d+\}-{48}\n\n', doc_md)[1:]
        tot_pages = len(doc_page_md)
        pages_queue: Iterable[int] = get_tqdm_iterable(
            range(tot_pages), True, "Converting pages to markdown..."
        )
        results = []
        for index in pages_queue:
            page_content = doc_page_md[index]
            if page_content:

                # remove tables
                #if not table:
                #    page_content = self.remove_tables_from_md(page_content)

                # describe images
                if img: # TODO Else must put a placeholder instead
                    page_content = await self.image_describer.describe_imgs(md_page=page_content, lang=languages, images_lst=images)

                results.append(
                    {"page_content": page_content,
                     "metadata":
                        {"filename": filename,
                         "page_number": index + 1
                         }
                     }
                )
            else: # empty page
                self.logger.warning("Got empty page! Marker failed at extracting text!...")
                results.append(
                    {"page_content": "[empty_page]",
                     "metadata":
                        {"filename": filename,
                         "page_number": index + 1
                         }
                     }
                )

        return results


    def create_batches_of_pages(self, full_path: str, batch_size: Optional[int] = 200):
        with open(full_path, "rb") as f:
            total_pages = len(PdfReader(f).pages)
        batches = []
        for start in range(0, total_pages, batch_size):
            end = min(start + batch_size, total_pages-1)
            batches.append(f"{start}-{end}")
        self.logger.info(f"Processing {total_pages} pages in batches of size {batch_size} ({len(batches)} total batches).")
        return batches


    @staticmethod
    def get_table_elements_from_dict(details_results, page_number, image_dir):
        page_table_elements = details_results["pdf_info"][page_number]["tables"]
        tables_dict = {}
        for table in page_table_elements:
            html_table = table["blocks"][0]["lines"][0]["spans"][0]["html"]
            img_filename = table["blocks"][0]["lines"][0]["spans"][0]["image_path"]
            img_table_path = os.path.join(image_dir, img_filename)
            pil_image = Image.open(img_table_path)
            tables_dict[html_table] = pil_image
        return tables_dict


    @staticmethod
    def get_pdf_splits(pdf_pages: Sequence[PageObject],
                       split_size: int = 1
                       ) -> Iterator[Tuple[bytes, int]]:
        """
        Splits a PDF into smaller docs and returns each doc with its page offset.
        :param pdf_pages: Sequence of PDF pages.
        :param split_size: Number of pages per doc.
        :return: An iterator of file chunks and their page offsets.
        """
        offset = 0
        while offset < len(pdf_pages):
            pdf_buffer = PDFHelper._create_pdf_buffer(pdf_pages[offset:offset + split_size])
            yield pdf_buffer.read(), offset
            offset += split_size


    @staticmethod
    def _create_pdf_buffer(pages: Sequence[PageObject]) -> io.BytesIO:
        """
        Creates an in-memory PDF buffer from a list of pages.
        :param pages: List of PDF pages.
        :return: A BytesIO object containing the PDF content.
        """
        pdf_writer = PdfWriter()
        pdf_buffer = io.BytesIO()
        for page in pages:
            pdf_writer.add_page(page)
        pdf_writer.write(pdf_buffer)
        pdf_buffer.seek(0)
        return pdf_buffer

    @staticmethod
    def replace_image_descr_to_url(md_text: str) \
            -> str:
        # get all images urls i.e. ![](_page_11_Picture_0.jpeg)
        regex_url = r"(!\[(.*)\]\(.*\))"
        table_pattern = re.compile(
            regex_url,
            re.MULTILINE
        )

        # Find all occurrences
        matches = table_pattern.finditer(md_text)

        for match in matches:
            img_url = match.group(1)
            img_descr = match.group(2)
            if not img_descr:
                img_descr = "Error"
            md_text = md_text.replace(img_url, f"\n[image_description]{'{' + img_descr + '}'}\n")
        return md_text

    @staticmethod
    def remove_tables_from_md(md_text: str) -> str:
        """
        Removes tables from markdown text by replacing them with an empty string.
        """
        # Regex pattern to capture all Markdown tables
        regex = r"(\|.*\|\s?)+"

        # Replace all matches with an empty string
        cleaned_text = re.sub(regex, "", md_text, flags=re.MULTILINE)

        return cleaned_text.strip()


class ImageHandler:

    def __init__(self, llm_doc_service, main_llm, helper_llm):
        self.llm_doc_service = llm_doc_service
        self.main_llm = main_llm
        self.helper_llm = helper_llm
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, "..", "prompts")
        self.prompt_manager = PromptManager(prompts_folder=prompt_path)
        self.logger = DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the username
        """
        self.logger.set_user(user)

    def _get_images_name(self,
                         md_text: str) \
            -> Tuple[List[str], List[str]]:
        """
        Extracts html tables from markdown text.
        :param md_text: markdown text.
        :return: list of table string formatted in html.
        """
        # get all images urls i.e. ![](_page_11_Picture_0.jpeg)
        regex_url = r"(!\[.*\]\((.*)\))"
        url_img_pattern = re.compile(
            regex_url,
            re.MULTILINE
        )

        # Find all occurrences
        matches = url_img_pattern.finditer(md_text)
        img_urls = []
        img_filenames = []
        for match in matches:
            img_urls.append(match.group(1))
            img_filenames.append(match.group(2))
        _image_filenames, _img_urls = self.remove_images_urls(img_filenames, img_urls)
        return _image_filenames, _img_urls


    async def describe_imgs(self,
                      md_page: str,
                      lang: str,
                      images_lst: Optional[dict[str, PIL.Image.Image]] = None,
                      image_dir: Optional[Union[str, Path]] = ""):

        image_description_prompt = self.prompt_manager.get_prompt("IMG_DESCR")
        prompt = image_description_prompt.format(lang=lang)
        if images_lst:
            return await self._descr_images_from_list(md_page, images_lst, prompt, max_workers=NUM_WORKERS)

        elif image_dir:
            return await self._descr_images_from_dir(md_page, image_dir, prompt, max_workers=NUM_WORKERS)

        else:
            return md_page


    @staticmethod
    def remove_images_urls(
                    image_filenames: List[str],
                    img_urls: List[str])\
            -> Tuple[List[str], List[str]]:
        index_to_delete : List[int] = []
        for index, img in enumerate(image_filenames):
            if not img.startswith("_page"):
                index_to_delete.append(index)

        new_image_filenames = [image_filenames[index] for index in range(len(image_filenames)) if index not in index_to_delete]
        new_img_urls = [img_urls[index] for index in range(len(img_urls)) if index not in index_to_delete]

        return new_image_filenames, new_img_urls


    async def _generate_description(self, img_bytes: PIL.Image.Image, prompt: str, max_retries=3) -> str:
        """Core logic to call LLM for image description. Retries and backoff are handled by LLMCallManager."""
        return await self.llm_doc_service.adescr_img(
            prompt=prompt,
            main_llm=self.main_llm,
            helper_llm=self.helper_llm,
            image_pil=img_bytes,
            max_retries=max_retries,
        )

    async def _process_image_task(self,
                            target_url: str,
                            img_bytes: PIL.Image.Image,
                            prompt: str,
                            error_replacement: str) -> Tuple[str, str]:
        """
        Generic worker for processing a loaded PIL image.
        """
        try:
            img_descr = await self._generate_description(img_bytes, prompt)
            return target_url, f"\n[image_description]{{{img_descr}}}\n"
        except Exception as e:
            self.logger.error(f"Error describing image: {e}")
            return target_url, error_replacement

    async def _process_path_task(self,
                           target_url: str,
                           img_path: str,
                           prompt: str) -> Tuple[str, str]:
        """
        Worker specifically for loading from disk and processing.
        """
        try:
            with PIL.Image.open(img_path) as img_bytes:
                img_bytes.load()
                img_descr = await self._generate_description(img_bytes, prompt)
                return target_url, f"\n[image_description]{{{img_descr}}}\n"
        except Exception as e:
            self.logger.warning(f"Image '{img_path}' not found or error! {e}")
            return target_url, f"\n[image_description]{{ERROR}}\n"

    async def _descr_images_from_list(self,
                                      md_page: str,
                                      images_lst: Dict[str, PIL.Image.Image],
                                      prompt: str,
                                      max_workers: int = 5
                                      ) -> str:
        """
        Describe images from a list asynchronously
        """
        image_filenames, img_urls = self._get_images_name(md_page)

        if not image_filenames:
            return md_page

        tasks = []
        urls = []
        for index, img_name in enumerate(image_filenames):
            if img_name not in images_lst:
                continue

            img_bytes = images_lst[img_name]
            img_url = img_urls[index]

            tasks.append(self._process_image_task(img_url, img_bytes, prompt, ""))
            urls.append(img_url)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    self.logger.error(f"The task for {urls[i]} crashed!: {res}")
                else:
                    target_url, replacement_text = res
                    md_page = md_page.replace(target_url, replacement_text)

        return md_page

    async def _descr_images_from_dir(self,
                                     md_page: str,
                                     image_dir: Optional[Union[str, Path]],
                                     prompt: str,
                                     max_workers: int = 5
                                     ) -> str:
        """
        Describe images from directory asynchronously
        """
        image_filenames, img_urls = self._get_images_name(md_page)

        if not image_filenames or not image_dir:
            return md_page

        tasks = []
        urls = []
        for index, img_name_raw in enumerate(image_filenames):
            img_url = img_urls[index]

            image_filename = img_name_raw.split("/")[-1]
            image_path = os.path.join(str(image_dir), image_filename)

            tasks.append(self._process_path_task(img_url, image_path, prompt))
            urls.append(img_url)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    self.logger.error(f"The task for {urls[i]} crashed!: {res}")
                else:
                    target_url, replacement_text = res
                    md_page = md_page.replace(target_url, replacement_text)

        return md_page