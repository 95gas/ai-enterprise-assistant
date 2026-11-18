import inspect, uuid
from typing import List, Dict, Literal

from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    step,
)

from src.services.chat.schema import Source
from src.services.chat.workflows.base import Summary
from src.services.chat.agents.base_agent import BaseAgentWorkflow, AgentStream, PlanTools


class InputEvent(Event):
    chat_history: List[ChatMessage]

class ExecuteEvent(Event):
    curr_plan: PlanTools
    chat_history: List[ChatMessage]

class ReviewEvent(Event):
    chat_history: List[ChatMessage]

class OutputEvent(Event):
    response: str

class CustomStopEvent(StopEvent):
    response: str
    produced_content: Source | None
    input_tokens: int
    output_tokens: int


class ReportAgent(BaseAgentWorkflow):
    name = "ReportAgent"
    description = "Useful to write a report. Can work only on a single report at the time."

    @step
    async def agent_start(self, ctx: Context, ev: StartEvent) -> InputEvent | OutputEvent:
        chat_history = [ChatMessage(role="user", content=ev.input_text)] 
        tools = self.get_tools([self.read_document,
                                self.write_document, 
                                self.save_document, 
                                self.compile_pdf_from_tex])

        report_type: Literal["r&d", "free"] = ev.state.get("report_type", "r&d") # TODO Implement again
        provided_sources: List[Source] = ev.state.get("provided_sources") # TODO Perhaps add retrieved_sources
        if not provided_sources:     
            return OutputEvent(response="The data to fill the report need to be provided in order to write a report.")

        provided_sources_str = self.format_sources_to_str(provided_sources)
        instruction = " "
        
        recorded_notes: Dict[str, str] = ev.state.get("recorded_notes") 
        
        state = {"provided_sources_str": provided_sources_str,
                 "produced_content": None}
        await ctx.store.set("state", state)
        await ctx.store.set("recorded_notes", recorded_notes)
        await ctx.store.set("instruction", instruction)
        await ctx.store.set("tools", tools)
        await ctx.store.set("steps_taken", 0)
        await ctx.store.set("max_steps", 0)
        self.logger.info(f"{self.name} started...'")
        return InputEvent(chat_history=chat_history)
    
    
    @step
    async def agent_input(self, ctx: Context, ev: InputEvent) -> ExecuteEvent | OutputEvent:
        chat_history = ev.chat_history
        tools = await ctx.store.get("tools")
        instruction = await ctx.store.get("instruction")
        recorded_notes = await ctx.store.get("recorded_notes")

        try:
            _prompt = self.prompt_manager.get_prompt(prompt_name="PLANNER_TOOLS", 
                                                     tools_str=self.format_tools_to_str(tools),
                                                     instruction=instruction,
                                                     recorded_notes_str=self.format_recorded_notes_to_str(recorded_notes))
            response = await self._chat(prompt=_prompt, 
                                        messages=chat_history,
                                        output_model=PlanTools,
                                        streaming=False)
            chat_history.append(ChatMessage(role="assistant", content=str(response)))

            self.logger.debug(f"{self.name} CHAT_HISTORY:")
            self.logger.debug(f"PROMPT:\n{str(_prompt)}")
            for i,m in enumerate(chat_history):
                self.logger.debug(f"[{i}]:\t{str(m)}")

            return ExecuteEvent(curr_plan=response, chat_history=chat_history)

        except Exception as e:
            error_str = f"Error encounted during task completion: {e}"
            self.logger.error(error_str)
            assessment = chat_history[-1].content
            return OutputEvent(response=assessment if isinstance(ev, ReviewEvent) else error_str) # error response is the last assessment


    @step
    async def agent_execute(self, ctx: Context, ev: ExecuteEvent) -> ReviewEvent:
        chat_history = ev.chat_history
        curr_plan = ev.curr_plan
        tools = await ctx.store.get("tools", default=[])

        for step in curr_plan.steps:
            tool_name = step.tool_name.lower()
            tool_input = step.tool_input or {}
            tool_call_id = str(uuid.uuid4())[:4]

            selected_tool = tools.get(tool_name.lower())
            if selected_tool:
                chat_history.append(ChatMessage(role="assistant",
                                                content=None,
                                                additional_kwargs={"tool_calls": [{"id": tool_call_id,
                                                                                   "type": "function",
                                                                                   "function": {"name": tool_name,
                                                                                                "arguments": str(tool_input)}}]}))
            else:
                error_str = f"Unrecognized tool_name: '{tool_name}'"
                self.logger.warning(error_str)
                chat_history.append(ChatMessage(role="assistant", content=error_str))
                continue

            streaming_msg = f"Tool: {tool_name} - Input: {tool_input}\n"
            ctx.write_event_to_stream(AgentStream(step=streaming_msg))
            try:
                async with ctx.store.edit_state() as ctx_state:
                    result = selected_tool["fn"](state=ctx_state["state"], **tool_input)
                    response = await result if inspect.isawaitable(result) else result
            except Exception as e:
                response = f"Error running tool '{tool_name}': {str(e)}"
                self.logger.warning(response)
                
            chat_history.append(ChatMessage(role="tool", 
                                            content=response,
                                            additional_kwargs={"name": tool_name, "tool_call_id": tool_call_id}))
        return ReviewEvent(chat_history=chat_history)


    @step
    async def agent_review(self, ctx: Context, ev: ReviewEvent) -> InputEvent | OutputEvent:
        chat_history = ev.chat_history
        try:
            user_msg = self.prompt_manager._fetch_prompt("STEPS_SUMMARY")
            response = await self._chat(messages=chat_history + [ChatMessage(role="user", content=user_msg)],
                                        streaming=False,
                                        label="STEPS_SUMMARY",
                                        output_model=Summary)
            agent_summary = response.summary
            agent_assessment = response.assessment
        except Exception as e:
            self.logger.error(f"STEPS_SUMMARY response badly formatted: {e}")
            agent_summary = f"This is what I've done:\n{chat_history}"
            agent_assessment = "CONTINUE"

        steps_taken = await ctx.store.get("steps_taken")
        if steps_taken >= await ctx.store.get("max_steps") or agent_assessment.lower() == "STOP".lower():

            chat_history.append(ChatMessage(role="user", content=agent_summary)) # TODO Remove these two lines
            self.logger.warning(str(chat_history))

            return OutputEvent(response=agent_summary)
        
        else:
            await ctx.store.set("steps_taken", steps_taken + 1)
            self.logger.info(f"STEPS TAKEN: {steps_taken}")
            chat_history.append(ChatMessage(role="user", content=agent_summary))
            return InputEvent(chat_history=chat_history)


    @step
    async def agent_response(self, ctx: Context, ev: OutputEvent) -> CustomStopEvent:
        state = await ctx.store.get("state", {})
        return CustomStopEvent(response=ev.response,
                               produced_content=state.get("produced_content"),
                               input_tokens=self.input_tokens,
                               output_tokens=self.output_tokens)