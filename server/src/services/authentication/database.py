from src.services.authentication.errors import (
    AuthenticationError,
    UserNotFoundError,
    WrongCredentialsError,
)
from src.services.authentication.hashing import PasswordHasher
from src.common.connectors.postgres.user import UserRepo
from src.common.logging.logger import DebugLogger
from src.schema.user import User

class DBAuthService:
    """
    Handles user authentication against PostgreSQL.
    This service expects a fully configured UserRepo to be injected.
    """

    def __init__(self, user_repo: UserRepo = None, password_hasher=None, logger=None):
        """
        Initialize the DBAuthService.
        :param user_repo: Optional configured user repository.
        :param password_hasher: Optional password hasher instance.
        :param logger: Optional logger instance.
        """
        self.user_repo = user_repo or UserRepo()
        self.password_hasher = password_hasher or PasswordHasher()
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="LOGIN")

    def set_logger(self, user: str):
        self.logger.set_user(user)

    def login_db(self, email: str, password: str) -> User:
        """
        Authenticate a user by verifying their credentials in the database.

        :param email: The user's email.
        :param password: The user's password.
        :return: The authenticated User object.
        :raises AuthenticationError: For validation errors or unexpected issues.
        :raises UserNotFoundError: If the user is not found in the database.
        :raises WrongCredentialsError: If the password is incorrect.        """
        self.set_logger(email)
        self.logger.info(f"Attempting database login for user: {email}")

        try:
            self._validate_credentials(email, password)
            user = self._retrieve_user(email)
            self._verify_password(password, user)
            if not user.password.startswith("pbkdf2_sha256$"):
                user.password = self.password_hasher.hash_password(password)
                self.user_repo.save(user)
            self.logger.success(f"User {email} successfully authenticated.")
            return user

        except UserNotFoundError as e:
            self.logger.warning(str(e))
            raise

        except WrongCredentialsError as e:
            self.logger.warning(str(e))
            raise

        except AuthenticationError as e:
            self.logger.error(str(e))
            raise

        except Exception as e:
            message = f"Unexpected authentication error for user {email}: {e}"
            self.logger.error(message)
            raise AuthenticationError(message) from e

    @staticmethod
    def _validate_credentials(email: str, password: str):
        """
        Validate the email and password.
        :param email: The user's email.
        :param password: The user's password.
        :raises AuthenticationError: If either e-mail or password is missing.
        """
        if not email or not password:
            raise AuthenticationError("E-mail and password are required for authentication.")

    def _retrieve_user(self, email: str) -> User:
        """
        Retrieve user data from the database.
        :param email: The user's email.
        :return: User object.
        :raises UserNotFoundError: If the user does not exist in the database.
        :raises AuthenticationError: If the user data is invalid.
        """
        try:
            user = self.user_repo.get(email)
            if not hasattr(user, "password"):
                self._handle_missing_password(email)
            return user
        except UserNotFoundError:
            raise

    def _handle_missing_password(self, email: str):
        """
        Handle the scenario where a user does not have a password in the database.
        :param email: The user's email.
        :raises AuthenticationError: Always raised after handling the missing password case.
        """
        raise AuthenticationError(f"User {email} does not have a password.")

    def _verify_password(self, password: str, user: User):
        """
        Verify the user's password.
        :param password: The provided password.
        :param user: The user's data.
        :raises WrongCredentialsError: If the password is incorrect.
        """
        if not self.password_hasher.verify_password(password, user.password):
            raise WrongCredentialsError(f"Wrong credentials for user {user.email}.")

    @staticmethod
    def _to_lower_case(txt: str) -> str:
        """Lower case the text."""
        return txt.lower()