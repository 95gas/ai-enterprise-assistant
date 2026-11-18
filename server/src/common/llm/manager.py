from typing import Any, Optional, Union, List, AsyncGenerator, Generator
import asyncio
import time
import random
import re

from openai import APITimeoutError, RateLimitError
from pydantic import BaseModel
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.prompts import RichPromptTemplate
from llama_index.core.output_parsers import PydanticOutputParser
from llama_index.core.program import LLMTextCompletionProgram, MultiModalLLMCompletionProgram
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.huggingface import HuggingFaceLLM

from src.common.connectors.postgres.base import PostgresManager
from src.common.connectors.postgres.token import TokenRepo
from src.common.models.tokenizer import TokenCounter
from src.common.logging.logger import DebugLogger


class LLMCallManager:
    """
    Centralized manager handling all LLM calls (sync and async), retries,
    streaming processes, rate limiting, and token tracking.
    """

    def __init__(self,
                 db_manager: Optional[PostgresManager] = None,
                 llm: Optional[Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI, HuggingFaceLLM]] = None,
                 helper_llm: Optional[Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI, HuggingFaceLLM]] = None,
                 user: Optional[str] = None,
                 logger: Optional[DebugLogger] = None,
                 max_retry: int = 5):
        """
        Initializes the LLMCallManager.
        :param db_manager: Optional PostgreSQL manager for token tracking.
        :param llm: The primary LLM client.
        :param helper_llm: A secondary LLM client used as a fallback.
        :param user: The current user's identifier.
        :param logger: Logger instance for debugging.
        :param max_retry: Maximum number of retry attempts for LLM calls.
        """
        self.llm = llm
        self.helper_llm = helper_llm
        self.max_retry = max_retry
        self.user = user
        self.logger = logger or DebugLogger(user=self.user, class_name=self.__class__.__name__,
                                            main_feature="LLM_CALLS")

        self.token_manager = None
        if db_manager:
            try:
                self.token_manager = TokenRepo(db_manager=db_manager)
                if self.user:
                    self.token_manager.logger.set_user(user=self.user)
            except Exception as e:
                self.logger.warning(f"Could not initialize TokenRepo: {e}")

        self.input_tokens = 0
        self.output_tokens = 0

    def get_model_name(self, client: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI, HuggingFaceLLM]) -> str:
        """
        Determines the model name from the LLM client instance.
        """
        try:
            if isinstance(client, AzureOpenAI):
                return client.engine
            if isinstance(client, HuggingFaceLLM):
                return client.model_name
            else:
                return client.model
        except Exception as e:
            self.logger.warning(f"Unable to read model name: {e}")
        return "unknown-model"

    @staticmethod
    def get_provider_name(client: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI, HuggingFaceLLM]) -> str:
        """
        Determines the provider name from the LLM client instance.
        """
        if isinstance(client, AzureOpenAI):
            return "azure"
        elif isinstance(client, Ollama):
            return "ollama"
        elif isinstance(client, GoogleGenAI):
            return "google"
        elif isinstance(client, OpenAI):
            return "openai"
        elif isinstance(client, HuggingFaceLLM):
            return "huggingface"
        raise TypeError(f"Unknown client type: {type(client).__name__}")

    def get_tokenizer(self, client: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI, HuggingFaceLLM]) -> TokenCounter:
        """
        Initializes and returns a TokenCounter for the specified LLM client.
        """
        provider = self.get_provider_name(client)
        model_name = self.get_model_name(client)
        return TokenCounter(logger=self.logger, provider=provider, model_name=model_name)

    def save_tokens(self, input_tokens: int, output_tokens: int,
                    client: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI, HuggingFaceLLM], label: str):
        """
        Logs token usage and saves it to PostgreSQL when configured.
        """
        provider = self.get_provider_name(client)
        self.logger.info(f"Input tokens: {input_tokens} - Output tokens: {output_tokens}")

        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

        if self.token_manager:
            try:
                self.token_manager.save(
                    user=self.user,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    llm_model=client.model,
                    provider=provider,
                    label=label,
                )
            except Exception as e:
                self.logger.warning(f"Could not save tokens to PostgreSQL due to {str(e)}")

    def _adjust_temperature(self):
        """
        Attempts to lower the temperature of the current LLM
        """
        try:
            current_temp = getattr(self.llm, 'temperature', None)

            # Decrease temperature by 0.2
            new_temp = max(0.0, float(current_temp) - 0.2)
            self.llm.temperature = new_temp
            self.logger.warning(
                f"Adjusted LLM temperature from {current_temp} to {new_temp} due to exception.")

        except Exception as e:
            self.logger.warning(f"Failed to adjust temperature: {e}")

    # -------------------------------------------------------------------------
    # SHARED UTILITIES
    # -------------------------------------------------------------------------

    def structured_output(self, 
                          output_model: BaseModel, 
                          prompt: Optional[str] = None,
                          messages: List[ChatMessage] = None):
        """
        Executes a prompt to generate a structured Pydantic output, fully supporting multimodal LLMs.
        Note: This is inherently synchronous in llama_index for programs unless using aprogram.
        """
        try:
            prompt_str = ""
            if prompt:
                prompt_str += str(prompt) + "\n"

            has_images = False
            image_blocks = []

            if messages:
                for m in messages:
                    if getattr(m, 'content', None) and isinstance(m.content, str):
                        prompt_str += f"{m.role}: {m.content}\n"
                    if getattr(m, 'blocks', None):
                        for block in m.blocks:
                            if getattr(block, 'text', None):
                                prompt_str += f"{m.role}: {block.text}\n"
                            elif getattr(block, 'image', None):
                                has_images = True
                                image_blocks.append(block)

            prompt_template_str = "{context_str}"

            if has_images:
                program = MultiModalLLMCompletionProgram.from_defaults(
                    output_parser=PydanticOutputParser(output_cls=output_model),
                    prompt_template_str=prompt_template_str,
                    multi_modal_llm=self.llm,
                    verbose=False
                )
                return program(
                    context_str=prompt_str.strip(),
                    image_documents=image_blocks
                )
            else:
                program = LLMTextCompletionProgram.from_defaults(
                    output_parser=PydanticOutputParser(output_cls=output_model),
                    prompt_template_str=prompt_template_str,
                    verbose=False,
                    llm=self.llm
                )
                return program(context_str=prompt_str.strip())

        except Exception as e:
            self.logger.error(f"Error compiling obj: {e}")
            return ""

    # -------------------------------------------------------------------------
    # ASYNC METHODS
    # -------------------------------------------------------------------------

    async def _handle_llm_exception(self, exc: Exception, attempt: int, base_delay: float = 2.0):
        is_rate_limit = "429" in str(exc) or "token" in str(exc).lower() or isinstance(exc, (APITimeoutError, RateLimitError))
        is_policy = "ResponsibleAIPolicyViolation" in str(exc)

        if is_policy and not self.helper_llm:
            self.logger.error(f"AIPolicyViolation: Cannot retry. Error: {exc}")
            raise exc

        if is_rate_limit or is_policy:
            if self.helper_llm:
                self.logger.warning("RateLimit or Policy error hit! Switching to fallback/helper LLM...")
                self.llm = self.helper_llm
                return

            jitter = random.uniform(0, 1)
            sleep_time = (base_delay * (2 ** attempt)) + jitter
            self.logger.warning(f"RateLimit exceeded. Retrying in {sleep_time:.2f}s...")
            await asyncio.sleep(sleep_time)
        else:
            self.logger.warning(f"An unexpected error occurred on attempt {attempt + 1}: {exc}. Retrying...")
            await asyncio.sleep(5)

    async def _process_llm_stream(self, stream: Any) -> AsyncGenerator[str, None]:
        completion = ""
        async for chunk in stream:
            delta = chunk.delta if hasattr(chunk, 'delta') else str(chunk)
            completion += delta
            if isinstance(self.llm, Ollama):
                cleaned = re.sub(r"<think>.*?</think>", "", completion, flags=re.DOTALL).strip()
                yield cleaned
            else:
                yield completion

    async def _aexecute_llm_call(self,
                                 messages: List[ChatMessage] = None,
                                 prompt: str = None,
                                 streaming: bool = False,
                                 output_model: BaseModel = None,
                                 label: str = None) -> AsyncGenerator[str, None]:
        if not messages and not prompt:
            self.logger.error("No messages or prompt provided.")
            raise RuntimeError("No messages or prompt provided.")

        if streaming and output_model:
            self.logger.error("You cannot stream a structured output.")
            raise RuntimeError("You cannot stream a structured output.")

        if label is None or label == "UNDEFINED":
            label = "UNDEFINED"
            self.logger.warning(f"Running prompt with no label [{label}]. Please remember to assign one.")

        last_exc = None
        for attempt in range(self.max_retry):
            try:
                completion = ""
                if not output_model:
                    if streaming:
                        if not prompt:
                            stream = await self.llm.astream_chat(messages=messages)
                        else:
                            stream = await self.llm.astream_complete(prompt=prompt)
                        async for chunk in self._process_llm_stream(stream):
                            completion = chunk
                            yield completion
                    else:
                        if not prompt:
                            response = await self.llm.achat(messages=messages)
                            completion = response.message.content
                        else:
                            response = await self.llm.acomplete(prompt=prompt)
                            completion = response.text
                        yield completion
                else:
                    completion = self.structured_output(output_model=output_model, prompt=prompt, messages=messages)
                    yield completion

                self._record_tokens(prompt, messages, output_model, completion, label)
                return
            except Exception as exc:
                last_exc = exc
                await self._handle_llm_exception(exc, attempt)

        self.logger.error(f"Max retries ({self.max_retry}) reached for '{label}'. Last error: {last_exc}", exc_info=True)
        raise RuntimeError("LLM call failed after maximum retries.") from last_exc

    async def acomplete(self,
                        prompt: Union[str, RichPromptTemplate],
                        label: Optional[str] = None,
                        streaming: bool = False,
                        output_model: BaseModel = None) -> Union[str, AsyncGenerator[str, None]]:
        if isinstance(prompt, RichPromptTemplate):
            if not label:
                label = prompt.metadata.get("prompt_name")
            prompt = prompt.format()

        generator = self._aexecute_llm_call(prompt=prompt, label=label, streaming=streaming, output_model=output_model)

        if streaming:
            return generator
        else:
            final_result = ""
            async for partial in generator:
                final_result = partial
            return final_result

    async def achat(self,
                    messages: List[ChatMessage],
                    prompt: Union[str, RichPromptTemplate] = None,
                    label: Optional[str] = None,
                    streaming: bool = False,
                    output_model: BaseModel = None) -> Union[str, AsyncGenerator[str, None]]:
        if prompt:
            if isinstance(prompt, RichPromptTemplate):
                if not label:
                    label = prompt.metadata.get("prompt_name")
                prompt = prompt.format()
            messages = [ChatMessage(role="system", content=prompt)] + messages

        generator = self._aexecute_llm_call(messages=messages, label=label, streaming=streaming, output_model=output_model)

        if streaming:
            return generator
        else:
            final_result = ""
            async for partial in generator:
                final_result = partial
            return final_result


    # -------------------------------------------------------------------------
    # SYNCHRONOUS METHODS
    # -------------------------------------------------------------------------

    def _handle_llm_exception_sync(self, exc: Exception, attempt: int, base_delay: float = 2.0):
        """
        Synchronous version of exception handler with time.sleep() instead of asyncio.sleep()
        """
        is_rate_limit = "429" in str(exc) or "token" in str(exc).lower() or isinstance(exc, (APITimeoutError, RateLimitError))
        is_policy = "ResponsibleAIPolicyViolation" in str(exc)

        if is_policy and not self.helper_llm:
            self.logger.error(f"AIPolicyViolation: Cannot retry. Error: {exc}")
            raise exc

        if is_rate_limit or is_policy:
            if self.helper_llm:
                self.logger.warning("RateLimit or Policy error hit! Switching to fallback/helper LLM...")
                self.llm = self.helper_llm
                return

            jitter = random.uniform(0, 1)
            sleep_time = (base_delay * (2 ** attempt)) + jitter
            self.logger.warning(f"RateLimit exceeded. Retrying in {sleep_time:.2f}s...")
            time.sleep(sleep_time)
        else:
            self.logger.warning(f"An unexpected error occurred on attempt {attempt + 1}: {exc}. Retrying...")
            time.sleep(5)

    def _process_llm_stream_sync(self, stream: Any) -> Generator[str, None, None]:
        """
        Synchronous stream processing, yielding clean text chunks.
        """
        completion = ""
        for chunk in stream:
            delta = chunk.delta if hasattr(chunk, 'delta') else str(chunk)
            completion += delta
            if isinstance(self.llm, Ollama):
                cleaned = re.sub(r"<think>.*?</think>", "", completion, flags=re.DOTALL).strip()
                yield cleaned
            else:
                yield completion

    def _execute_llm_call(self,
                          messages: List[ChatMessage] = None,
                          prompt: str = None,
                          streaming: bool = False,
                          output_model: BaseModel = None,
                          label: str = None) -> Generator[str, None, None]:
        """
        Synchronous version of execution core handling logic, structure formatting and retries.
        """
        if not messages and not prompt:
            self.logger.error("No messages or prompt provided.")
            raise RuntimeError("No messages or prompt provided.")

        if streaming and output_model:
            self.logger.error("You cannot stream a structured output.")
            raise RuntimeError("You cannot stream a structured output.")

        if label is None or label == "UNDEFINED":
            label = "UNDEFINED"
            self.logger.warning(f"Running prompt with no label [{label}]. Please remember to assign one.")

        last_exc = None
        for attempt in range(self.max_retry):
            try:
                completion = ""
                if not output_model:
                    if streaming:
                        if not prompt:
                            stream = self.llm.stream_chat(messages=messages)
                        else:
                            stream = self.llm.stream_complete(prompt=prompt)
                        for chunk in self._process_llm_stream_sync(stream):
                            completion = chunk
                            yield completion
                    else:
                        if not prompt:
                            response = self.llm.chat(messages=messages)
                            completion = response.message.content
                        else:
                            response = self.llm.complete(prompt=prompt)
                            completion = response.text
                        yield completion
                else:
                    completion = self.structured_output(output_model=output_model, prompt=prompt, messages=messages)
                    yield completion

                self._record_tokens(prompt, messages, output_model, completion, label)
                return
            except Exception as exc:
                last_exc = exc
                self._handle_llm_exception_sync(exc, attempt)

        self.logger.error(f"Max retries ({self.max_retry}) reached for '{label}'. Last error: {last_exc}", exc_info=True)
        raise RuntimeError("LLM call failed after maximum retries.") from last_exc

    def complete(self,
                 prompt: Union[str, RichPromptTemplate],
                 label: Optional[str] = None,
                 streaming: bool = False,
                 output_model: BaseModel = None) -> Union[str, Generator[str, None, None]]:
        """
        Synchronously completes a single prompt using the LLM.
        """
        if isinstance(prompt, RichPromptTemplate):
            if not label:
                label = prompt.metadata.get("prompt_name")
            prompt = prompt.format()

        generator = self._execute_llm_call(prompt=prompt, label=label, streaming=streaming, output_model=output_model)

        if streaming:
            return generator
        else:
            final_result = ""
            for partial in generator:
                final_result = partial
            return final_result

    def chat(self,
             messages: List[ChatMessage],
             prompt: Union[str, RichPromptTemplate] = None,
             label: Optional[str] = None,
             streaming: bool = False,
             output_model: BaseModel = None) -> Union[str, Generator[str, None, None]]:
        """
        Synchronously executes a chat completion using the LLM.
        """
        if prompt:
            if isinstance(prompt, RichPromptTemplate):
                if not label:
                    label = prompt.metadata.get("prompt_name")
                prompt = prompt.format()
            messages = [ChatMessage(role="system", content=prompt)] + messages

        generator = self._execute_llm_call(messages=messages, label=label, streaming=streaming, output_model=output_model)

        if streaming:
            return generator
        else:
            final_result = ""
            for partial in generator:
                final_result = partial
            return final_result

    def _record_tokens(self, prompt, messages, output_model, completion, label):
        """
        Helper method to isolate token processing calculation out of the execution loops.
        """
        tokenizer = self.get_tokenizer(self.llm)
        prompt_str = str(prompt or "")
        messages_str = ""
        if messages:
            for m in messages:
                if getattr(m, 'content', None) and isinstance(m.content, str):
                    messages_str += " " + m.content
                if getattr(m, 'blocks', None):
                    for b in m.blocks:
                        if getattr(b, 'text', None):
                            messages_str += " " + b.text

        input_content = prompt_str + messages_str + (
            str(output_model.model_json_schema()) if output_model else "")

        input_tokens = tokenizer.count(input_content)
        output_tokens = tokenizer.count(str(completion))
        self.save_tokens(input_tokens, output_tokens, self.llm, label=label)