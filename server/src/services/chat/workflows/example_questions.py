from src.services.chat.workflows.base import BaseWorkflow
from llama_index.core.workflow import (
    step,
    Context,
    StartEvent,
    StopEvent,
    Event
)
from pydantic import BaseModel
from typing import List


class QuestionModel(BaseModel):
    question: str
    summary: str
    sources: List[int]

class ExampleQuestionsModel(BaseModel):
    q1: List[QuestionModel]
    q2: List[QuestionModel]
    q3: List[QuestionModel]


class CreateQuestionsEvent(Event):
    pass

class CustomStopEvent(StopEvent):
    output: dict


class ExampleQuestionsWorkflow(BaseWorkflow):
    """
    StartEvent -> CreateQuestionsEvent -> CustomStopEvent
    """
    @step
    async def retrieve_nodes(self, ctx: Context, ev: StartEvent) -> CreateQuestionsEvent:
        """Retrieves nodes and creates the example questions."""
        chat_history = ev.chat_history
        await ctx.store.set("chat_history", chat_history)
        
        all_languages = {"it": "Italian", "en": "English", "zh": "Chinese"}
        language = all_languages.get(ev.get("selected_language"), "English")
        await ctx.store.set("language", language)

        self.retriever.set_random_mode(True)
        retrieved_nodes = await self._get_nodes(extract_all=True)
        if retrieved_nodes:
            batch_of_sources = self.normalize_nodes_to_sources(retrieved_nodes)
            sources_with_ids = self.add_id_to_sources(lst_sources=batch_of_sources, 
                                                      chat_history=await ctx.store.get("chat_history"))
            sources_str = self.format_sources_to_str(sources_with_ids=sources_with_ids)
        else:
            sources_with_ids = []
            sources_str = "No relevant nodes were found."

        await ctx.store.set("sources_with_ids", sources_with_ids)
        await ctx.store.set("sources_str", sources_str)
        return CreateQuestionsEvent()

    @step
    async def write_json(self, ctx: Context, ev: CreateQuestionsEvent) -> CustomStopEvent:
        self.logger.info("Generating example questions...")

        prompt = self.prompt_manager.get_prompt(prompt_name="EXAMPLE_QUESTIONS",
                                                sources_str=await ctx.store.get("sources_str"),
                                                language=await ctx.store.get("language"))
        try:
            json_obj = await self._chat(prompt=prompt, 
                                        messages=await ctx.store.get("chat_history"),
                                        output_model=ExampleQuestionsModel,
                                        streaming=False)
        except Exception as e:
            self.logger.error(f"Error generating example questions: {e}")
            json_obj = ExampleQuestionsModel.model_dump_json()

        return CustomStopEvent(output=json_obj)