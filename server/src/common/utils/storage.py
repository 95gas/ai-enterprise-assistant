from pathlib import Path
from typing import Optional

from src.common.logging.logger import DebugLogger


class StorageManager:
    """
    Manages the storage directories, ensuring they are created and cleaned as needed.
    """

    def __init__(self, storage_path: Path, logger: DebugLogger = None) -> None:
        """
        Initializes the StorageManager with a specified storage path.

        :param storage_path: The root path for storage directories.
        """
        self.storage_path = storage_path
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initialize storage manager...")
        self.logger.success("Storage manager ready.")

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger.
        :param user: the user
        """
        self.logger.set_user(user)

    def setup_storage_directories(self) -> Optional[str]:
        """
        Sets up the required storage directories.

        :return: None if successful, or an error message if an exception occurs.
        """
        self.logger.info("Setting up storage directories...")
        return self._create_directories(self.storage_path)

    def _create_directories(self, *paths: Path) -> Optional[str]:
        """
        Creates the specified directories, ensuring they exist.

        :param paths: One or more Path objects representing directories to create.
        :return: None if successful, or an error message if an exception occurs.
        """
        try:
            for path in paths:
                if not path.exists():
                    path.mkdir(parents=True, exist_ok=True)
                    self.logger.success(f"Directory created: {path}")
                else:
                    self.logger.info(f"Directory already exists: {path}")
            return None
        except OSError as e:
            error_message = f"Unable to create storage directories: {e}"
            self.logger.error(error_message)
            return error_message
