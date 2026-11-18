from fastapi import Request, HTTPException, BackgroundTasks
from datetime import datetime, timezone
import uuid, os

from src.services.md_ingestor.services.pipeline.ingestor import DocIngestor
from src.services.md_ingestor.schemas.schemas import InputData, OutputData
from src.common.schema.documents import DocumentToProcess, DocumentToDelete
from src.common.connectors.neo4j.manager import Neo4jDBManager
from src.common.connectors.postgres.base import PostgresManager
from src.common.microservices.schemas import TaskSubmission
from src.common.connectors.s3.manager import S3DBManager
from src.services.authentication.jwt_manager import jwt_manager
from src.common.microservices.base import Microservice
from src.common.models.llama_config import LIConfig
from src.common.models.manager import ModelManager
from src.common.logging.logger import DebugLogger
from src.services.rag.vector_rag import VectorRAG
from src.services.rag.graph_rag import GraphRAG
from config.settings import settings

DATE_FORMAT = settings.DATE_FORMAT


class MdIngestor(Microservice[InputData, OutputData]):
    def __init__(self):
        super().__init__(input_model=InputData, output_model=OutputData)

        # Config Llama Index
        self.logger = DebugLogger(class_name=self.__class__.__name__,
                                  main_feature="DOC",
                                  user="undefined")
        self.logger.info("Configuring LlamaIndex...")
        LIConfig()

        self.logger.info("Initializing DocIngestor...")
        try:
            # Initialize database managers if not provided
            self.logger.info("Initializing databases...")
            self.db_manager = PostgresManager()
            self.db_manager.initialize()
            self.db_manager_neo4j = Neo4jDBManager()
            self.db_manager_s3 = S3DBManager()
            self.logger.success("Databases ready.")

            # Initialize RAG systems if not provided
            self.logger.info("Initializing Knowledge...")
            self.vector_rag = VectorRAG(db_manager=self.db_manager_neo4j)
            self.graph_rag = GraphRAG(db_manager=self.db_manager_neo4j)
            self.vector_manager = self.vector_rag.knowledge_manager
            self.graph_manager = self.graph_rag.knowledge_manager
            self.vector_manager.load_index()
            self.graph_manager.load_index()
            self.logger.success("Knowledge ready.")

            # Initialize document ingestor
            self.logger.info("Initializing model manager...")
            self.model_manager = ModelManager()
            self.logger.success("Model manager ready.")

            # Initialize document ingestor
            self.logger.info("Initializing ingestor pipeline...")
            self.doc_ingestor = DocIngestor(
                model_manager=self.model_manager,
                vector_manager=self.vector_manager,
                graph_manager=self.graph_manager,
                db_manager_neo4j=self.db_manager_neo4j,
                db_manager=self.db_manager,
                db_manager_s3=self.db_manager_s3
            )

            self.logger.info("Initializing custom routes...")
            self._register_custom_routes()

            self.logger.success(f"{self.__class__.__name__} initiated.")
        except Exception as e:
            self.logger.error("Error initializing DocIngestor.", exc_info=True)
            raise

    def _register_custom_routes(self):
        """
        Wraps the core deletion logic to use BackgroundTasks and Redis tracking,
        matching the base Microservice architecture.
        """
        async def batch_delete_wrapper(
            request: Request, 
            background_tasks: BackgroundTasks, 
            body: InputData
        ):
            try:
                user = jwt_manager.authenticate_request(request)
                self.logger.set_user(user)
                
                task_id = str(uuid.uuid4())
                task_data = {
                    "task_id": task_id,
                    "status": self.STATUS_PENDING,
                    "result": None,
                    "error": None,
                    "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d_%H:%M:%S"),
                    "user": user
                }
                await self._save_task(task_id=task_id, data=task_data)

                background_tasks.add_task(self._background_delete_handler, task_id, body, user)
                self.logger.info(f"Delete Task {task_id} queued for user {user}")
                return TaskSubmission(
                    task_id=task_id, 
                    status=self.STATUS_PENDING,
                    message="Delete task submitted successfully."
                )
                
            except HTTPException as e:
                raise e
            except Exception as e:
                self.logger.error(f"Batch delete endpoint error: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))

        self.app.add_api_route(
            path="/execute/batch_delete",
            endpoint=batch_delete_wrapper,
            methods=["POST"],
            response_model=TaskSubmission,
            status_code=202,              
            name="Batch Delete Documents"
        )

    async def _background_delete_handler(self, task_id: str, input_data: InputData, user: str):
        try:
            await self._update_task_status(task_id=task_id, status=self.STATUS_PROCESSING)

            result_model: OutputData = await self.batch_delete_documents(
                input_data=input_data, user=user, task_id=task_id
            )

            await self._update_task_result(task_id=task_id, result=result_model, status=self.STATUS_COMPLETED)
            self.logger.success(f"Delete Task {task_id} completed.")

        except Exception as e:
            self.logger.error(f"Delete Task {task_id} failed: {e}")
            await self._update_task_error(task_id=task_id, error_msg=str(e), status=self.STATUS_FAILED)

    async def batch_delete_documents(self, input_data: InputData, user: str, task_id: str) -> OutputData:
        """
        This is the core logic that runs a batch deletion of documents.
        """
        self.logger.info(f"Starting execution of task '{task_id}' requested by user '{user}'.")
        start_time = datetime.now()

        docs = input_data.docs_to_delete

        if not docs:
            self.logger.warning("Batch delete called but no documents were provided.")
            raise HTTPException(status_code=400, detail="No documents provided in 'docs_to_delete'.")

        docs = [DocumentToDelete(filename=d.filename,
                                 s3_bucket=d.s3_bucket,
                                 s3_path=d.s3_path,
                                 og_filename=d.og_filename,
                                 source_filepath=d.source_filepath) if isinstance(d, DocumentToProcess) else d for d in docs]
        
        self.logger.info(f"Received batch delete request for {len(docs)} files by user '{user}'.")
        
        results = await self.doc_ingestor.delete_documents_from_kb(docs)
        
        self.logger.success(f"Batch delete for {len(docs)} files completed.")
        
        return OutputData(docs_succeeded=[f for f in results["deleted"]],
                          docs_failed=[f for f in results["failed"]],
                          processing_time=(datetime.now() - start_time).total_seconds(),
                          timestamp=datetime.now(timezone.utc).strftime(DATE_FORMAT))
        
    async def process_request(self, input_data: InputData, user: str, task_id: str) -> OutputData:
        """
        This is the core logic that runs in the BackgroundTask.
        """
        self.logger.info(f"Starting execution of task '{task_id}' requested by user '{user}'.")
        start_time = datetime.now()

        docs_to_ingest = input_data.docs_to_ingest
        docs_success_list = []
        docs_failed_list = []
        
        if not docs_to_ingest:
            self.logger.error("No documents to ingest.")
        else:
            ingest_results = await self.doc_ingestor.ingest_batch(docs_to_ingest=docs_to_ingest)
            for result in ingest_results:
                file = result.get("file")
                response_obj = result.get("response")
                if response_obj.status_code == 200:
                    docs_success_list.append(file)
                else:
                    docs_failed_list.append(file)

            # Clean up failed documents
            if docs_failed_list:
                self.logger.info(f"Cleaning up {len(docs_failed_list)} failed documents from databases...")
                await self.doc_ingestor.delete_documents_from_kb(docs_failed_list)

            if docs_success_list:
                self.logger.info(f"Cleaning up ingested documents leftovers...")
                for d in docs_success_list:
                    if d.source_filepath and d.source_filepath.exists():
                        os.remove(d.source_filepath)

        return OutputData(docs_succeeded=[f.og_filename for f in docs_success_list],
                          docs_failed=[f.og_filename for f in docs_failed_list],
                          processing_time=(datetime.now() - start_time).total_seconds(),
                          timestamp=datetime.now(timezone.utc).strftime(DATE_FORMAT))


microservice = MdIngestor()
app = microservice.app