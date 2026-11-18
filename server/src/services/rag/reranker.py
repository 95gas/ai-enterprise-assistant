import os
from google.oauth2 import service_account
from google.cloud import discoveryengine_v1 as discoveryengine

from llama_index.core.llms import LLM
from llama_index.core import QueryBundle
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.postprocessor.cohere_rerank import CohereRerank
from llama_index.postprocessor.rankgpt_rerank import RankGPTRerank
from llama_index.core.postprocessor import SentenceTransformerRerank, LLMRerank

from src.common.logging.logger import DebugLogger
from config.settings import settings

GOOGLE_CREDENTIALS_PATH = settings.GOOGLE_CREDENTIALS_PATH
GOOGLE_PROJECT_ID = settings.models_secrets.google.project_id


# Reference: https://cloud.google.com/generative-ai-app-builder/docs/ranking?hl=it

class Reranker:
    def __init__(self,
                 logger: DebugLogger):
        self.logger = logger or DebugLogger()
        self.google_credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH
        )
        self.client = discoveryengine.RankServiceClient(credentials=self.google_credentials)
        self.ranking_config = self.client.ranking_config_path(
            project=GOOGLE_PROJECT_ID,
            location="global",
            ranking_config="default_ranking_config",
        )
        self.logger.info("Reranker initialized")

    def run(self,
            nodes: list[NodeWithScore],
            query: QueryBundle | str,
            reranker: str,
            top: int = 10,
            llm: LLM = None) -> list[NodeWithScore]:

        match reranker.lower():
            case "google":
                if not isinstance(query, str):
                    raise ValueError("Google reranker expects query as a string.")
                return self.run_google(nodes, query, top_n=top)

            case "cohere":
                if not isinstance(query, QueryBundle):
                    raise ValueError("Cohere reranker expects query as a QueryBundle.")
                return self.run_cohere(nodes, query)

            case "sentence_transformer":
                if not isinstance(query, QueryBundle):
                    raise ValueError("SentenceTransformer reranker expects query as a QueryBundle.")
                return self.run_sentence_transformer(nodes, query)

            case "semantic_rerank":
                if llm is None:
                    raise ValueError("LLM must be provided for semantic_rerank.")
                if not isinstance(query, QueryBundle):
                    raise ValueError("Semantic reranker expects query as a QueryBundle.")
                return self.run_semantic_rerank(nodes, query, llm)

            case "rankgpt":
                if llm is None:
                    raise ValueError("LLM must be provided for RankGPT.")
                if not isinstance(query, QueryBundle):
                    raise ValueError("RankGPT reranker expects query as a QueryBundle.")
                return self.run_rankgptrerank(nodes, query, llm)

            case _:
                raise ValueError(f"Unknown reranker type: {reranker}")

    def run_google(self,
            nodes: list[NodeWithScore],
            query: str,
            top_n=10)->list[NodeWithScore]:

        self.logger.info("Reranking nodes with Google...")
        records=[ discoveryengine.RankingRecord(
                    id=index+1,
                    content=node.text,
                ) for index, node in enumerate(nodes)]

        request = discoveryengine.RankRequest(
            ranking_config=self.ranking_config,
            model="semantic-ranker-512@latest",
            top_n=top_n,
            query=query,
            records=[records],
        )

        results = self.client.rank(request=request)

        return [NodeWithScore(node=TextNode(text=result["content"]),
                              score=result["score"])
                   for result in results["records"]]


    def run_cohere(self,
                     nodes: list[NodeWithScore],
                     query_bundle: QueryBundle) \
            -> list[NodeWithScore]:

        self.logger.info("Reranking nodes with Cohere...")

        api_key = ""
        reranker = CohereRerank(api_key=api_key, top_n=30)

        nodes = reranker.postprocess_nodes(
            nodes, query_bundle
        )
        self.logger.success("Rerank nodes with Cohere done")

        return nodes

    def run_sentence_transformer(self,
                     nodes: list[NodeWithScore],
                     query_bundle: QueryBundle) \
            -> list[NodeWithScore]:

        self.logger.info("Reranking nodes with SentenceTransformerRerank...")

        reranker = SentenceTransformerRerank(
            model="mixedbread-ai/mxbai-rerank-large-v1", top_n=30
        )
        nodes = reranker.postprocess_nodes(
            nodes, query_bundle
        )
        self.logger.success("Rerank nodes with SentenceTransformerRerank done")

        return nodes

    def run_semantic_rerank(self,
                     nodes: list[NodeWithScore],
                     query_bundle: QueryBundle,
                     llm: LLM) \
            -> list[NodeWithScore]:
        self.logger.info("Reranking nodes with LLMRerank...")

        reranker = LLMRerank(
            llm=llm,
            choice_batch_size=5,
            top_n=30,
        )
        nodes = reranker.postprocess_nodes(
            nodes, query_bundle
        )
        self.logger.success("Rerank nodes with LLMRerank done")

        return nodes

    def run_rankgptrerank(self,
                     nodes: list[NodeWithScore],
                     query_bundle: QueryBundle,
                     llm: LLM)\
            -> list[NodeWithScore]:

        self.logger.info("Reranking nodes with RankGPTRerank...")
        # configure reranker
        reranker = RankGPTRerank(
            llm=llm,
            top_n=30,
            verbose=True,
        )
        nodes = reranker.postprocess_nodes(
            nodes, query_bundle
        )

        self.logger.success("Rerank nodes with RankGPTRerank done")

        return nodes