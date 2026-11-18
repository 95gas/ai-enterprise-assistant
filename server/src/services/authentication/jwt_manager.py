import os
import jwt
import uuid
import secrets
import datetime
from pathlib import Path
from fastapi import HTTPException, Request

from src.common.logging.logger import DebugLogger
from config.settings import settings

SECRET_KEY_PATH = settings.SECRET_KEY_PATH
ALGORITHM = settings.jwt.algorithm


class JWTAuthManager:
    """
    Class for managing the JWT authentication framework.
    Handles JWT generation and validation using a shared configured secret or
    the legacy local daily key for standalone development.
    """

    def __init__(self, secret_key_path: Path = SECRET_KEY_PATH, algorithm: str = ALGORITHM):
        self.secret_key_path = secret_key_path
        self.algorithm = algorithm
        self.configured_secret = settings.jwt.secret
        self.logger = DebugLogger(class_name=self.__class__.__name__, main_feature="AUTH")

    def get_daily_secret(self) -> str:
        """Return the shared secret, falling back to the legacy daily key."""
        if self.configured_secret:
            return self.configured_secret

        try:
            # Check if the key exists
            if os.path.exists(self.secret_key_path):
                # Get the date of the file
                file_mtime = os.path.getmtime(self.secret_key_path)
                file_date = datetime.date.fromtimestamp(file_mtime)

                if file_date == datetime.date.today():
                    with open(self.secret_key_path, "r") as f:
                        return f.read().strip()
                else:
                    self.logger.info("Secret key is from a previous day. Rotating...")

            # Generate a new one
            os.makedirs(os.path.dirname(self.secret_key_path), exist_ok=True)
            secret = secrets.token_hex(32)  # Generate new secret

            with open(self.secret_key_path, "w") as f:
                f.write(secret)

            return secret

        except Exception as e:
            self.logger.error(f"Error reading/writing secret key: {e}")
            raise RuntimeError(f"Error reading secret key: {e}")

    def generate_jwt(self, user: str, issuer: str, expires_in_minutes: int = 86400) -> str:
        """
        Creates a digitally signed JWT.
        """
        header = {"alg": self.algorithm, "typ": "JWT"}
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "iss": issuer,
            "sub": user,
            "iat": now,
            "exp": now + datetime.timedelta(minutes=expires_in_minutes),
            "jti": str(uuid.uuid4())
        }
        secret_key = self.get_daily_secret()
        token = jwt.encode(payload, key=secret_key, algorithm=self.algorithm, headers=header)

        return token

    def authenticate_request(self, request: Request) -> str:
        """Verifies the JWT from the incoming request and extracts the user securely."""
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            self.logger.error("Missing or invalid Authorization header")
            raise HTTPException(status_code=401, detail="Unauthorized: Missing Bearer token")

        token = auth_header.split(" ")[1]
        secret_key = self.get_daily_secret()

        try:
            # Verify the signature using the shared secret
            payload = jwt.decode(token, key=secret_key, algorithms=[self.algorithm])
            user = payload.get("sub")
            if not user:
                raise HTTPException(status_code=401, detail="Unauthorized: Token missing user claim")
            return user
        except jwt.ExpiredSignatureError:
            self.logger.error(f"Expired token!")
            raise HTTPException(status_code=401, detail="Unauthorized: Token expired")
        except Exception as e:
            self.logger.error(f"Invalid token error: {str(e)}")
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid token")

jwt_manager = JWTAuthManager()