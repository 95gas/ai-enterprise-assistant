"""HTTP client dependency for validating callers through the auth service."""

import os

import httpx
from fastapi import HTTPException, Request

from src.schema.user import User, UserPermissions


async def require_user(request: Request) -> User:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")

    auth_service_url = os.getenv("AUTH_SERVICE_URL", "http://localhost:8003").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{auth_service_url}/verify",
                headers={"Authorization": authorization},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable.") from exc

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials.")
    if response.is_error:
        raise HTTPException(status_code=503, detail="Authentication service unavailable.")

    try:
        data = response.json()["user"]
        permissions = UserPermissions(**data["permissions"])
        return User(
            id=data["id"],
            password="",
            email=data["email"],
            name=data["name"],
            groups=data["groups"],
            domain=data["domain"],
            permissions=permissions,
            last_login=data["last_login"],
            tot_token_limit=data["tot_token_limit"],
            tot_limit_reset_period=data["tot_limit_reset_period"],
            expiring_date_trial=data["expiring_date_trial"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Authentication service returned an invalid user profile.",
        ) from exc
