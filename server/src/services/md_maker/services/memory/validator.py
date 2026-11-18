import os
import psutil
from flask import abort
from typing import Optional
from src.common.logging.logger import DebugLogger


class MemoryValidator:
    """
    Validates that sufficient memory is available for processing.
    Rejects requests if memory is below the configured minimum threshold.
    """
    def __init__(self, logger:Optional[DebugLogger]=None):
        self.logger = logger or DebugLogger()


    def check_free_memory(self) -> None:
        """
        Validates that there is enough free memory for processing.
        Logs the current memory status and aborts the request if memory is insufficient.

        :raises: HTTP 503 error if available memory is below the minimum threshold.
        """
        available_memory = MemoryValidator._get_available_memory()
        memory_free_minimum = MemoryValidator._get_memory_free_minimum_mb()

        self.logger.info(
            f"Checking free memory: available={MemoryValidator._bytes_to_mb(available_memory)} MB, "
            f"minimum required={memory_free_minimum} MB."
        )

        if available_memory <= MemoryValidator._mb_to_bytes(memory_free_minimum):
            MemoryValidator._reject_request_due_to_low_memory(memory_free_minimum)
        else:
            self.logger.info("Memory validation passed. Sufficient free memory available.")


    @staticmethod
    def _get_available_memory(self) -> int:
        """
        Retrieves the available system memory in bytes.

        :return: Available memory in bytes.
        """
        return psutil.virtual_memory().available


    def _get_memory_free_minimum_mb(self) -> int:
        """
        Retrieves the minimum required free memory in MB from environment variables.
        Defaults to 1048 MB if not set or invalid.

        :return: The minimum required free memory in MB.
        """
        try:
            return int(os.getenv("UNSTRUCTURED_MEMORY_FREE_MINIMUM_MB", 1048))
        except ValueError:
            self.logger.warning(
                "Invalid value for UNSTRUCTURED_MEMORY_FREE_MINIMUM_MB. Using default value of 1048 MB."
            )
            return 1048
        

    @staticmethod
    def _mb_to_bytes(mb: int) -> int:
        """
        Converts memory from megabytes to bytes.

        :param mb: Memory in megabytes.
        :return: Memory in bytes.
        """
        return mb * 1024 * 1024
    

    @staticmethod
    def _bytes_to_mb(bytes_value: int) -> int:
        """
        Converts memory from bytes to megabytes.

        :param bytes_value: Memory in bytes.
        :return: Memory in megabytes.
        """
        return bytes_value // (1024 * 1024)
    

    def _reject_request_due_to_low_memory(self, memory_free_minimum: int) -> None:
        """
        Logs a warning and rejects the request if memory is below the minimum threshold.

        :param memory_free_minimum: The minimum required free memory in MB.
        :raises: HTTP 503 error.
        """
        self.logger.warning(f"Rejecting request: free memory below {memory_free_minimum} MB threshold.")
        abort(503, description="Server is under heavy load. Please try again later.")