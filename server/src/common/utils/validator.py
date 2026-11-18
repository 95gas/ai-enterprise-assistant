import mimetypes
import os
from io import IOBase
from pathlib import Path
from typing import Union, Optional
from flask import abort
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from src.common.logging.logger import DebugLogger


class FileManager:
    """
    Validates files for their MIME type and extension. Checks the integrity of PDF files.
    """
    ALLOWED_EXTENSIONS = {
        'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx',
        'xls', 'xlsx', 'ppt', 'pptx', 'csv', 'zip', 'rar', 'mp4',
        'mp3', 'wav', 'avi', 'mkv', 'flv', 'mov', 'wmv', 'xml', 'md',
        'eml', "jpg", "mpeg", "dat"
    }

    def __init__(self, logger: DebugLogger = None) -> None:
        """
        Initializes the FileValidator with a logger instance.
        """
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initialize file manager...")
        self.logger.success("File manager ready.")

    def config_log(self, user: Optional[str]):
        """
        Sets the current user for the current logger and the class name to print.
        :param user: the user
        """
        self.logger.set_user(user)
        self.logger.set_class_name(self.__class__.__name__)
        self.logger.set_main_feature("DOC")

    def validate_mimetype(self, file: IOBase) -> str:
        """
        Validates the MIME type of a given file.

        :param file: The file object to validate.
        :return: The validated MIME type of the file.
        :raises: HTTP 400 error if the file type is unsupported or indeterminable.
        """
        self.logger.info("Validating MIME type.")

        if isinstance(file, IOBase):
            file.seek(0)

        # Ensure file has a name or fallback to a safer default
        file_name = getattr(file, 'name', None) or "unknown_file"

        # Attempt to determine the MIME type
        content_type = getattr(file, 'content_type', None) or mimetypes.guess_type(file_name)[0]
        allowed_mimetypes = os.getenv("UNSTRUCTURED_ALLOWED_MIMETYPES", "application/pdf,text/plain").split(",")

        if not content_type:
            self.logger.error("Unable to determine file MIME type.")
            abort(400, description="Unable to determine file MIME type.")

        if content_type not in allowed_mimetypes:
            self.logger.error(f"Unsupported file type: {content_type}")
            abort(400, description=f"File type {content_type} is not supported.")

        self.logger.success(f"MIME type validated: {content_type}")
        return content_type

    def check_pdf(self, file: IOBase) -> None:
        """
        Validates if a given file is a valid PDF.

        :param file: The PDF file object to validate.
        :raises: HTTP 422 error if the PDF file is invalid.
        """
        self.logger.info("Validating PDF file integrity.")
        try:
            file.seek(0)  # Reset the file pointer to the beginning.
            PdfReader(file)
            file.seek(0)  # Reset the file pointer after validation.
            self.logger.success("PDF file is valid.")
        except PdfReadError as e:
            self.logger.error(f"Invalid PDF file: {e}")
            abort(422, description="Invalid PDF file.")
        except ValueError as e:
            self.logger.error(f"Invalid file stream: {e}")
            abort(422, description="Invalid PDF file.")
        except Exception as e:
            self.logger.error(f"Unexpected error during PDF validation: {e}")
            abort(500, description="An unexpected error occurred during PDF validation.")

    def allowed_file(self, filename: str) -> bool:
        """
        Validates if a file's extension is allowed.
        :param filename: The name of the file to validate.
        :return: True if the file extension is allowed, otherwise False.
        """
        if not filename or '.' not in filename:
            return False

        extension = filename.rsplit('.', 1)[1].lower()
        result = extension in FileManager.ALLOWED_EXTENSIONS
        if not result:
            self.logger.warning(f"File '{filename}' is not allowed! Skipping processing...")
        else:
            self.logger.info(f"File '{filename}' is allowed: {result}")
        return result

    def convert_path_to_str(self, path: Union[str, Path]) -> str:
        """
        Converts a Path object to a string, if necessary.
        :param path: The file path, either as a string or a Path object.
        :return: The string representation of the path.
        """
        result = str(path) if isinstance(path, Path) else path
        self.logger.info(f"Converted path: {result}")
        return result
