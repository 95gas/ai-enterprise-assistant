from typing import Union, Tuple

from src.services.authentication.errors import (
    AuthenticationError,
    UserNotFoundError,
    WrongCredentialsError,
)
from src.services.authentication.database import DBAuthService
from src.common.logging.logger import DebugLogger
from src.schema.user import User
from config.settings import settings

CREDENTIALS_DICT = settings.credentials


class AuthService:
    """
    Handles database authentication and applies configured RBAC.
    """

    def __init__(
            self,
            db_auth_service: DBAuthService = None,
            logger: DebugLogger = None,
    ):
        """
        Initialize AuthService with dependencies.
        :param db_auth_service: Service for database authentication (optional).
        :param logger: DebugLogger instance for logging (optional).
        """
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="LOGIN")
        self.db_auth_service = db_auth_service or DBAuthService()

    def get_user(self, user_id: str) -> Union[User, None]:
        """
        Load a user by ID using the database authentication service.

        :param user_id: The user's ID.
        :return: The User object or None if not found.
        """
        self.logger.set_user(user_id)
        self.logger.info(f"Fetching user with ID: {user_id}")
        return self.db_auth_service.user_repo.get(user_id)

    def authenticate_user(self, email: str, password: str) -> Union[User, None]:
        """
        Authenticate a user against the local user database.

        :param email: The user's email.
        :param password: The user's password.
        :return: The authenticated User object.
        """
        self.logger.set_user(email)
        self.logger.info(f"Authenticating user: {email}")

        user = self.db_auth_service.login_db(email, password)
        self._update_user_groups(user)
        self._update_user_permissions(user)
        self.db_auth_service.user_repo.save(user)
        return user

    def _update_user_groups(self, user: User) -> None:
        """
        Update the user's groups based on configuration.
        """
        user_email = user.email.lower()
        self.logger.set_user(user_email)

        if user_email not in user.groups:
            user.groups.append(user_email)

        try:
            special_users = getattr(CREDENTIALS_DICT, "groups", {})
            user_config = special_users.get(user_email, {})
            
            if not user_config:
                return  # No special group configuration for this user

            mode = getattr(user_config, "mode")
            new_groups = getattr(user_config, "groups", [])
            if not new_groups:
                return 

            if mode == "substitute": # Replace user’s current group list
                user.groups = new_groups.copy()
                if user_email not in user.groups:
                    user.groups.append(user_email)
                self.logger.success(f"Substituted groups for {user_email}: {user.groups}")

            elif mode == "extend": # Add new groups without removing existing ones
                existing_groups = set(user.groups)
                for group in new_groups:
                    if group not in existing_groups:
                        user.groups.append(group)
                        existing_groups.add(group)
                self.logger.success(f"Extended groups for {user_email}: {user.groups}")

            else:
                raise ValueError(f"Invalid group mode '{mode}' for user {user_email}")
        except Exception as e:
            self.logger.error(f"Failed to load special users configuration: {str(e)}")
        return


    def _update_user_permissions(self, user: User) -> None:
        """
        Update user's permissions based on configuration.
        """
        try:
            special_permissions = getattr(CREDENTIALS_DICT, "permissions", {})
            if not isinstance(special_permissions, dict):
                special_permissions = special_permissions.__dict__

            for feature, rules in special_permissions.items():
                allowed = False
                included = getattr(rules, "include", [])
                excluded = getattr(rules, "exclude", [])
                if user.email in included or any(g in included for g in user.groups):
                    allowed = True
                if user.email in excluded or any(g in excluded for g in user.groups):
                    allowed = False
                setattr(user.permissions, feature, allowed)
            self.logger.success(f"Authenticated user with permissions: {user.permissions}")

        except Exception as e:
            self.logger.error(f"Failed to load user permissions: {str(e)}")


    def _update_user_tot_token_limit(self, user: User) -> None:
        """
        Set user's token limits from DB or default configuration.
        """
        try:
            try:
                past_stored_user = self.db_auth_service.user_repo.get(user.id)
            except:
                past_stored_user = None
                self.logger.info(f"New user detected: {user.email}")
            
            default_values = getattr(CREDENTIALS_DICT, "default_values", {})
            if not isinstance(default_values, dict):
                default_values = default_values.__dict__

            for field, default_value in default_values.items():
                try:
                    if past_stored_user and hasattr(past_stored_user, field):
                        setattr(user, field, getattr(past_stored_user, field))
                    else:
                        self.logger.warning(f"Field {field} not found for user {user.email}. Setting default.")
                        setattr(user, field, default_value)
                except Exception as e:
                    self.logger.warning(f"Error setting {field} for user {user.email}: {str(e)}")
                    setattr(user, field, default_value)

        except Exception as e:
            self.logger.error(f"Failed to update token limits for user {user.email}: {str(e)}")


    def handle_login_exceptions(self, email: str, e: Exception) -> Tuple[dict, int]:
        """
        Handle known exceptions during login and return appropriate error responses.
        :param email: The user's email.
        :param e: The exception raised during login.
        :return: A tuple containing the JSON response and HTTP status code.
        """
        if isinstance(e, (UserNotFoundError, WrongCredentialsError, AuthenticationError)):
            self.logger.warning(f"Authentication rejected for user {email}.")
            return {"message": "Invalid email or password."}, 401

        self.logger.error(f"Unexpected error during login for user {email}: {str(e)}")
        return {"message": "Authentication failed."}, 500