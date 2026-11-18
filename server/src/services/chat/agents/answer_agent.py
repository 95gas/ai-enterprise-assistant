from typing import List, Dict
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.workflow import (
    Context,
    step,
    StartEvent,
    StopEvent
)

from src.services.chat.schema import Source
from src.services.chat.workflows.base import BaseWorkflow
from src.services.chat.agents.base_agent import AgentStream


class CustomStopEvent(StopEvent):
    response: str
    cited_sources: List[Source]
    input_tokens: int
    output_tokens: int


class AnswerAgent(BaseWorkflow):
    name = "AnswerAgent"
    description = "Useful to reply directly to the user. If any action has been taken, include a brief summary in the input message."
    
    @step
    async def agent_start(self, ctx: Context, ev: StartEvent) -> CustomStopEvent:
        """
        Entry point and start of the workflow.
        Reads the passed parameters and saves them into the context.
        """
        chat_history: List[ChatMessage] = ev.state.get("initial_chat_history")
        retrieved_sources: List[Source] = ev.state.get("retrieved_sources")
        produced_contents: List[Source] = ev.state.get("produced_contents")
        provided_sources: List[Source] = ev.state.get("provided_sources")
        recorded_notes: Dict[str, str] = ev.state.get("recorded_notes")
        prev_answer: ChatMessage | None = ev.state.get("prev_answer")
        internal_knowledge: bool = ev.state.get("internal_knowledge") 
        instruction: str | None = ev.state.get("instruction")
        web_search: bool = ev.state.get("web_search")
        doc_search: bool = ev.state.get("doc_search")
        input_text: str = ev.get("input_text") 

        lst_sources = retrieved_sources + provided_sources + produced_contents

        instruction = self.compile_instruction(internal_knowledge=internal_knowledge, 
                                               provided_sources=provided_sources,
                                               prev_answer=prev_answer,
                                               web_search=web_search,
                                               doc_search=doc_search)
        sources_with_ids = self.add_id_to_sources(lst_sources=lst_sources, 
                                                  chat_history=chat_history, 
                                                  prev_answer=prev_answer)
        _prompt = self.prompt_manager.get_prompt(prompt_name="ANSWER",
                                                 instruction=instruction,
                                                 recorded_notes_str=self.format_recorded_notes_to_str(recorded_notes=recorded_notes),
                                                 sources_str=self.format_sources_to_str(sources_with_ids=sources_with_ids))

        response_stream = await self._chat(prompt=_prompt, 
                                           messages=chat_history, # + [ChatMessage(role="user", content=input_text)], # TODO Implement in system prompt
                                           streaming=True)
        answer = ""
        async for response_completion in response_stream:
            answer = response_completion
            if isinstance(response_completion, str):
                ctx.write_event_to_stream(AgentStream(msg=response_completion))

        cited_sources = self.check_referenced_sources(answer=str(answer), sources=sources_with_ids)  

        return CustomStopEvent(response=str(answer),
                               cited_sources=cited_sources,
                               input_tokens=self.input_tokens,
                               output_tokens=self.output_tokens)