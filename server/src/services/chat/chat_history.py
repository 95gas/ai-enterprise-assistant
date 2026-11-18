from typing import Dict, Any, List, Optional

from llama_index.core.prompts import MessageRole
from llama_index.core.base.llms.types import ChatMessage

from src.common.models.tokenizer import TokenCounter
from src.common.logging.logger import DebugLogger
from src.services.chat.schema import Source
from config.settings import settings

MODELS_INFO_DICT = settings.models_info.model_dump()
CHAT_HISTORY_BUFFER_SIZE = settings.CHAT_HISTORY_BUFFER_SIZE


class ChatHistoryManager:
    """
    Manages the chat history, allowing for adding, updating, resetting, and initializing chat messages.
    """

    def __init__(self,
                 buffer_size: Optional[int] = None,
                 user: Optional[str] = None,
                 logger: Optional[DebugLogger] = None) -> None:
        """
        Initializes the chat history manager.
        :param buffer_size: The maximum number of tokens to store in the memory buffer.
        """
        self.logger = logger or DebugLogger(user=user,
                                            class_name=self.__class__.__name__,
                                            main_feature="CHAT")
        self.chat_history: Optional[List[ChatMessage]] = []
        self.buffer_size = buffer_size
        self.logger.success("ChatHistoryManager initialized successfully.")


    def _create_user_message(self, user_query: str, **kwargs) -> ChatMessage:
        add_kwargs = dict()
        selected_documents = kwargs.get("selected_documents", None)
        if selected_documents:
            if isinstance(selected_documents, list):
                add_kwargs["documents"] = selected_documents
            else:
                raise TypeError("selected_documents must be a list of strings")
        return ChatMessage(content=user_query, role=MessageRole.USER, additional_kwargs=add_kwargs)


    def set_history(self, messages: Optional[List[ChatMessage]]) -> None:
        """
        Sets the chat history.
        :param messages: A list of ChatMessage objects.
        """
        self.logger.info("Setting new chat history...")
        self.chat_history = messages
        self.logger.success("Chat history set successfully.")


    def get_history(self) -> Optional[List[ChatMessage]]:
        """
        Retrieves the current chat history.
        :return: A list of ChatMessage objects or None if no history exists.
        """
        self.logger.info("Fetching chat history...")
        if self.chat_history:
            history_size = len(self.chat_history)
            self.logger.info(f"Chat history contains {history_size} messages.")
        else:
            self.logger.info("No chat history available.")
        return self.chat_history
    

    def initialize_history(self, messages: List[Dict[str, Any]] | List[ChatMessage] = []) -> None:
        """
        Initializes the chat history with a given list of messages.
        :param messages: A list of message dictionaries with keys 'role', 'content', and optionally 'sources' or 'documents'.
        """
        self.logger.info("Initializing chat history...")
        tokenizer = TokenCounter(logger=DebugLogger(user=self.logger.user, 
                                                    class_name=self.__class__.__name__, 
                                                    main_feature="DOC"),
                                 provider=MODELS_INFO_DICT["helper_model"]["provider"],
                                 model_name=MODELS_INFO_DICT["helper_model"]["custom_name"])
        
        self.logger.success(f"Retrieved conversation with {len(messages)} messages from the database.")
        entire_chat_history = [self.message_to_chat_message(message) for message in messages]
        chat_history = self.apply_buffer_to_entire_chat_history(entire_chat_history=entire_chat_history,
                                                                tokenizer=tokenizer)
        self.set_history(chat_history)
        self.logger.success(f"Chat history initialized with {len(chat_history)} messages.")
        

    @staticmethod
    def apply_buffer_to_entire_chat_history(entire_chat_history: List[ChatMessage],
                                            tokenizer: TokenCounter = None) -> List[ChatMessage]:
        if tokenizer:
            counting_fn = tokenizer.count
        else:
            counting_fn = lambda x: len(x) // 4

        tot_tokens = 0
        _chat_history = []
        for msg in entire_chat_history[::-1]:
            tot_tokens += counting_fn(str(msg))
            if tot_tokens < CHAT_HISTORY_BUFFER_SIZE:
                _chat_history.insert(0, msg)
            else:
                break
        return _chat_history
            

    def message_to_chat_message(self, message: Dict[str, Any] | ChatMessage) -> List[ChatMessage]:
        """
        Converts a list of message dictionaries or ChatMessage objects into ChatMessage instances.
        """
        additional_kwargs = {}
        if isinstance(message, dict):
            if message.get("sources"):
                try:
                    lst_dicts = []
                    for entry in message["sources"]:
                        filename = entry.get("filename")
                        src_type = entry.get("type")
                        references = entry.get("references", [])
                        for ref in references:
                            ref["filename"] = filename
                            ref["type"] = src_type
                            lst_dicts.append(ref)

                    additional_kwargs["sources"] = []
                    for d in lst_dicts:
                        try:
                            additional_kwargs["sources"].append(Source(**d).model_dump(exclude_none=True))
                        except Exception as e:
                            self.logger.error(f"Error creating Source instance: {e}")
                except Exception as e:
                    self.logger.error(f"Error reading source from chat_history: {e}")

            return ChatMessage(role=message["role"],
                               content=message["content"],
                               additional_kwargs=additional_kwargs)
        elif not isinstance(message, ChatMessage):
            self.logger.error(f"Message type not recognized: {type(message)}")
        return message