class FileProcessingError(Exception):
    def __init__(self, message, filename, error_type):
        super().__init__(message)
        self.message = message
        self.filename = filename
        self.error_type = error_type

    def __str__(self):
        return f"{self.error_type} for document {self.filename}."