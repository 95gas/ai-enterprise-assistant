from typing import List
from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    step
)

from src.services.chat.agents.base_agent import BaseAgentWorkflow, PlanAgents
from src.services.chat.workflows.base import StreamingEvent
from src.services.chat.schema import Source


class InputEvent(Event):
    chat_history: List[ChatMessage]

class ExecuteEvent(Event):
    curr_plan: PlanAgents
    chat_history: List[ChatMessage]

class ReviewEvent(Event):
    chat_history: List[ChatMessage]

class OutputEvent(Event):
    response: str

class GenerateChatNameEvent(Event):
    generate_chat_name: bool

class FinalAnswerEvent(Event):
    notes: str = None

class CustomStopEvent(StopEvent):
    answer: str
    sources: List[Source]
    input_tokens: int
    output_tokens: int
    llm_model: str
    chat_name: str | None


class UserSupportAgent(BaseAgentWorkflow):
    @step
    async def orchestrator_start(self, ctx: Context, ev: StartEvent) -> GenerateChatNameEvent | InputEvent | FinalAnswerEvent:
        """
        Entry point and start of the workflow.
        Reads the passed parameters and saves them into the context.
        """
        chat_history = ev.chat_history
        state = {"retrieved_sources": [],
                 "recorded_notes": ev.recorded_notes,
                 "initial_chat_history": ev.chat_history.copy(),
                 "internal_knowledge": ev.internal_knowledge,
                 "web_search": ev.web_search,
                 "doc_search": ev.doc_search,
                 "produced_contents": [],
                 }
        await ctx.store.set("state", state)

        ctx.send_event(GenerateChatNameEvent(generate_chat_name=ev.generate_chat_name))

        self.set_current_agents(["AnswerAgent", "ResearchAgent", "TicketAgent"])

        instruction = self.compile_instruction(internal_knowledge=ev.internal_knowledge, 
                                               provided_sources=ev.provided_sources,
                                               prev_answer=ev.prev_answer,
                                               web_search=ev.web_search,
                                               doc_search=ev.doc_search)

        await ctx.store.set("agents", self.current_agents)
        await ctx.store.set("instruction", instruction)
        await ctx.store.set("max_steps", 1)
        await ctx.store.set("steps_taken", 0)
        return InputEvent(chat_history=chat_history, state=state)


    @step
    async def orchestrator_generate_chat_name(self, ctx: Context, ev: GenerateChatNameEvent) -> FinalAnswerEvent:
        """
        Generates a name for the chat.
        """
        ctx.write_event_to_stream(StreamingEvent(step_id="GenerateChatNameEvent"))
        async with ctx.store.edit_state() as ctx_state:
            if ev.generate_chat_name:
                chat_name = await self.generate_chat_name(chat_history=ctx_state["state"]["initial_chat_history"])
            else:
                chat_name = None
            ctx_state["state"]["chat_name"] = str(chat_name)
        return FinalAnswerEvent()


    @step
    async def orchestrator_input(self, ctx: Context, ev: InputEvent) -> ExecuteEvent | FinalAnswerEvent:
        chat_history = ev.chat_history
        state = await ctx.store.get("state")

        agents_str = "\n".join([f'<agent_name="{agent.name}">{agent.description}</agent>'
                                for agent in (await ctx.store.get("agents")).values()])
        instruction = await ctx.store.get("instruction")
        state = await ctx.store.get("state", {})
        recorded_notes = state.get("recorded_notes")
        provided_sources = state.get("provided_sources")
        retrieved_sources = state.get("retrieved_sources")
        produced_contents = state.get("produced_contents")

        prompt = self.prompt_manager.get_prompt(prompt_name="PLANNER_AGENTS",
                                                instruction=instruction,
                                                agents_str=agents_str,
                                                recorded_notes_str=self.format_recorded_notes_to_str(recorded_notes),
                                                provided_sources_str=", ".join([s.filename for s in provided_sources]) if provided_sources else "No source has been provided by the user.",
                                                retrieved_sources_str=", ".join([s.filename for s in retrieved_sources]) if retrieved_sources else "No source has been retrieved yet.",
                                                produced_contents_str=", ".join([s.filename for s in produced_contents]) if produced_contents else "No content has been produced yet."
                                                )
        try:
            response = await self._chat(prompt=prompt, 
                                        messages=chat_history,
                                        output_model=PlanAgents,
                                        streaming=False)
            chat_history.append(ChatMessage(role="assistant", content=str(response)))
            
            self.logger.debug(f"UserSupportAgent chat_history:")
            for i,m in enumerate(chat_history):
                self.logger.debug(f"{i}\t{m}")

            return ExecuteEvent(curr_plan=response,
                                chat_history=chat_history)

        except Exception as e:
            self.logger.error(f"Error generating UserSupport plan: {e}")
            assessment = chat_history[-1].content
            return FinalAnswerEvent(notes=assessment if isinstance(ev, ReviewEvent) else None)


    @step
    async def orchestrator_execute(self, ctx: Context, ev: ExecuteEvent) -> InputEvent | FinalAnswerEvent:
        chat_history = ev.chat_history
        plan = ev.curr_plan
        agents = await ctx.store.get("agents")
        for step in plan.steps:
            input_text = step.agent_task
            if step.agent_name == "AnswerAgent":
                return FinalAnswerEvent(notes=input_text)
            elif step.agent_name in [agent_name for agent_name in agents]:
                self.logger.info(f"Running agent: {step.agent_name}")
                response_dict = await self.call_agent(agent_name=step.agent_name,
                                                      ctx=ctx,
                                                      input_text=input_text)
                self.logger.debug(f"Agent response:\n{response_dict}")
                msg = f"Task completed: {step}\nAgent response: {response_dict['response']}"
            else:
                msg = f"Unrecognized agent name: {step.agent_name}"
                self.logger.error(msg)
            chat_history.append(ChatMessage(role="assistant", content=msg))
        return ReviewEvent(chat_history=chat_history)


    @step
    async def orchestrator_review(self, ctx: Context, ev: ReviewEvent) -> InputEvent | FinalAnswerEvent:
        chat_history = ev.chat_history
        steps_taken = await ctx.store.get("steps_taken")
        self.logger.debug(f"Step: {steps_taken}")
        await ctx.store.set("steps_taken", steps_taken + 1)
        if steps_taken > await ctx.store.get("max_steps"):
            return FinalAnswerEvent()
        else:
            msg_content = "I've completed the previous plan. Do you need to continue and plan more steps? If not, tell AnswerAgent to produce an answer."
            chat_history.append(ChatMessage(role="user", content=msg_content))
            return InputEvent(chat_history=chat_history)


    @step
    async def orchestrator_response(self, ctx: Context, ev: FinalAnswerEvent) -> CustomStopEvent | None:
        evs = ctx.collect_events(ev, [FinalAnswerEvent] * 2)
        if evs is None:
            return
        notes = "\n".join([ev.notes for ev in evs if ev.notes])
        
        agent_resp = await self._call_answer_agent(ctx=ctx, input_text=notes)
        self.input_tokens += agent_resp.input_tokens
        self.output_tokens += agent_resp.output_tokens

        state = await ctx.store.get("state")
        return CustomStopEvent(answer=state["answer"],
                               sources=state["cited_sources"],
                               input_tokens=self.input_tokens,
                               output_tokens=self.output_tokens,
                               llm_model=self._llm.model,
                               chat_name=state["chat_name"],
                               recorded_notes=state["recorded_notes"]
                               )