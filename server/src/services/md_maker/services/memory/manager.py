from src.services.md_maker.services.memory.validator import MemoryValidator
from src.common.logging.logger import DebugLogger
from typing import Optional

class MemoryManager:
    """
    Manages memory validation and protection for high-resolution models.
    Ensures sufficient free memory and applies memory protection mechanisms.
    """

    def __init__(self, logger:Optional[DebugLogger]=None) -> None:
        """
        Initializes the MemoryManager with a logger instance.
        """
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info('Initializing memory manager...')
        self.logger.success('Memory Manager ready')


    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)
        self.logger.set_class_name(self.__class__.__name__)
        self.logger.set_main_feature("DOC")


    def validate_memory(self) -> None:
        """
        Validates that there is sufficient free memory available for processing.
        Logs the status of the memory check.
        :raises: Exception if insufficient memory is available.
        """
        self.logger.info("Validating available free memory.")
        MemoryValidator(logger=self.logger).check_free_memory()
        self.logger.success("Memory validation completed successfully.")