from llama_index.readers.file import UnstructuredReader
import os
from pydub.utils import make_chunks
import math
from src.common.logging.logger import DebugLogger
from pathlib import Path
from typing import IO, Any, List, Sequence, Tuple, Union, Optional, Iterator
from PIL import Image
from src.common.document_processing.parser.table import TableHelper
from src.common.document_processing.services.llm_service import LLMService
from src.common.document_processing.utils.utils import delete_file
from src.common.prompt_manager import PromptManager
from llama_index.llms.azure_openai import AzureOpenAI
from openai import OpenAI
from llama_index.llms.ollama import Ollama
from audio_extract import extract_audio
from os.path import isfile, join
from pydub import AudioSegment
from os import listdir
from config.settings import settings

STORAGE_PATH = settings.STORAGE_PATH


class GeneralFileTypeHelper:
    """Handles the different steps of the Office family doc (xlsx, docx, csv and xml) processing for conversion to markdown."""

    def __init__(self,
                 main_llm: Union[OpenAI, AzureOpenAI, Ollama],
                 helper_llm: Union[OpenAI, AzureOpenAI, Ollama],
                 table_helper: TableHelper,
                 llm_doc_service: LLMService,
                 logger: Optional[DebugLogger] = None,
                 max_retry: int = 5,
                 ):
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initializing GeneralFileTypeHelper...")
        self.cache_dir =  STORAGE_PATH
        self.deployment_azure = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        self.table_manager = table_helper
        self.max_retry = max_retry
        self.counter = 0
        self.main_llm = main_llm
        self.helper_llm = helper_llm
        self.llm_doc_service = llm_doc_service
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, "..", "prompts")
        self.prompt_manager = PromptManager(prompts_folder=prompt_path)
        self.logger.success("GeneralFileTypeHelper ready.")

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)
        self.llm_doc_service.logger.set_user(user)
        self.logger.set_class_name(self.__class__.__name__)
        self.logger.set_main_feature("DOC")

    @DebugLogger.profile
    async def get_markdown_email(
            self,
            full_path: str,
            filename: str,
            languages: Optional[Union[str, List[str]]] = None
    ) -> List[dict]:
        try:
            self.logger.info(f"Processing email file '{filename}'")
            loader = UnstructuredReader()
            eml_documents = loader.load_data(
                Path(full_path),
                unstructured_kwargs={"process_attachments": False}
            )

            return [{"page_content": thread.text,
                     "metadata":
                         {"filename": filename
                          }
                     } for thread in
                             eml_documents]

        except Exception as e:
            self.logger.error(f"Failed to get markdown: {str(e)}")
            raise e

    @DebugLogger.profile
    async def get_markdown_image(
            self,
            full_path: str,
            filename: str,
            languages: Optional[Union[str, List[str]]] = None
    ) -> List[dict]:
        try:
            self.logger.info(f"Processing image file '{filename}'")

            image_description_prompt = self.prompt_manager.get_prompt("IMG_DESCR")
            pil_image = Image.open(full_path)
            md = await self.llm_doc_service.adescr_img(prompt=image_description_prompt, main_llm=self.main_llm,
                                                       helper_llm=self.helper_llm, image_pil=pil_image)

            return [{"page_content": md,
                     "metadata":
                         {"filename": filename
                          }
                     }]

        except Exception as e:
            self.logger.error(f"Failed to get markdown: {str(e)}")
            raise e

    @DebugLogger.profile
    async def get_markdown_audio(
            self,
            full_path: str,
            filename: str,
            file_content_type: str,
            languages: Optional[Union[str, List[str]]] = None
    ) -> List[dict]:
        audio_dir = str(self.cache_dir)
        os.makedirs(audio_dir, exist_ok=True)
        try:
            self.logger.info(f"Processing audio file '{filename}'")

            if file_content_type == "video/mp4":
                tmp_audio = audio_dir + "/audio.mp3"
                extract_audio(input_path=full_path, output_path=tmp_audio)
                byte_size = os.path.getsize(tmp_audio)
                audio_file_path = tmp_audio
            else:
                byte_size = os.path.getsize(full_path)
                audio_file_path = full_path

            # check size audio and split
            mb_size = byte_size / (1024 * 1024)
            results = []
            audio_file_list = []
            if mb_size > 25:
                self.split_audio(audio_file_path, audio_dir, int(mb_size))
                os.unlink(audio_file_path)
                audio_file_list = [f for f in listdir(audio_dir) if isfile(join(audio_dir, f))]
                for f in audio_file_list:
                    self.logger.info(f"Processing audio chunk file '{f}'...")
                    file_path = join(audio_dir, f)
                    results.append({"page_content": self.transcribe_audio(file_path),
                     "metadata":
                         {"filename": filename
                          }
                     })
            else:
                results.append({"page_content": self.transcribe_audio(audio_file_path),
                                "metadata":
                                    {"filename": filename
                                     }
                                })
            delete_file(audio_file_path)
            [delete_file(audio) for audio in audio_file_list]
            self.logger.info(f"Audio file '{filename}' processed successfully!")
            return results

        except Exception as e:
            self.logger.error(f"Failed to get markdown: {str(e)}")
            raise e


    def split_audio(self,
                    file_path:str,
                    output_dir:str,
                    mb_size: int):  # 29 minutes in milliseconds
        try:
            self.logger.info("Splitting audio...")
            filename, file_extension = os.path.splitext(file_path)
            _file_extension = file_extension.replace(".", "")
            myaudio = AudioSegment.from_file(file_path, _file_extension)
            duration_in_sec = len(myaudio) / 1000  # Length of audio in sec
            file_size = mb_size * 1000000
            file_split_size = 10000000  # 10Mb OR 10, 000, 000 bytes

            chunk_length_in_sec = math.ceil((duration_in_sec * file_split_size) / file_size)  # in sec
            chunk_length_ms = chunk_length_in_sec * 1000
            chunks = make_chunks(myaudio, chunk_length_ms)

            # Export all of the individual chunks as wav files
            for i, chunk in enumerate(chunks):
                chunk_name = output_dir + f"/chunk{i}.{_file_extension}"
                chunk.export(chunk_name, format=_file_extension)
            self.logger.info("Audio split successfully")
        except Exception as e:
            self.logger.error(f"Failed to split audio: {str(e)}")
            raise e

    @staticmethod
    async def transcribe_audio(
                         audio_file_path: str):
        client = OpenAI()
        with open(audio_file_path, "rb") as audio_file_bytes:
            transcription = await client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=audio_file_bytes,
            )
            return transcription.text