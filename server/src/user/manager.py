from datetime import datetime, timezone

from src.schema.user import User, UserPermissions
from config.settings import settings

DATE_FORMAT = settings.DATE_FORMAT


class UserManager:
    """
    Maps user records from persistence and external authentication providers.
    """
    @staticmethod
    def create_user_from_data(user_data: dict) -> User:
        """
        Creates a User object from a dictionary of user data.

        :param user_data: A dictionary containing persisted or authenticated user information.
                         Expected keys: 'id', 'email', 'name', 'groups', 'domain'.
        :return: A User object initialized with the provided data.
        :raises KeyError: If any required field is missing from the user_data dictionary.
        """
        try:
            return User(
                id=user_data["id"],
                password=user_data.get("password"),
                email=user_data["email"],
                name=user_data["name"],
                groups=list(user_data.get("groups", [])),  # Use empty list if 'groups' key is missing
                domain=user_data["domain"],
                permissions=UserPermissions(**user_data.get("permissions", {})),
                last_login=datetime.now(timezone.utc).strftime(DATE_FORMAT),
                tot_token_limit=int(user_data.get("tot_token_limit")),
                tot_limit_reset_period=user_data.get("tot_limit_reset_period"),
                expiring_date_trial = datetime.strptime(user_data.get("expiring_date_trial"), DATE_FORMAT).strftime(DATE_FORMAT)
            )
        except KeyError as e:
            raise KeyError(f"Missing required field in user data: {e}")
