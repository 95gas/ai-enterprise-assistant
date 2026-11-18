from datetime import datetime, timezone
import abc, uuid, inspect, asyncio, json, redis
import os
from typing import Dict, Optional, Generic, Type

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.common.microservices.schemas import InputT, OutputT, TaskSubmission, TaskStatusResponse
from src.services.authentication.jwt_manager import jwt_manager
from src.common.logging.logger import DebugLogger
from src.common.telemetry import configure_fastapi_metrics
from config.settings import settings

SECRET_KEY_PATH = settings.SECRET_KEY_PATH
TASK_TTL = settings.microservices.task_ttl
ALGORITHM = settings.jwt.algorithm
DATE_FORMAT = settings.DATE_FORMAT

import redis.asyncio as aioredis
from fakeredis import aioredis as fake_aioredis


class Microservice(abc.ABC, Generic[InputT, OutputT]):
    
    STATUS_PENDING = "PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"


    def __init__(self, input_model: Type[InputT], output_model: Type[OutputT]):
        self.logger = DebugLogger(class_name=self.__class__.__name__, 
                                  main_feature="MAIN", 
                                  user="undefined")
        self.app = FastAPI(title=self.__class__.__name__)

        @self.app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request: Request, exc: RequestValidationError):
            self.logger.error(f"Validation Error: {exc.errors()}")
            self.logger.error(f"Invalid Body: {exc.body}")
            return JSONResponse(status_code=422, content={"detail": exc.errors(), "body": exc.body})

        self.secret_key_path = SECRET_KEY_PATH
        self.algorithm = ALGORITHM
        
        self.input_model = input_model
        self.output_model = output_model
        service_name = {
            "MdMaker": "md-maker",
            "MdIngestor": "md-ingestor",
        }.get(type(self).__name__, type(self).__name__.lower())
        configure_fastapi_metrics(self.app, service_name)
        
        # --- Redis Connection ---
        redis_host = os.getenv("REDIS_HOST", getattr(settings.redis, "host", "localhost"))
        redis_port = int(os.getenv("REDIS_PORT", getattr(settings.redis, "port", 6379)))
        redis_password = os.getenv("REDIS_PASSWORD", getattr(settings.redis, "password", None))
        redis_db = int(os.getenv("REDIS_DB", getattr(settings.redis, "db", 0)))
        redis_url = os.getenv("REDIS_URL", getattr(settings.redis, "url", None))

        try:
            if redis_url:
                self.redis = aioredis.from_url(redis_url, decode_responses=True)
            else:
                self.redis = aioredis.Redis(
                    host=redis_host,
                    port=redis_port,
                    password=redis_password,
                    db=redis_db,
                    decode_responses=True,
                )
            self.logger.success(f"Configured Redis client targeting {redis_host}:{redis_port}.")
        except Exception as e:
            self.logger.warning(f"Could not initialize Redis client ({e}); falling back to FakeRedis.")
            self.redis = fake_aioredis.FakeRedis(decode_responses=True)

        # --- Dynamic Route Registration ---
        self._register_routes()
        self.logger.success("Base microservice initiated.")


    def _register_routes(self):

        # POST
        async def execute_wrapper(
            request: Request, 
            background_tasks: BackgroundTasks,
            body: self.input_model
        ):
            return await self._handle_execution(request, background_tasks, body)

        execute_wrapper.__annotations__['body'] = self.input_model

        self.app.add_api_route(
            "/execute",
            execute_wrapper,
            methods=["POST"],
            response_model=TaskSubmission,
            status_code=202,
            name="Execute Task"
        )

        # GET
        async def status_wrapper(request: Request, task_id: str):
            return await self._handle_get_status(request, task_id)

        self.app.add_api_route(
            "/tasks/{task_id}",
            status_wrapper,
            methods=["GET"],
            response_model=TaskStatusResponse[self.output_model],
            name="Get Task Status"
        )


    # --- Route Handlers ---
    async def _handle_execution(self, request: Request, background_tasks: BackgroundTasks, body: InputT):
        try:
            user = jwt_manager.authenticate_request(request)
            self.logger.set_user(user)
            
            task_id = str(uuid.uuid4())
            task_data = {"task_id": task_id,
                         "status": self.STATUS_PENDING,
                         "result": None,
                         "error": None,
                         "created_at": datetime.now(timezone.utc).strftime(DATE_FORMAT),
                         "user": user}
            
            await self._save_task(task_id=task_id, data=task_data)
            
            background_tasks.add_task(self._background_handler, task_id, body, user)
            self.logger.info(f"Task {task_id} queued for user {user}")
            
            return TaskSubmission(task_id=task_id, 
                                  status=self.STATUS_PENDING,
                                  message="Task submitted successfully.")
        except HTTPException as e:
            raise e
        except Exception as e:
            self.logger.error(f"Init error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    async def _handle_get_status(self, request: Request, task_id: str):
        task = await self._get_task(task_id)
        if not task:
            self.logger.warning(f"Task not found: '{task_id}'")
            raise HTTPException(status_code=404, detail="Task not found")
        return task


    # --- Internal Logic ---
    async def _background_handler(self, task_id: str, input_data: InputT, user: str):
        try:
            await self._update_task_status(task_id=task_id, status=self.STATUS_PROCESSING)

            result_model: OutputT = await self._process_request(input_data=input_data, user=user, task_id=task_id)

            await self._update_task_result(task_id=task_id, result=result_model, status=self.STATUS_COMPLETED)
            self.logger.success(f"Task {task_id} completed.")

        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {e}")
            await self._update_task_error(task_id=task_id, error_msg=str(e), status=self.STATUS_FAILED)


    async def _process_request(self, input_data: InputT, user: str, task_id: str) -> OutputT:
        is_process_request_async = inspect.iscoroutinefunction(self.process_request)
        if is_process_request_async:
            result = await self.process_request(input_data, 
                                                user, 
                                                task_id)
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, 
                self.process_request,
                input_data, 
                user, 
                task_id
            )
        return result


    # --- REDIS IMPLEMENTATION ---
    async def _save_task(self, task_id: str, data: Dict):
        """Saves dict to Redis as JSON string with TTL."""
        json_str = json.dumps(data, default=str)
        try:
            await self.redis.set(f"task:{task_id}", json_str, ex=TASK_TTL)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            if not isinstance(self.redis, fake_aioredis.FakeRedis):
                self.logger.warning(f"Live Redis unavailable ({e}); falling back to FakeRedis.")
                self.redis = fake_aioredis.FakeRedis(decode_responses=True)
                await self.redis.set(f"task:{task_id}", json_str, ex=TASK_TTL)
            else:
                self.logger.error(f"Redis save error: {e}")
        except Exception as e:
            self.logger.error(f"Redis save error: {e}")

    async def _get_task(self, task_id: str) -> Optional[Dict]:
        """Retrieves JSON string from Redis and parses to Dict."""
        try:
            json_str = await self.redis.get(f"task:{task_id}")
            if not json_str:
                return None
            return json.loads(json_str)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            if not isinstance(self.redis, fake_aioredis.FakeRedis):
                self.logger.warning(f"Live Redis unavailable ({e}); falling back to FakeRedis.")
                self.redis = fake_aioredis.FakeRedis(decode_responses=True)
                json_str = await self.redis.get(f"task:{task_id}")
                return json.loads(json_str) if json_str else None
            return None
        except Exception as e:
            self.logger.error(f"Redis get error: {e}")
            return None


    async def _update_task_status(self, task_id: str, status: str):
        """Fetch, Update Status, Save."""
        data = await self._get_task(task_id)
        if data:
            data["status"] = status
            await self._save_task(task_id, data)


    async def _update_task_result(self, task_id: str, result: OutputT, status: str):
        """
        Fetch, Update Result, Save. 
        IMPORTANT: Converts Pydantic model to dict via .model_dump() 
        so it can be serialized to JSON.
        """
        data = await self._get_task(task_id)
        if data:
            data["result"] = result.model_dump()
            data["status"] = status
            await self._save_task(task_id, data)


    async def _update_task_error(self, task_id: str, error_msg: str, status: str):
        data = await self._get_task(task_id)
        if data:
            data["error"] = error_msg
            data["status"] = status
            await self._save_task(task_id, data)


    @abc.abstractmethod
    async def process_request(self, input_data: InputT, user: str, task_id: str) -> OutputT:
        pass