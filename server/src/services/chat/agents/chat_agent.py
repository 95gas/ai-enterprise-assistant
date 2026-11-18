from typing import List, Dict
import time
import uuid
from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import (Context,
                                       Event,
                                       StartEvent,
                                       StopEvent,
                                       step)

from src.services.chat.schema import Source
from src.services.chat.workflows.base import StreamingEvent
from src.services.chat.agents.base_agent import BaseAgentWorkflow, PlanAgents


class InputEvent(Event):
    chat_history: List[ChatMessage]

class GenerateChatNameEvent(Event):
    generate_chat_name: bool

class ExecuteEvent(Event):
    curr_plan: PlanAgents
    chat_history: List[ChatMessage]

class ReviewEvent(Event):
    chat_history: List[ChatMessage]

class AnswerEvent(Event):
    notes: str = None

class CustomStopEvent(StopEvent):
    response: str
    sources: List[Source]
    input_tokens: int
    output_tokens: int
    llm_model: str
    chat_name: str | None
    recorded_notes: Dict[str, str] | None


class ChatAgent(BaseAgentWorkflow):
    name = "ChatAgent"
    
    @step
    async def orchestrator_start(self, ctx: Context, ev: StartEvent) -> GenerateChatNameEvent | InputEvent:
        """
        Entry point and start of the workflow.
        Reads the passed parameters and stores them into the context.
        """
        chat_history = ev.chat_history

        state = {"initial_chat_history": ev.chat_history.copy(),
                 "recorded_notes": ev.recorded_notes,
                 "prev_answer": ev.prev_answer,
                 "internal_knowledge": ev.internal_knowledge,
                 "web_search": ev.web_search,
                 "doc_search": ev.doc_search,
                 "retrieved_sources": [],
                 "provided_sources": ev.provided_sources,
                 "report_type": ev.report_type,
                 "produced_contents": [],
                 }

        instruction = self.compile_instruction(internal_knowledge=ev.internal_knowledge, 
                                               provided_sources=ev.provided_sources,
                                               prev_answer=ev.prev_answer,
                                               web_search=ev.web_search,
                                               doc_search=ev.doc_search)

        await ctx.store.set("state", state)
        await ctx.store.set("instruction", instruction)
        await ctx.store.set("agents", self.current_agents)
        await ctx.store.set("max_steps", 2)
        await ctx.store.set("steps_taken", 0)
        ctx.send_event(GenerateChatNameEvent(generate_chat_name=ev.generate_chat_name))
        return InputEvent(chat_history=chat_history)


    @step
    async def orchestrator_generate_chat_name(self, ctx: Context, ev: GenerateChatNameEvent) -> AnswerEvent:
        """
        Generates a name for the chat.
        """
        async with ctx.store.edit_state() as ctx_state:
            if ev.generate_chat_name:
                ctx.write_event_to_stream(StreamingEvent(step_id="GenerateChatNameEvent"))
                chat_name = await self.generate_chat_name(chat_history=ctx_state["state"]["initial_chat_history"])
            else:
                chat_name = None
            ctx_state["state"]["chat_name"] = chat_name
        return AnswerEvent()


    @step
    async def orchestrator_input(self, ctx: Context, ev: InputEvent) -> ExecuteEvent | AnswerEvent:
        chat_history = ev.chat_history
        agents = await ctx.store.get("agents")
        instruction = await ctx.store.get("instruction")
        state = await ctx.store.get("state", {})
        recorded_notes = state.get("recorded_notes")
        provided_sources = state.get("provided_sources")
        retrieved_sources = state.get("retrieved_sources")
        produced_contents = state.get("produced_contents")

        prompt = self.prompt_manager.get_prompt(prompt_name="PLANNER_AGENTS",
                                                agents_str=self.format_agents_to_str(agents),
                                                instruction=instruction,
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
            
            self.logger.debug(f"{self.name} chat_history:")
            for i,m in enumerate(chat_history):
                self.logger.debug(f"[{i}]:\t{m}")

            return ExecuteEvent(curr_plan=response,
                                chat_history=chat_history)
        
        except Exception as e:
            self.logger.error(f"Error generating ChatAgent plan: {e}")
            assessment = chat_history[-1].content
            return AnswerEvent(notes=assessment if isinstance(ev, ReviewEvent) else "There's been an error processing the answer. Please try again")


    @step
    async def orchestrator_execute(self, ctx: Context, ev: ExecuteEvent) -> ReviewEvent | AnswerEvent:
        chat_history = ev.chat_history
        plan = ev.curr_plan
        agents = await ctx.store.get("agents")
        for step in plan.steps:
            input_text = step.agent_task
            if step.agent_name == "AnswerAgent":
                progress_id = str(uuid.uuid4())
                await ctx.store.set("answer_progress", {
                    "id": progress_id,
                    "started": time.perf_counter(),
                })
                ctx.write_event_to_stream(StreamingEvent(
                    progress_id=progress_id,
                    progress_phase="start",
                    progress_agent="AnswerAgent",
                ))
                return AnswerEvent(notes=input_text)
            elif step.agent_name in [agent_name for agent_name in agents]:
                self.logger.info(f"[{step.agent_name}] Running...")
                progress_id = str(uuid.uuid4())
                started = time.perf_counter()
                ctx.write_event_to_stream(StreamingEvent(
                    progress_id=progress_id,
                    progress_phase="start",
                    progress_agent=step.agent_name,
                ))
                try:
                    agent_resp = await self.call_agent_workflow(
                        agent_name=step.agent_name,
                        ctx=ctx,
                        input_text=input_text,
                    )
                except Exception:
                    ctx.write_event_to_stream(StreamingEvent(
                        progress_id=progress_id,
                        progress_phase="error",
                        progress_agent=step.agent_name,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    ))
                    raise
                ctx.write_event_to_stream(StreamingEvent(
                    progress_id=progress_id,
                    progress_phase="complete",
                    progress_agent=step.agent_name,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                ))
                msg = f"[{step.agent_name}] Task: {input_text}\nResponse: {agent_resp}"
                self.logger.success(msg)
            else:
                msg = f"Unrecognized agent name: {step.agent_name}"
                self.logger.error(msg)
            chat_history.append(ChatMessage(role="assistant", content=msg))
        return ReviewEvent(chat_history=chat_history)


    @step
    async def orchestrator_review(self, ctx: Context, ev: ReviewEvent) -> InputEvent | AnswerEvent:
        chat_history = ev.chat_history
        steps_taken = await ctx.store.get("steps_taken") + 1
        if steps_taken >= await ctx.store.get("max_steps"):
            user_msg = "Summarize all the steps you have taken and the results."
            response = await self._chat(messages=chat_history + [ChatMessage(role="user", content=user_msg)],
                                        streaming=False,
                                        label="ORCHESTRATOR_SUMMARY")
            return AnswerEvent(notes=response)
        
        else:
            await ctx.store.set("steps_taken", steps_taken)
            self.logger.info(f"STEPS TAKEN: {steps_taken}")
            return InputEvent(chat_history=chat_history)
        """
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
            agent_assessment = "STOP"
        steps_taken = await ctx.store.get("steps_taken") + 1
        if steps_taken >= await ctx.store.get("max_steps") or agent_assessment.upper() == "STOP":
            return AnswerEvent(notes=agent_summary)
        
        else:
            await ctx.store.set("steps_taken", steps_taken)
            self.logger.info(f"STEPS TAKEN: {steps_taken}")
            chat_history.append(ChatMessage(role="user", content=agent_summary))
            return InputEvent(chat_history=chat_history)
        """


    @step
    async def orchestrator_response(self, ctx: Context, ev: AnswerEvent) -> CustomStopEvent | None:
        evs = ctx.collect_events(ev, [AnswerEvent] * 2)
        if evs is None:
            return
        notes = "\n".join([ev.notes for ev in evs if ev.notes])
       
        progress = await ctx.store.get("answer_progress", None)
        agent_resp = await self.call_agent_workflow(
            agent_name="AnswerAgent",
            ctx=ctx,
            input_text=notes if notes else "Answer the user.",
        )
        if progress:
            ctx.write_event_to_stream(StreamingEvent(
                progress_id=progress["id"],
                progress_phase="complete",
                progress_agent="AnswerAgent",
                duration_ms=int((time.perf_counter() - progress["started"]) * 1000),
            ))

        state = await ctx.store.get("state")
        return CustomStopEvent(response=agent_resp,
                               sources=state["cited_sources"],
                               input_tokens=self.input_tokens,
                               output_tokens=self.output_tokens,
                               llm_model=self.get_model_name_from_llm(self._llm),
                               chat_name=state["chat_name"],
                               recorded_notes=state["recorded_notes"]
                               )