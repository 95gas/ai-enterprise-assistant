import asyncio
from typing import List, Dict, Optional

from llama_index.core.workflow import (Context,
                                       step,
                                       StartEvent,
                                       Event,
                                       StopEvent)
from llama_index.core.schema import NodeWithScore

from src.services.chat.schema import Source
from src.services.chat.workflows.base import (BaseWorkflow,
                                                  StreamingEvent,
                                                  FinalAnswerEvent)


class GenerateChatNameEvent(Event):
    generate_chat_name: bool

class RetrieveEvent(Event):
    pass

class PartialAnswersEvent(Event):
    retrieved_nodes: List[NodeWithScore]

class MergeAnswersEvent(Event):
    answers_list: List[str]

class CustomStopEvent(StopEvent):
    response: str
    sources: List[Source]
    input_tokens: int
    output_tokens: int
    llm_model: str
    chat_name: str | None
    recorded_notes: Optional[Dict[str, str]] = None


class FocusModeWorkflow(BaseWorkflow):
    """
    StartEvent -> GenerateChatNameEvent -> RetrieveEvent -> PartialAnswersEvent -> MergeAnswersEvent
    -> FinalAnswerEvent
    """
    @step
    async def start_answer(self, ctx: Context, ev: StartEvent) -> GenerateChatNameEvent | RetrieveEvent:
        """
        Entry point and start of the workflow.
        Reads the passed parameters and saves them into the context.
        """
        chat_history = ev.chat_history
        prev_answer = ev.prev_answer
        recorded_notes = ev.recorded_notes
        await ctx.store.set("messages", [chat_history[-1]])
        await ctx.store.set("recorded_notes_str", self.format_recorded_notes_to_str(recorded_notes))
        await ctx.store.set("prev_answer", prev_answer)
        await ctx.store.set("chat_history", chat_history)
        ctx.send_event(GenerateChatNameEvent(generate_chat_name=ev.generate_chat_name))
        return RetrieveEvent()


    @step
    async def generate_chat_name_event(self, ctx: Context, ev: GenerateChatNameEvent) -> FinalAnswerEvent:
        """
        Generates a name for the chat.
        """
        if ev.generate_chat_name:
            ctx.write_event_to_stream(StreamingEvent(step_id="GenerateChatNameEvent"))
            chat_name = await self.generate_chat_name(chat_history=await ctx.store.get("chat_history"))
        else:
            chat_name = None
        await ctx.store.set("chat_name", chat_name)
        return FinalAnswerEvent()


    @step
    async def retrieve_nodes(self, ctx: Context, ev: RetrieveEvent) -> PartialAnswersEvent | FinalAnswerEvent:
        """Retrieves nodes and adds them to the context."""
        ctx.write_event_to_stream(StreamingEvent(step_id="RetrieveEvent"))
        self._retriever.set_focus_mode(True)
        retrieved_nodes = await self._get_nodes(extract_all=True)
        if retrieved_nodes:
            lst_sources = self.normalize_nodes_to_sources(retrieved_nodes)
            sources_with_ids = self.add_id_to_sources(lst_sources=lst_sources,
                                                      chat_history=await ctx.store.get("chat_history"),
                                                      prev_answer=await ctx.store.get("prev_answer"))
            await ctx.store.set("retrieved_sources", sources_with_ids)
            nodes_tokens = sum([n.node.metadata["tokens"] for n in retrieved_nodes])
            if nodes_tokens > self.max_context_window // 4:
                return PartialAnswersEvent(retrieved_nodes=retrieved_nodes)
            else:
                self.logger.info("No partial answers were required.")
                sources_str = self.format_sources_to_str(sources_with_ids=sources_with_ids)
        else:
            await ctx.store.set("retrieved_sources", [])
            sources_str = "No relevant nodes were found."  # Triggers only if selected docs have no nodes, which should be impossible
            self.logger.warning("No relevant nodes were found while using Focus Mode.")

        await ctx.store.set("sources_str", sources_str)
        return FinalAnswerEvent()
    

    def select_current_nodes(self, nodes: List[NodeWithScore]) -> List[NodeWithScore]:
        """
        Selects the nodes that can processed in a single batch, giving priority to nodes from the same document.
        The limit of tokens is taken as a function of the max_context_window size.
        :param nodes: list of NodeWithScore
        :return: list of NodeWithScore selected for the current batch
        """
        required_tokens = 0
        selected_nodes = []
        current_filenames = sorted(list(set([n.node.metadata["filename"] for n in nodes])))
        for filename in current_filenames:
            current_nodes = [n for n in nodes if n.node.metadata["filename"] == filename]
            current_nodes_tokens = sum([n.node.metadata["tokens"] for n in current_nodes])
            required_tokens += current_nodes_tokens
            if required_tokens < self.max_context_window // 4:
                selected_nodes.extend(current_nodes)
            elif current_nodes_tokens >= self.max_context_window // 4:
                required_tokens = 0
                selected_nodes = []
                for n in current_nodes:
                    if required_tokens < self.max_context_window // 4:
                        required_tokens += n.node.metadata["tokens"]
                        selected_nodes.append(n)
                    else:
                        return selected_nodes
            else:
                return selected_nodes
        return selected_nodes


    def create_batches_of_nodes(self, retrieved_nodes: List[NodeWithScore]) -> List[List[NodeWithScore]]:
        """
        Groups the retrieved_nodes into batches of nodes (until no node is left) to be feed to each prompt.
        :param retrieved_nodes: list of NodeWithScore
        :return: list of batches of NodeWithScore
        """
        batches = list()
        while retrieved_nodes:
            batch = self.select_current_nodes(retrieved_nodes)
            retrieved_nodes = [n for n in retrieved_nodes if n not in batch]
            batches.append(batch)
        return batches


    @step
    async def generate_answers_concurrently(self, ctx: Context,
                                            ev: PartialAnswersEvent) -> MergeAnswersEvent | FinalAnswerEvent:
        """
        Creates batches of nodes and generates partial answers concurrently, then it sends the list of partial answers
        to the MergeAnswersEvent.
        """
        self.logger.info(f"Generating partial answers...")
        ctx.write_event_to_stream(StreamingEvent(step_id="PartialAnswersEvent"))
        retrieved_nodes = ev.retrieved_nodes
        batches = self.create_batches_of_nodes(retrieved_nodes)
        if len(batches) == 1:  # Should not be triggered in this workflow thanks to the check in retrieve_nodes
            self.logger.warning("Focus Mode entered with only 1 batch. This is inefficient but valid.")

        self.logger.info(f"Processing {len(batches)} batches..")
        tasks = list()
        for batch_of_nodes_with_ids in batches:
            sources_str = self.format_sources_to_str(sources_with_ids=batch_of_nodes_with_ids)
            _prompt = self.prompt_manager.get_prompt(prompt_name="ANSWER_PARTIAL",
                                                     sources_str=sources_str,
                                                     recorded_notes_str=await ctx.store.get("recorded_notes_str"))
            tasks.append(self._chat(prompt=_prompt,
                                    messages=await ctx.store.get("messages")))
        answers_list = await asyncio.gather(*tasks)
        for a in answers_list:
            self.logger.warning(a)
        return MergeAnswersEvent(answers_list=answers_list)


    @step
    async def merge_answers(self, ctx: Context, ev: MergeAnswersEvent) -> MergeAnswersEvent | FinalAnswerEvent:
        """
        Merges all given answer in ev.answers_list until they can be computed in a single prompt.
        """
        self.logger.info("Merging partial answers...")
        answers = ev.answers_list

        label = "ANSWER_MERGE"
        prompts_batch = list()
        required_tokens = 0
        ans_batch = list()
        for ans in answers:
            ans_tokens = self.check_context_window_size(ans)
            required_tokens += ans_tokens
            if required_tokens < self.max_context_window // 4:
                ans_batch.append(ans)
            else:
                grouped_ans_str = "".join([f"ANSWER #{i}:\n{answer}\n\n" for i, answer in enumerate(ans_batch, 1)])
                prompt = self.prompt_manager.get_prompt(prompt_name=label,
                                                        recorded_notes_str=await ctx.store.get("recorded_notes_str"), 
                                                        grouped_answers_str=grouped_ans_str)
                prompts_batch.append(prompt)
                required_tokens = ans_tokens
                ans_batch = [ans]
        grouped_ans_str = "".join([f"ANSWER #{i}:\n{answer}\n\n" for i, answer in enumerate(ans_batch, 1)])
        prompt = self.prompt_manager.get_prompt(prompt_name=label,
                                                recorded_notes_str=await ctx.store.get("recorded_notes_str"), 
                                                grouped_answers_str=grouped_ans_str)
        prompts_batch.append(prompt)

        if len(prompts_batch) == 1:
            await ctx.store.set("prompt", prompts_batch[0])
            return FinalAnswerEvent()

        tasks = [self._chat(prompt=_prompt, 
                            messages=await ctx.store.get("messages")
                            ) for _prompt in prompts_batch]
        merged_answers = await asyncio.gather(*tasks)
        return MergeAnswersEvent(answers_list=merged_answers)


    @step
    async def generate_final_answer(self, ctx: Context, ev: FinalAnswerEvent) -> CustomStopEvent | None:
        """
        Given a prompt, generates the final answer with streaming, then it stops the workflow.
        """
        evs = ctx.collect_events(ev, [FinalAnswerEvent] * 2)
        if evs is None:
            return None

        _prompt = await ctx.store.get("prompt", None)
        if not _prompt:
            _prompt = self.prompt_manager.get_prompt(prompt_name="ANSWER",
                                                     recorded_notes_str=await ctx.store.get("recorded_notes_str"), 
                                                     sources_str=await ctx.store.get("sources_str"))

        # Iterate over the async stream of the answer generator
        response_stream = await self._chat(prompt=_prompt, messages=await ctx.store.get("chat_history"), streaming=True)
        answer = ""
        async for response_completion in response_stream:
            answer = response_completion
            if isinstance(response_completion, str):
                ctx.write_event_to_stream(StreamingEvent(msg=response_completion))

        # Check references
        sources = self.check_referenced_sources(answer=str(answer), sources=await ctx.store.get("retrieved_sources"))
        return CustomStopEvent(response=str(answer),
                               sources=sources,
                               input_tokens=self.input_tokens,
                               output_tokens=self.output_tokens,
                               llm_model=str(self._llm.model),
                               chat_name=await ctx.store.get("chat_name"),
                               recorded_notes=None
                               )
