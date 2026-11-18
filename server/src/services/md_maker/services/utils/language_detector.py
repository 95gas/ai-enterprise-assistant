import fitz
import random
from langcodes import *
from PIL import Image
import io
import os
import langcodes
from src.common.logging.logger import DebugLogger
from src.common.prompt_manager import PromptManager
from src.common.document_processing.services.llm_service import LLMService
from typing import Optional, Union
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.google_genai import GoogleGenAI
from src.services.md_maker.schemas.schemas import LanguageCode


class PdfLanguageDetector:

    def __init__(self,
                 vllm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                 llm_doc_service: LLMService,
                 logger: Optional[DebugLogger] = None,
                 ):
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initializing pdf lang detector...")
        self.llm_doc_service = llm_doc_service
        self.vllm = vllm
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, "..", "prompts")
        self.prompt_manager = PromptManager(prompts_folder=prompt_path)
        self.logger.success("Pdf lang detector ready.")

    def config_log(self, user: str):
        self.llm_doc_service.config_log(user)
        self.logger.set_user(user)

    @staticmethod
    def get_random_page_images(file_path: str,
                               pages_to_take: int = 3):
        try:
            doc = fitz.open(file_path)
            num_pages = len(doc)
            image_pages = []
            if num_pages > pages_to_take:
                random_indices = random.sample(range(1, num_pages - 1), num_pages - 2)
                pages_to_take = min(pages_to_take, len(random_indices))
            else:
                pages_to_take = 1
                random_indices = [0]
            for i in range(pages_to_take):
                page_index = random_indices[i]
                page = doc.load_page(page_index)
                pix_page_bytes = page.get_pixmap(dpi=200).pil_tobytes(format="JPEG")
                pil_image = Image.open(io.BytesIO(pix_page_bytes))
                image_pages.append(pil_image)
            doc.close()
            return image_pages
        except Exception as e:
            raise Exception("An error occurred while taking random pages! " + str(e))


    async def detect_pdf_language(self,
                            file_path: str):
        self.logger.info("Detecting pdf language...")
        images_page = self.get_random_page_images(file_path=file_path, pages_to_take=2)

        prompt = self.prompt_manager.get_prompt("LANG_DET")
        answer = await self.llm_doc_service.arun(
            prompt=prompt,
            client=self.vllm,
            image=images_page,
            max_retries=10,
            structured=True,
            output_cls=LanguageCode,
            label="DETECT_PDF_LANGUAGE",
        )

        lang_code = answer.main_language 
        if not Language.get(lang_code).is_valid():
            try:
                lang_code = str(langcodes.find(lang_code))
            except Exception:
                self.logger.warning("Could not detect pdf language!")
                raise Exception("Invalid lang code!")
        self.logger.success(f"Detected pdf language: {lang_code}")
        return lang_code