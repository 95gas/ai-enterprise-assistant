from typing import Any, Optional, Union, List, Dict, AsyncGenerator, Literal
from openai import APITimeoutError, RateLimitError
import re, json, asyncio, uuid, os
from pydantic import BaseModel

from llama_index.core.output_parsers import PydanticOutputParser
from llama_index.core.program import LLMTextCompletionProgram
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.prompts import RichPromptTemplate
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.core.workflow import Event, Workflow
from llama_index.core.schema import NodeWithScore
from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.huggingface import HuggingFaceLLM

from src.common.connectors.postgres.base import PostgresManager
from src.common.connectors.postgres.token import TokenRepo
from src.common.models.tokenizer import TokenCounter
from src.common.prompt_manager import PromptManager
from src.services.rag.retriever import CustomRetriever
from src.common.logging.logger import DebugLogger
from src.services.chat.schema import Source
from config.settings import settings
from src.common.telemetry import trace_rag_retrieval

STORAGE_CHATS = settings.STORAGE_CHATS


class Summary(BaseModel):
    summary: str
    assessment: Literal["STOP", "CONTINUE"]

class StreamingEvent(Event):
    """
    :param msg: Directly streamed
    :param step_id: Streamed only if configured in STEP_STRING_DICT, otherwise catch KeyError
    """
    msg: Union[str, None] = None
    step_id: Union[str, None] = None
    progress_id: Union[str, None] = None
    progress_phase: Union[str, None] = None
    progress_agent: Union[str, None] = None
    duration_ms: Union[int, None] = None

class FinalAnswerEvent(Event):
    pass

# ---------------------------------------------------------------------------------------------------------------------

class BaseWorkflow(Workflow):
    def __init__(self,
                 llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                 helper_llm: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI],
                 provider: str,
                 db_manager: PostgresManager,
                 prompt_manager: PromptManager = None,
                 chat_history: List[ChatMessage] = [],
                 retriever: Optional[CustomRetriever] = None,
                 max_context_window: Optional[int] = 128000,
                 chat_id: Optional[str] = None,
                 user: Optional[str] = None,
                 logger: Optional[DebugLogger] = None,
                 input_tokens: Optional[int] = 0,
                 output_tokens: Optional[int] = 0,
                 **kwargs) -> None:
        """
        Base class for all chat workflows, providing core functionality for
        LLM interaction, document retrieval, and state management.
        """
        super().__init__(timeout=3600.0,
                         # verbose=True,
                         **kwargs)
        self._retriever = retriever
        self._llm = llm
        self.user = user
        self.count_retry = 0
        self.max_retry = 5
        self._provider = provider
        self.helper_llm = helper_llm
        self.chat_history = chat_history
        self.db_manager = db_manager
        self.prompt_manager = prompt_manager or PromptManager(user=user)
        self.token_manager = TokenRepo(db_manager=db_manager)
        self.token_manager.logger.set_user(user=user)
        self.max_context_window = max_context_window or 128000
        self.logger = logger or DebugLogger(user=self.user,
                                            class_name=self.__class__.__name__,
                                            main_feature="CHAT")
        self.tokenizer = TokenCounter(logger=DebugLogger(user=self.user,
                                                         main_feature="CHAT"),
                                      provider=self._provider,
                                      model_name=self.get_model_name_from_llm(self._llm))
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self._MAX_QUERY_WORDS = 1024
        self._TRUNCATION_WORD_COUNT = 500
        self.request_id = uuid.uuid4()
        self.chat_id = chat_id
        self.chat_folder = STORAGE_CHATS / self.chat_id
        os.makedirs(self.chat_folder, exist_ok=True)


    def _process_nodes(self, nodes: List[NodeWithScore], extract_all: bool) -> int:
        """
        Processes nodes in-place to handle tables, eliminates duplicates and calculates total token count.
        Returns the total number of tokens.
        """
        total_tokens = 0
        token_limit = self.max_context_window // 4
        seen_texts = set()
        processed_nodes = []
        for n in nodes:
            # Refactor table elements if they fit within the context budget
            if n.node.metadata.get("type") == "table":
                n.node.text = n.node.metadata.get("markdown_table", "")
                n.node.metadata["tokens"] = int(n.node.metadata.get("table_tokens", 0))
            if n.node.text in seen_texts:
                if extract_all:  # Only add if extract_all is true and conditions are met
                    if total_tokens <= token_limit or n.node.metadata.get("type") != "table":
                        total_tokens += int(n.node.metadata.get("tokens", 0))
                        processed_nodes.append(n)
            else:
                total_tokens += int(n.node.metadata.get("tokens", 0))
                seen_texts.add(n.node.text)
                processed_nodes.append(n)
        nodes[:] = processed_nodes
        return total_tokens


    def check_context_window_size(self, prompt: str) -> int:
        """
        Counts input tokens for knowing the amount of context window used.
        :param prompt: the input prompt to the llm
        :return: number of tokens
        """
        _total_token = self.tokenizer.count(prompt)
        if _total_token >= self.max_context_window:
            self.logger.error(f"Please reduce the length of your messages.")
            raise RateLimitError
        return _total_token


    async def _generate_and_validate_query(self, rag_query: Optional[str] = None, chat_history: Optional[List[ChatMessage]] = list) -> str:
        """Generates a RAG query and ensures it's within the word limit."""
        if not rag_query and not chat_history:
            raise ValueError("Must provide either rag_query or chat_history.")

        if not rag_query:
            prompt = self.prompt_manager.get_prompt(prompt_name="WRITE_RAG_QUERY", conversation=str(chat_history))
            rag_query = await self._complete(prompt=prompt)

        query_words = rag_query.split()
        if len(query_words) == 0:
            self.logger.warning("RAG query is empty.")
            rag_query = chat_history[-1].content
        if len(query_words) <= self._MAX_QUERY_WORDS:
            return rag_query

        # If too long, try summarizing first
        self.logger.warning(f"Initial RAG query exceeds {self._MAX_QUERY_WORDS} words. Summarizing...")
        prompt = self.prompt_manager.get_prompt(prompt_name="SUMMARIZE_QUERY", user_query=rag_query)
        rag_query = await self._complete(prompt=prompt)

        query_words = rag_query.split()
        if len(query_words) <= self._MAX_QUERY_WORDS:
            return rag_query

        # If still too long, perform hard truncation as a last resort
        self.logger.warning(f"Summarized query still too long. Truncating to {2 * self._TRUNCATION_WORD_COUNT} words.")
        truncated_query = " ".join(
            query_words[:self._TRUNCATION_WORD_COUNT] +
            ["[...]"] +
            query_words[-self._TRUNCATION_WORD_COUNT:]
        )
        return truncated_query


    @trace_rag_retrieval
    async def _get_nodes(self,
                         query: Optional[str] = None,
                         chat_history: Optional[List[ChatMessage]] = None,
                         max_nodes: Optional[int] = 25,
                         extract_all: Optional[bool] = False,
                         ) -> List[NodeWithScore]:
        """
        Generates a RAG query, retrieves relevant nodes, and post-processes them.
        :param user_query: The user's query.
        :param chat_history: The past conversation to avoid reusing reference IDs.
        :param extract_all: If true, bypasses similarity search and retrieves all nodes.
        :return: A list of processed and unique nodes.
        """
        if not query and not chat_history and not extract_all:
            raise ValueError("Must provide either query or chat_history or extract_all.")

        if extract_all:
            rag_query = ""
            self.logger.info("Extracting all nodes (texts and tables)...")
        else:
            rag_query = await self._generate_and_validate_query(rag_query=query, chat_history=chat_history)
            self.logger.info(f"Retrieving nodes with query: {rag_query}")

        self._retriever._similarity_top_k = max_nodes
        self.logger.debug(f"Running RAG query: {rag_query}")
        nodes = self._retriever.retrieve(rag_query)
        self.logger.info(f"Retrieved nodes: {len(nodes)}")
        if not nodes:
            self.logger.warning(f"No nodes found for query: {rag_query}")
            return []

        # --- Apply post retrieving processing steps ---
        nodes_tokens = self._process_nodes(nodes, extract_all)

        nodes.sort(key=lambda x: (x.node.metadata.get("filename", ""), int(x.node.metadata.get("chunk_number", 0))))

        self.logger.success(f"Tokens retrieved: {nodes_tokens}")
        self.logger.success(f"Num of sources after postprocessing: {len(nodes)}")
        return nodes


    def normalize_nodes_to_sources(self, nodes: List[NodeWithScore]) -> List[Source]:
        return [Source(type="docs",
                       filename=n.node.metadata["filename"],
                       text=str(n.node.text),
                       chunk_number=n.node.metadata["chunk_number"],
                       reference_index=n.node.metadata["index_in_doc"],
                       s3_bucket=n.node.metadata["s3_bucket"],
                       s3_path=n.node.metadata["s3_path"],
                       s3_page=n.node.metadata["s3_page"],
                       uri=n.node.metadata.get("og_uri"),
                       id=n.node.id_) for n in nodes]


    def check_referenced_sources(self,
                                 answer: str,
                                 sources: List[Source],
        ) -> List[Source]:
        """
        Removes nodes that have not been cited in the answer.
        :param answer: The answer string containing citations like [1, 2-4].
        :param nodes: A list of all source nodes.
        :return: The list of nodes that were actually cited.
        """
        self.logger.info("Checking references...")
        if not sources:
            self.logger.info("No nodes found, skipping references' check.")
            return []
        try:
            mapping = {ord("\u2012"): ord("-"),
                       ord("\u2013"): ord("-"),
                       ord("\u2014"): ord("-"),
                       ord("\u2212"): ord("-")}
            answer = answer.translate(mapping)
            # Step 1: Find all strings inside citation brackets, e.g., ["1, 2", "4-6"]
            citation_regex = r"\[([\d\s,-]+)\]"
            cited_contents = re.findall(citation_regex, answer)
            # Step 2: Parse all found citation strings into a single set of IDs
            all_cited_ids = set()
            for content in cited_contents:
                parts = re.split(r'[,\s]+', content.strip())
                for part in parts:
                    part = part.strip()
                    if "-" in part: # handle ranges like 2-40
                        start, end = map(int, part.split('-'))
                        all_cited_ids.update(i for i in range(start, end + 1))
                    elif part.isdigit(): # handle single numbers
                        all_cited_ids.add(int(part))
            if not all_cited_ids:
                self.logger.info("No referenced sources found in the answer.")
                return []
            # Step 3: Filter nodes to keep only those that were cited
            cited_sources = [s for s in sources if s.reference_id in all_cited_ids]
            delta = len(sources) - len(cited_sources)
            self.logger.success(f"Checking references completed. Removed {delta}/{len(sources)} sources.")
            return cited_sources
        except Exception as e:
            self.logger.warning(f"An unexpected error occurred while checking references: {e}")
            return []
        

    def chat_history_to_str(self, chat_history: List[ChatMessage]) ->  List[str]:
        """
        Converts the chat history from a list of ChatMessage to a list of dictionaries.
        :param chat_history: list of ChatMessage
        :return: list of messages as string
        """
        if not chat_history:
            return ["No past conversation."]
        chat_history_str = []
        if chat_history:
            for msg in chat_history:
                if msg.role == "assistant":
                    if "sources" in msg.additional_kwargs:
                        if msg.additional_kwargs["sources"]:
                            list_sources_str = self.get_sources_str(msg.additional_kwargs["sources"])
                            msg_str = {"role": msg.role, "content": msg.content + "\nFrom sources " + list_sources_str}
                        else:
                            msg_str = {"role": msg.role, "content": msg.content + "\nFrom my internal knowledge"}
                    else:
                        msg_str = {"role": msg.role, "content": msg.content + "\nFrom my internal knowledge"}
                else:
                    msg_str = {"role": msg.role, "content": msg.content}
                chat_history_str.append(json.dumps(msg_str))
        return chat_history_str


    @staticmethod
    def get_sources_str(sources: List[dict]) -> str:
        """
        Converts the sources list into a string.
        :param sources: sources list
        :return: string representation of the sources.
        """
        sources_to_string = "[" + sources[0]["filename"]
        for item in sources[1:]:
            sources_to_string += ", " + item["filename"]
        sources_to_string += "]"
        return sources_to_string


    def get_sources_from_chat_history(self, chat_history: List[ChatMessage]) -> List[Source]:
        if not chat_history:
            return []
        
        past_sources = []
        for message in chat_history:
            if isinstance(message, ChatMessage): 
                for s in message.additional_kwargs.get("sources", []):
                    if isinstance(s, Source):
                        past_sources.append(s)
                    else:
                        try:
                            past_sources.append(Source(**s))
                        except Exception as e:
                            self.logger.error(f"Error creating Source: {e}")
            else:
                self.logger.warning(f"Source type '{type(message)}' not recognized.")
        return past_sources


    def add_id_to_sources(self, 
                          lst_sources: List[Source], 
                          chat_history: Optional[List[ChatMessage]] = [],
                          prev_answer: Optional[ChatMessage | None] = None,
                          ) -> List[Source]:
        if not lst_sources:
            return []

        lst_sources.sort(key=lambda x: (x.type, x.filename, x.chunk_number))
    
        for s in lst_sources:
            s.reference_id = 0

        if prev_answer:
            chat_history.append(prev_answer)
        past_sources = self.get_sources_from_chat_history(chat_history=chat_history) # previous sources keep their ids
        for s in past_sources:
            for new_s in lst_sources:
                if s.id == new_s.id:
                    new_s.reference_id = s.reference_id

        past_ref_ids = [s.reference_id for s in lst_sources + past_sources]
        next_id = max(past_ref_ids + [0])
        for s in lst_sources:
            if not s.reference_id:
                next_id += 1
                s.reference_id = next_id

        return lst_sources


    def format_tools_to_str(self, tools) -> str:
        return str(tools)
        #return "\n".join([f"{i+1}. {tool.metadata.name}: {tool.metadata.description}" for i, tool in enumerate(tools)])


    def format_agents_to_str(self, agents) -> str:
        return "\n".join([f'<agent agent_name="{agent.name}">{agent.description}</agent>' for agent in agents.values()])


    def format_recorded_notes_to_str(self, recorded_notes: Dict[str, str]) -> str:
        if not recorded_notes:
            return "No recorded notes."
        return "\n---\n".join([f"**{title}**:{content}" for title, content in recorded_notes.items()])


    def format_sources_to_str(self, sources_with_ids: List[Source]) -> str:
        if not sources_with_ids:
            return "No sources found."
        
        sources_with_ids.sort(key=lambda x: (x.type, x.filename, x.chunk_number))
        s_type = None
        s_name = None
        s_chunk_number = None
        output_str = ""
        try:
            for s in sources_with_ids:
                if s_type != s.type:
                    s_type = s.type
                    s_chunk_number = s.chunk_number or 0
                    output_str += f'\n### NEW **TYPE OF SOURCES** "{s_type.upper()}":'
                if s_name != s.filename:
                    s_name = s.filename
                    s_chunk_number = s.chunk_number or 0
                    output_str += f'\n- NEW **SOURCE** Excerpts from "{s_name}":'
                elif s_chunk_number != s.chunk_number:
                    s_chunk_number = s.chunk_number or 0
                    output_str += f"\n[...]"
                output_str += f"\n[{s.reference_id}]: "
                output_str += "{ " + self.truncate_text(s.text) if s.text else "PAST_REFERENCED_SOURCE" +" }"
                s_chunk_number += 1
        except Exception as e:
            self.logger.error(f"Error while formatting sources to str: {str(e)}")
            output_str = "[Error]"
        return output_str
    

    @staticmethod
    def truncate_text(text: str) -> str:
        if len(text) < 5000:
            return text.strip()
        return text[:2500].strip() + "..\n[...]\n.." + text[-2500:].strip()


    @staticmethod
    def compile_instruction(internal_knowledge: bool = False, 
                            web_search: bool = False, 
                            doc_search: bool = False, 
                            provided_sources: List[str] = [],
                            prev_answer: Optional[ChatMessage | None] = None,
                            orchestrator_input_text: Optional[str | None] = None) -> str:
        _instruction = "\n".join(filter(None, [
            "",
            "## Instruction\n",
            "The user has set following rules, that you must follow when generating the answer.\n",
            "### Authorized Knowledge Sources\n",
            "Your answer can be based **only** on:",
            "- Your internal knowledge" if internal_knowledge else "",
            "- Sources found in the web" if web_search else "",
            "- Sources found in the documents knowledge base" if doc_search else "",
            "- Sources provided by the user" if provided_sources else "",
            "\n",  # Line break
            "### Restrictions\n\nIf any data source is disabled, you must strictly adhere to the following constraints:" 
                if not any([internal_knowledge, web_search, doc_search]) else "",
            "- You must not use your internal knowledge" if not internal_knowledge else "",
            "- You have no access to the web" if not web_search else "",
            "- You have no access to any document" if not doc_search else "",
            f"\nHere are all the accessible documents: ```{[s for s in provided_sources]}```" if provided_sources else "",
            "\n"
        ]))
        if prev_answer:
            _instruction += "\n\n".join(["## Previous Answer",
                                        "Generate a long answer replying to the given user query.",
                                        "Your answer has to have more details and be longer than the input answer.",
                                        "If it is not possible to add more details, rephrase the given input answer making it longer.",
                                        "The previous answer to be expanded:",
                                        f"```{prev_answer}```",
                                        ""])
        return _instruction


    # --- LLM Calls -----------------------------------------------------------------------------------------------------------------------
    async def generate_chat_name(self, chat_history: List[ChatMessage]) -> str:
        """
        Generates a name for the chat.
        """
        self.logger.info(f"Generating chat name...")
        user_query = chat_history[-1].content
        if len(user_query) > 400:
            user_query = user_query[:200] + " [...] " + user_query[-200:]
        _prompt = self.prompt_manager.get_prompt(prompt_name="GENERATE_CHAT_NAME", user_query=user_query)
        _generated_name = await self._complete(prompt=_prompt)
        return _generated_name if _generated_name else "Chat"


    async def rewrite_user_query(self, conversation: str):
        """
        Generates a concise chat name from the user's query using an LLM
        """
        try:
            _prompt = self.prompt_manager.get_prompt(prompt_name="REWRITE_QUERY", conversation=str(conversation))
            return await self._complete(prompt=_prompt)
        except Exception as e:
            raise e
        

    @staticmethod
    def get_model_name_from_llm(
        llm_client: Union[OpenAI, AzureOpenAI, Ollama, GoogleGenAI, HuggingFaceLLM]
    ) -> str:
        if isinstance(llm_client, AzureOpenAI):
            return llm_client.engine
        if isinstance(llm_client, HuggingFaceLLM):
            return llm_client.model_name
        return llm_client.model


    # --- LLM Processing -----------------------------------------------------------------------------------------------------------------------
    def save_tokens(self, input_tokens: int, output_tokens: int, label: str):
        """Log token usage and save it to the database."""
        self.logger.info(f"Label: {label} - Input tokens: {input_tokens} - Output tokens: {output_tokens}")
        try:
            self.token_manager.save(
                user=self.user,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                llm_model=self.get_model_name_from_llm(self._llm),
                provider=self._provider,
                label=label,
            )
        except Exception as e:
            self.logger.warning(f"Could not save tokens to PostgreSQL due to {str(e)}")
        # Update instance token counts
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens


    async def _handle_llm_exception(self, exc: Exception, attempt: int, label: str):
        """Handle exceptions from the LLM call, with specific logic for retries."""
        if isinstance(exc, (APITimeoutError, RateLimitError)):
            # Specific handling for token-based rate limits: switch to a fallback LLM
            if "token" in str(exc) and isinstance(self.helper_llm, Ollama):
                self.logger.warning("Token RateLimit hit! Retrying with local LLM...")
                self._llm = self.helper_llm
            else:
                retry_time = getattr(exc, "retry_after", 10 * (attempt + 1))
                self.logger.warning(f"RateLimit exceeded. Retrying in {retry_time}s...")
                await asyncio.sleep(retry_time)
        elif "ResponsibleAIPolicyViolation" in str(exc):
            self.logger.error(f"AIPolicyViolation: Cannot retry. Error: {exc}")
            raise exc
        elif "PydanticError" in str(exc):
            self.logger.error(f"Error compiling obj '{label}': {exc}") #TODO CHeck error str 
            raise exc
        else:
            self.logger.warning(f"An unexpected error occurred on attempt {attempt + 1}: {exc}. Retrying...")
            await asyncio.sleep(5)


    async def _process_llm_stream(self, stream: Any) -> AsyncGenerator[str, None]:
        """Asynchronously process the LLM stream and clean the output."""
        completion = ""
        async for chunk in stream:
            delta = chunk.delta if hasattr(chunk, 'delta') else str(chunk)
            completion += delta
            if isinstance(self._llm, Ollama):
                cleaned = re.sub(r"<think>.*?</think>", "", completion, flags=re.DOTALL).strip()
                yield cleaned
            else:
                yield completion


    async def _structured_output(self, output_model: BaseModel, prompt: str = "", messages: List[ChatMessage] = "", label: str = "") -> BaseModel:
        program = LLMTextCompletionProgram.from_defaults(
            output_parser=PydanticOutputParser(output_cls=output_model),
            prompt_template_str=str(prompt) + str(messages),
            llm=self._llm
        )
        return await program.acall()

    async def _execute_llm_call(self,
                                messages: List[ChatMessage] = None,
                                prompt: str = None,
                                streaming: bool = False,
                                output_model: BaseModel = None,
                                label: str = None
                                ) -> AsyncGenerator[str, None]:
        """
        Execute an LLM call with retry logic. 
        Yields the full accumulated text at each step if streaming, 
        or the final text once if not streaming.
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
        completion = ""
        
        # 1. Isolate the LLM call and retries
        for attempt in range(self.max_retry):
            try:
                if not output_model:
                    if streaming:
                        stream = await self._llm.astream_chat(messages=messages)
                        async for chunk in self._process_llm_stream(stream):
                            completion = chunk
                            yield completion
                    else:
                        if not prompt:
                            response = await self._llm.achat(messages=messages)
                            completion = response.message.content
                        else:
                            response = await self._llm.acomplete(prompt=prompt)
                            completion = response.text
                        yield completion
                else:
                    completion = await self._structured_output(prompt=prompt, messages=messages, output_model=output_model, label=label)
                    yield completion
                
                # If we reached here, the LLM call succeeded. Break the retry loop!
                break 
                
            except Exception as exc:
                last_exc = exc
                await self._handle_llm_exception(exc, attempt, label)
        else:
            self.logger.error("Max retries reached.")
            raise RuntimeError("LLM call failed.") from last_exc

        # 2. Handle post-processing safely outside the retry loop
        try:
            # Extract only text to avoid heavy Pydantic stringification
            input_content = prompt or ""
            if messages:
                input_content += " ".join([m.content for m in messages if m.content])
            if output_model:
                input_content += str(output_model.model_json_schema()) 
                
            # Run synchronous CPU-bound token counting in a separate thread
            input_tokens = await asyncio.to_thread(self.tokenizer.count, input_content)
            output_tokens = await asyncio.to_thread(self.tokenizer.count, str(completion))
            
            # Save tokens (Assuming this does network I/O, you might want to run this in a thread too if it's not native async)
            self.save_tokens(input_tokens, output_tokens, label=label)
        except Exception as e:
            self.logger.error(f"Failed to calculate or save tokens: {e}")

    async def ____execute_llm_call(self,
                                messages: List[ChatMessage] = None,
                                prompt: str = None,
                                streaming: bool = False,
                                output_model: BaseModel = None,
                                label: str = None
                                ) -> AsyncGenerator[str, None]:
        """
        Execute an LLM call with retry logic. 
        Yields the full accumulated text at each step if streaming, 
        or the final text once if not streaming.
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
                            stream = await self._llm.astream_chat(messages=messages)
                        else:
                            stream = await self._llm.astream_complete(prompt=prompt)
                        async for chunk in self._process_llm_stream(stream):
                            completion = chunk
                            yield completion
                    else:
                        if not prompt:
                            response = await self._llm.achat(messages=messages)
                            completion = response.message.content
                        else:
                            response = await self._llm.acomplete(prompt=prompt)
                            completion = response.text
                        yield completion

                else:
                    completion = await self._structured_output(prompt=prompt, messages=messages, output_model=output_model, label=label)
                    yield completion

                input_content = str(prompt) + str(messages) + str(output_model.model_json_schema()) if output_model else str(prompt) + str(messages)
                input_tokens = self.tokenizer.count(input_content)
                output_tokens = self.tokenizer.count(str(completion))
                self.save_tokens(input_tokens, output_tokens, label=label)
                return
            except Exception as exc:
                last_exc = exc
                await self._handle_llm_exception(exc, attempt, label)
        self.logger.error(f"Max retries ({self.max_retry}) reached for '{label}'. Last error: {last_exc}", exc_info=True)
        raise RuntimeError("LLM call failed after maximum retries.") from last_exc
    
    
    @DebugLogger.profile
    async def _complete(self,
                        prompt: Union[str, RichPromptTemplate],                    
                        label: Optional[str] = None,
                        streaming: bool = False,
                        output_model: BaseModel = None,
                        ) -> Union[str, AsyncGenerator[str, None]]:
        """
        Generates a complete operation using the LLM.
        Returns a string if streaming=False, or an AsyncGenerator if streaming=True.
        """
        if isinstance(prompt, RichPromptTemplate):
            if not label:
                label = prompt.metadata["prompt_name"]
            prompt = prompt.format()

        generator = self._execute_llm_call(prompt=prompt, label=label, streaming=streaming, output_model=output_model)
        
        if streaming:
            return generator
        else:
            final_result = ""
            async for partial in generator:
                final_result = partial
            return final_result


    @DebugLogger.profile
    async def _chat(self,
                    messages: List[ChatMessage],
                    prompt: Union[str, RichPromptTemplate] = None,
                    label: Optional[str] = None,
                    streaming: bool = False,
                    output_model: BaseModel = None,
                    ) -> Union[str, AsyncGenerator[str, None]]:
        """
        Executes a chat completion call to the LLM.
        Returns a string if streaming=False, or an AsyncGenerator if streaming=True.
        """
        if prompt:
            if isinstance(prompt, RichPromptTemplate):
                if not label:
                    label = prompt.metadata["prompt_name"]
                prompt = prompt.format()
            messages = [ChatMessage(role="system", content=prompt)] + messages 

        generator = self._execute_llm_call(messages=messages, label=label, streaming=streaming, output_model=output_model)

        if streaming:
            return generator
        else:
            final_result = ""
            async for partial in generator:
                final_result = partial
            return final_result