import PIL
import base64
from io import BytesIO
from typing import Annotated, List, Union, Optional, Type
from llama_index.core.base.llms.types import ChatMessage, ImageBlock
from pydantic import BaseModel
from PIL import Image

from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.google_genai import GoogleGenAI
from src.common.logging.logger import DebugLogger
from src.common.connectors.postgres.base import PostgresManager
from src.common.connectors.postgres.token import TokenRepo
from src.common.llm.manager import LLMCallManager
from src.common.document_processing.schemas.schemas import ImageDescription


class LLMService:

    def __init__(self,
                 logger: Optional[DebugLogger] = None,
                 db_manager: Optional[PostgresManager] = None):
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initializing LLMDocService...")
        self.token_repo = TokenRepo(db_manager=db_manager)
        self.logger.success("LLMDocService ready.")

    def config_log(self, user: str):
        self.logger.set_user(user)
        self.token_repo.logger.set_user(user)

    def image_to_base64(self, image: PIL.Image.Image, ext: str):
        if image.mode == "RGBA":
            image = image.convert("RGB")
        image_bytes = BytesIO()
        image.save(image_bytes, format=ext)
        return base64.b64encode(image_bytes.getvalue()).decode("utf-8")

    def prepare_images(
            self, images: Union[Image.Image, List[Image.Image]], client: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI]
    ) -> List[ImageBlock]:
        if isinstance(images, Image.Image):
            images = [images]
        if isinstance(client, Ollama):
            return [ImageBlock(image=self.image_to_base64(image=img, ext="jpeg")) for img in images]
        return [ImageBlock(image=self.image_to_base64(image=img, ext="webp"), detail="high") for img in images]

    # -------------------------------------------------------------------------
    # ASYNC METHODS
    # -------------------------------------------------------------------------

    async def arun(
            self,
            prompt: str,
            client: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
            image: Union[PIL.Image.Image, List[PIL.Image.Image], None] = None,
            text: str = "",
            max_retries: int = 5,
            structured: bool = False,
            output_cls: BaseModel = None,
            label: str = None,
            helper_llm: Optional[Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI]] = None,
    ) -> Union[str, BaseModel]:
        """
        Main method to run a query against an LLM asynchronously, with support for retries,
        structured output, and multi-modal input. Delegates execution to LLMCallManager.
        """
        messages = [ChatMessage(role="system", content=prompt)]
        if text:
            messages.append(ChatMessage(role="user", content=text))
        if image:
            image_list = [image] if not isinstance(image, list) else image
            image_data = self.prepare_images(image_list, client)
            messages.append(ChatMessage(role="user", blocks=image_data))

        llm_manager = LLMCallManager(
            db_manager=self.token_repo.db_manager,
            llm=client,
            helper_llm=helper_llm,
            user=self.logger.user,
            logger=self.logger,
            max_retry=max_retries
        )

        generator = llm_manager._aexecute_llm_call(
            messages=messages,
            prompt=prompt,
            streaming=False,
            output_model=output_cls if structured else None,
            label=label
        )

        final_result = None
        async for r in generator:
            final_result = r

        return final_result

    async def adescr_img(self,
                        prompt: str,
                        main_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                        helper_llm: Optional[Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI]] = None,
                        image_path: Optional[str] = None,
                        image_pil: Optional[PIL.Image.Image] = None,
                        max_retries: int = 10,
                        output_cls: Type[BaseModel] = ImageDescription,
                        label: str = "IMAGE_DESCRIPTION"
                        ) -> str:
        """
        Query the llm asynchronously to describe the input image.
        :param image_path: The path of the image.
        :param main_llm: The main llm to use
        :param helper_llm: The llm to use in case of rate limit error
        :return: The text description of the image.
        """
        if not helper_llm:
            helper_llm = main_llm

        if image_path:
            pil_image = Image.open(image_path)
        else:
            pil_image = image_pil

        result = await self.arun(prompt=prompt,
                                client=main_llm,
                                helper_llm=helper_llm,
                                image=pil_image,
                                max_retries=max_retries,
                                label=label,
                                structured=True,
                                output_cls=output_cls,
                                )

        # Unpack the Pydantic model and return a string
        if isinstance(result, BaseModel):
            result_dict = result.model_dump()
            return str(next(iter(result_dict.values())))

        return str(result)

    # -------------------------------------------------------------------------
    # SYNCHRONOUS METHODS
    # -------------------------------------------------------------------------
    # we used it for running the multithreading for describing the images

    def run(self,
            prompt: str,
            client: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
            image: Union[PIL.Image.Image, List[PIL.Image.Image], None] = None,
            text: str = "",
            max_retries: int = 5,
            structured: bool = False,
            output_cls: BaseModel = None,
            label: str = None,
            helper_llm: Optional[Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI]] = None,
    ) -> Union[str, BaseModel]:
        """
        Main method to run a query against an LLM synchronously, with support for retries,
        structured output, and multi-modal input. Delegates execution to LLMCallManager.
        """
        messages = [ChatMessage(role="system", content=prompt)]
        if text:
            messages.append(ChatMessage(role="user", content=text))
        if image:
            image_list = [image] if not isinstance(image, list) else image
            image_data = self.prepare_images(image_list, client)
            messages.append(ChatMessage(role="user", blocks=image_data))

        llm_manager = LLMCallManager(
            db_manager=self.token_repo.db_manager,
            llm=client,
            helper_llm=helper_llm,
            user=self.logger.user,
            logger=self.logger,
            max_retry=max_retries
        )

        generator = llm_manager._execute_llm_call(
            messages=messages,
            prompt=prompt,
            streaming=False,
            output_model=output_cls if structured else None,
            label=label
        )

        final_result = None
        for r in generator:
            final_result = r

        return final_result

    def descr_img(self,
                        prompt: str,
                        main_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                        helper_llm: Optional[Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI]] = None,
                        image_path: Optional[str] = None,
                        image_pil: Optional[PIL.Image.Image] = None,
                        max_retries: int = 10,
                        output_cls: Type[BaseModel] = ImageDescription,
                        label: str = "IMAGE_DESCRIPTION"
                        ) -> str:
        """
        Query the llm synchronously to describe the input image.
        :param image_path: The path of the image.
        :param main_llm: The main llm to use
        :param helper_llm: The llm to use in case of rate limit error
        :return: The text description of the image.
        """
        if not helper_llm:
            helper_llm = main_llm

        if image_path:
            pil_image = Image.open(image_path)
        else:
            pil_image = image_pil

        result = self.run(prompt=prompt,
                                client=main_llm,
                                helper_llm=helper_llm,
                                image=pil_image,
                                max_retries=max_retries,
                                label=label,
                                structured=True,
                                output_cls=output_cls,
                                )

        # Unpack the Pydantic model and return a string
        if isinstance(result, BaseModel):
            result_dict = result.model_dump()
            return str(next(iter(result_dict.values())))

        return str(result)