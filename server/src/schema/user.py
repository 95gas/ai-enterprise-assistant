import json
from dataclasses import dataclass, asdict
from typing import List
from pydantic import BaseModel 


class UserPermissions(BaseModel):
    web_search: bool = False
    doc_search: bool = False
    upload_common: bool = False
    upload_private: bool = False
    app_name: bool = False


@dataclass
class User:
    """
    Class to represent a logged-in user.
    """
    id: str
    password: str
    email: str
    name: str
    groups: List[str]
    domain: str
    permissions: UserPermissions
    last_login: str
    tot_token_limit: int
    tot_limit_reset_period: str
    expiring_date_trial: str

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    def to_json(self) -> str:
        """Returns the user's attributes as a JSON string."""
        data = asdict(self)
        data["permissions"] = self.permissions.model_dump()
        data.pop("password", None)
        return json.dumps(data)