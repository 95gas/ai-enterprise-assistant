"""Standalone FastAPI service for database authentication and RBAC identities."""

import json
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, SecretStr

from src.common.telemetry import configure_fastapi_metrics
from src.services.authentication.jwt_manager import jwt_manager
from src.services.authentication.errors import UserNotFoundError
from src.services.authentication.manager import AuthService
from config.settings import settings


PORT = int(os.getenv("AUTH_SERVICE_PORT", "8000"))
auth_service = AuthService()


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Authentication Service",
    description="Database login, bearer token issuance, and RBAC identity lookup.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.system.allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
configure_fastapi_metrics(app, "auth-service")


async def require_user(request: Request):
    email = jwt_manager.authenticate_request(request)
    try:
        user = auth_service.get_user(email)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials.") from exc
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials.")
    return user


@app.get("/")
async def healthcheck():
    return {"service": "auth-service", "status": "running"}


@app.get("/healthcheck")
async def health():
    return {"healthcheck": "AUTH SERVICE OK"}


@app.post("/login")
async def login(body: LoginRequest):
    try:
        user = auth_service.authenticate_user(body.email, body.password.get_secret_value())
    except Exception as exc:
        detail, status_code = auth_service.handle_login_exceptions(body.email, exc)
        raise HTTPException(status_code=status_code, detail=detail["message"]) from exc

    return {
        "user": json.loads(user.to_json()),
        "token": jwt_manager.generate_jwt(user=user.email, issuer="auth-service"),
    }


@app.get("/me")
async def get_current_user(user=Depends(require_user)):
    return json.loads(user.to_json())


@app.get("/verify")
async def verify_token(user=Depends(require_user)):
    return {
        "active": True,
        "user": json.loads(user.to_json()),
        "groups": user.groups,
        "permissions": user.permissions.model_dump(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.services.authentication.app:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info",
    )
