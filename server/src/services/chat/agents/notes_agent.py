import inspect, uuid
from typing import List, Dict

from llama_index.core.workflow import Context, Event
from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import (
    Context,
    StartEvent,
    StopEvent,
    step,
)

from src.services.chat.agents.base_agent import BaseAgentWorkflow, AgentStream, PlanTools
from config.settings import settings

CHAT_NOTES_MAX_SIZE = settings.CHAT_NOTES_MAX_SIZE


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
    recorded_notes: Dict[str, str]
    input_tokens: int
    output_tokens: int


class NotesAgent(BaseAgentWorkflow):
    name = "NotesAgent"
    description = ("Memory writing specialist. Trigger this agent only when the user provides "
                   "foundational information, preferences, or technical constraints that must "
                   "persist beyond the current message exchange.")
    @step
    async def agent_start(self, ctx: Context, ev: StartEvent) -> InputEvent:
        chat_history = [ChatMessage(role="user", content=ev.input_text)] 
        recorded_notes: Dict[str, str] = ev.state["recorded_notes"]

        tools = self.get_tools([self.record_note, 
                                self.delete_note])

        state = {"recorded_notes": recorded_notes}
        
        await ctx.store.set("state", state)
        await ctx.store.set("tools", tools)
        await ctx.store.set("steps_taken", 0)
        await ctx.store.set("max_steps", 0)
        self.logger.info(f"{self.name} with {len(state['recorded_notes'].keys())} existing notes.")
        return InputEvent(chat_history=chat_history)
    
    
    @step
    async def agent_input(self, ctx: Context, ev: InputEvent) -> ExecuteEvent | OutputEvent:
        chat_history = ev.chat_history
        tools = await ctx.store.get("tools")
        state = await ctx.store.get("state")
        try:
            _prompt = self.prompt_manager.get_prompt(prompt_name="PLANNER_TOOLS", 
                                                     tools_str=self.format_tools_to_str(tools),
                                                     instruction="",
                                                     recorded_notes_str=self.format_recorded_notes_to_str(state["recorded_notes"]))
            response = await self._chat(prompt=_prompt, 
                                        messages=chat_history,
                                        output_model=PlanTools,
                                        streaming=False)
            chat_history.append(ChatMessage(role="assistant", content=str(response)))

            self.logger.debug(f"{self.name} chat_history:")
            for i,m in enumerate(chat_history):
                self.logger.debug(f"[{i}]:\t{m}")

            return ExecuteEvent(curr_plan=response, chat_history=chat_history)

        except Exception as e:
            error_str = f"Error encounted during task completion: {e}"
            self.logger.error(error_str)
            return OutputEvent(response=error_str)


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
    async def agent_review(self, ctx: Context, ev: ReviewEvent) -> OutputEvent:
        state = await ctx.store.get("state")
        recorded_notes = state["recorded_notes"]
        agent_assessment = "Recorded notes have been updated."
        try:
            recorded_notes_str = self.format_recorded_notes_to_str(recorded_notes)
            if len(recorded_notes_str) > CHAT_NOTES_MAX_SIZE:
                _prompt = self.prompt_manager.get_prompt(prompt_name="REVIEW_NOTES")
                response = await self._chat(prompt=_prompt, 
                                            messages=[ChatMessage(role="user", content=recorded_notes_str)], 
                                            streaming=False,
                                            output_model=Dict[str, str])
                state["recorded_notes"] = {title: content for title, content in response.items()}
        except:
            agent_assessment = f"Error updating recorded notes."
        return OutputEvent(response=agent_assessment)


    @step
    async def agent_response(self, ctx: Context, ev: OutputEvent) -> CustomStopEvent:
        state = await ctx.store.get("state")
        return CustomStopEvent(response=ev.response,
                               recorded_notes=state["recorded_notes"],
                               input_tokens=self.input_tokens,
                               output_tokens=self.output_tokens)