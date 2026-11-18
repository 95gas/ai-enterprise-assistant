from pathlib import Path
from functools import wraps
from typing import Optional, List
from flask_cors import cross_origin
from pydantic import ValidationError
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from pathvalidate import sanitize_filepath
import os, re, json, asyncio, flask_login
from typing import Dict, Any, Tuple, Union
from botocore.exceptions import ClientError
from flask import Blueprint, request, jsonify, Response, current_app, g

from src.common.schema.documents import DocumentToProcess, ProcessingConfig
from src.services.temporal.client import TemporalMicroserviceClient
from src.services.chat.temporal import temporal_enabled
from src.common.utils.validator import FileManager
from src.common.logging.logger import DebugLogger
from config.settings import settings

DATE_FORMAT = settings.DATE_FORMAT
STORAGE_PATH = settings.STORAGE_PATH
STORAGE_MARKDOWN = settings.STORAGE_MARKDOWN
STORAGE_FAILED_DOCS = settings.STORAGE_FAILED_DOCS
MAX_PRIVATE_DOCS_PER_USER = settings.MAX_PRIVATE_DOCS_PER_USER

FAST_SUPPORTED_MIMES = {
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
    'application/msword',  # .doc
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # .pptx
    'application/vnd.ms-powerpoint',  # .ppt
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.ms-excel'  # .xls
}


logger = DebugLogger()
ingest_router = Blueprint('ingest_router', __name__)
file_manager = FileManager()
storage_path = Path(STORAGE_PATH)


from typing import Any, Literal, List
from pydantic import BaseModel, field_validator


class FileUploadItem(BaseModel):
    """
    Pydantic schema to validate and coerce multipart/form-data payload.
    """
    file: Any
    visibility_groups: List[str] = []
    uploaded_by: str = "undefined"
    s3_bucket: Literal["users", "shared", "system"] = "shared"
    s3_path: str = "Common"
    method: Literal["fast", "full"] = "full"
    tables: bool = True
    images: bool = True

    @field_validator('visibility_groups', mode='before')
    @classmethod
    def parse_visibility_groups(cls, v: Any) -> List[str]:
        """Automatically parses a comma-separated string into a list of strings."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [p.strip() for p in v.split(',') if p.strip()]
        if isinstance(v, list):
            return v
        return []


@staticmethod
def sanitize_name(name: str) -> str:
    """Sanitizes filename while preserving the extension."""
    base_name, ext = os.path.splitext(name)
    safe_base = re.sub(r'[^a-zA-Z0-9-]', '_', base_name)
    return safe_base + ext


@ingest_router.before_request
def load_services():
    """Load services into the Flask request global `g`."""
    # This runs before each request to this blueprint, after the app context is available
    if not hasattr(g, 'main_agent'):
        g.main_agent = current_app.main_agent
        g.db_manager = g.main_agent.get_neo4j_connection()
        g.s3_manager = g.main_agent.get_s3_connection()


def setup_request_context(f):
    """Initializes loggers and services for the current request context."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # `g` is populated by the `before_request` hook
        user_email = flask_login.current_user.email
        # Configure the global logger for this route
        logger.set_user(user_email)
        logger.set_class_name("ingest")
        logger.set_main_feature("DOC")
        # Configure services from `g` and other globals
        g.main_agent.initialize(user=user_email)
        file_manager.config_log(user=user_email)  # Configure global file_manager
        g.db_manager.config_log(user_email)  # Configure g.db_manager
        return f(*args, **kwargs)

    return decorated_function


def upload_permission_required(f):
    """Ensures the current user has the 'upload_common' permission."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if flask_login.current_user.permissions.upload_common or flask_login.current_user.permissions.upload_private:
            return f(*args, **kwargs)
        logger.warning(f"Unauthorized access attempt by user: {flask_login.current_user.email}")
        return jsonify({"message": "This action requires upload privileges."}), 403

    return decorated_function

def _parse_request_files(req, user_email: str) -> List[FileUploadItem]:
    """Extracts files and metadata from the request object using Pydantic."""
    raw_inputs = []
    i = 0
    while f'file_{i}' in req.files:
        try:
            item = FileUploadItem(
                file=req.files.get(f'file_{i}'),
                visibility_groups=req.form.get(f'visibility_groups_{i}', ''),
                s3_bucket=req.form.get(f's3_bucket_{i}', "shared"),
                s3_path=req.form.get(f's3_path_{i}', "Common"),
                uploaded_by=user_email,
                method=req.form.get(f'method_{i}', "full"),
                tables=req.form.get(f'tables_{i}' == "true", True),
                images=req.form.get(f'images_{i}' == "true", True)
            )
            raw_inputs.append(item)
        except ValidationError as e:
            logger.error(f"Pydantic Validation error for file index {i}: {e}")
        i += 1
    return raw_inputs


def validate_and_store_docs(raw_items: List[FileUploadItem], tmp_dir_path: Path, user_email: str) -> Tuple[List[DocumentToProcess], Dict[str, str]]:
    """
    Validates a list of raw FileUploadItem objects
    """
    docs_to_process = []
    docs_not_processed = {}
    processed_filenames = set()

    private_uploads = sum([1 for item in raw_items if item.s3_bucket == "users"])
    if private_uploads:
        msg = f"A user may have at most {MAX_PRIVATE_DOCS_PER_USER}"
        if private_uploads > MAX_PRIVATE_DOCS_PER_USER:
            logger.info(msg)
            raise Exception(msg)
        private_docs_stored = g.db_manager.retrieve_documents(visibility_groups=[user_email])
        if private_uploads + len(private_docs_stored) > MAX_PRIVATE_DOCS_PER_USER:
            logger.info(msg)
            raise Exception(msg)

    for item in raw_items:

        file = item.file
        filename = sanitize_name(file.filename)

        s3_path = item.s3_path if item.s3_bucket != "users" else "Private"

        # Check Duplicates in execution
        if filename in processed_filenames: 
            logger.warning(f"Duplicate filename '{filename}' in request, skipping.")
            docs_not_processed[file.filename] = "File duplicated."
            continue

        # Check Duplicates in KB
        if g.db_manager.check_duplicate_doc(s3_bucket=item.s3_bucket, s3_path=s3_path, filename=filename):
            logger.warning(f"Document '{filename}' already stored, skipping.")
            docs_not_processed[file.filename] = "File already stored."
            continue

        # Check File Extension
        if not file_manager.allowed_file(filename):
            logger.warning(f"File type not allowed for {filename}, skipping.")
            docs_not_processed[file.filename] = "File type not allowed."
            continue

        try:
            # Write to temporary file
            file_content = file.read()
            tmp_file = tmp_dir_path / filename
            with open(tmp_file, "wb") as f:
                f.write(file_content)

            # Prepare metadata
            docs_to_process.append(DocumentToProcess(
                filename=filename,
                visibility_groups=item.visibility_groups if item.s3_bucket != "users" else [user_email],
                processing=ProcessingConfig(method=item.method, tables=item.tables, images=item.images),
                content_type=file.content_type,
                s3_bucket=item.s3_bucket,
                s3_path=s3_path,
                uploaded_by=item.uploaded_by,
                og_last_modified=datetime.now(timezone.utc).strftime(DATE_FORMAT),
                og_filename=file.filename,
                og_uri=None,
                source_filepath=tmp_file))
            
            processed_filenames.add(filename)
            logger.success(f"File '{filename}' validated and stored.")
        except Exception as e:
            logger.error(f"Error structuring data for '{file.filename}': {e}")
            docs_not_processed[file.filename] = "File unrecognizable."
            continue
    return docs_to_process, docs_not_processed


# --- Routes ---
@ingest_router.route("/general/v0/docs/process", methods=['POST'])
@cross_origin(supports_credentials=True)
@flask_login.login_required
@setup_request_context
@upload_permission_required
def process_file():
    """Refactored entry point for processing uploaded files."""
    logger.api(f"{request.method} {request.path}")

    # 1. Extraction & Initial Validation via Pydantic
    raw_inputs = _parse_request_files(request, user_email=flask_login.current_user.email)
    if not raw_inputs:
        return jsonify({"message": "No files provided in request."}), 400

    # 2. Execution
    try:
        with TemporaryDirectory() as tmp_dir:
            docs_to_process, docs_not_processed = validate_and_store_docs(raw_items=raw_inputs, tmp_dir_path=Path(tmp_dir), user_email=flask_login.current_user.email)
            if docs_not_processed:
                return jsonify({"message": f"Some files cannot be processed:\n{str(docs_not_processed)}", "data": docs_not_processed}), 500
            results = _execute_processing_and_ingestion(docs_to_process=docs_to_process)
            return jsonify({"message": "Files processed successfully.", "data": results}), 200

    except Exception as e:
        logger.error("Internal processing error")
        return jsonify({"error": str(e)}), 500


def convert_paths(obj):
    if isinstance(obj, dict):
        return {key: convert_paths(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [convert_paths(value) for value in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


def _execute_processing_and_ingestion(docs_to_process: List[DocumentToProcess]) -> dict:
    """Run document processing as a durable Temporal workflow."""
    fast_docs = [
        doc for doc in docs_to_process
        if doc.processing and doc.processing.method == "fast"
    ]
    unsupported = {
        doc.og_filename
        for doc in fast_docs
        if doc.content_type not in FAST_SUPPORTED_MIMES
    }
    if unsupported:
        raise ValueError(
            f"Fast extraction does not support: {', '.join(sorted(unsupported))}"
        )

    if not temporal_enabled():
        raise RuntimeError("Temporal ingestion is unavailable. Enable Temporal and start its worker.")

    user_email = flask_login.current_user.email
    serialized_docs = [convert_paths(doc.model_dump()) for doc in docs_to_process]
    result = asyncio.run(
        TemporalMicroserviceClient().execute_document_ingestion(
            docs_to_process=serialized_docs,
            user=user_email,
        )
    )
    return {
        "ingested": result.get("docs_succeeded", []),
        "failed": {
            "processment": [
                doc.get("og_filename", doc.get("filename", "unknown"))
                for doc in result.get("extraction_failed", [])
            ],
            "ingestion": result.get("docs_failed", []),
        },
    }

@ingest_router.route("/general/v0/docs/<s3_bucket>/<path:s3_path>/<filename>", methods=["DELETE"])
@flask_login.login_required
@setup_request_context
@upload_permission_required
def doc_delete(s3_bucket: str, s3_path: str, filename: str):
    """Delete a file from storage and its associated data from Neo4j."""
    logger.api(f"{request.method} {request.path}")
    logger.info(f"Attempting to delete file '{s3_bucket}//{s3_path}//{filename}'.")
    if "/markdown/" in s3_path:
        logger.error("'s3_path' cannot contain '/markdown/'.")
        return jsonify({"message": "Error deleting file data from database."}), 500

    # Delete from storage
    try:
        g.s3_manager.delete_markdowns(s3_bucket=s3_bucket, s3_path=s3_path, filename=filename)
        logger.success(f"File '{s3_bucket}//{s3_path}//{filename}' deleted.")
    except FileNotFoundError:
        logger.warning(f"File '{s3_bucket}//{s3_path}//{filename}' not found, may have been deleted already.")

    # Delete from database
    try:
        g.db_manager.delete_document(s3_bucket=s3_bucket, s3_path=s3_path, filename=filename)
        logger.success(f"Document '{s3_path}' and associated chunks deleted from Neo4j.")
        return jsonify({"message": f"Successfully deleted '{s3_path}'."}), 200
    except Exception as e:
        logger.error(f"Error deleting '{s3_path}' from Neo4j: {e}")
        return jsonify({"message": "Error deleting file data from database."}), 500


@ingest_router.route("/general/v0/docs", methods=["GET"])
@flask_login.login_required
@setup_request_context
def docs_retrieve():
    """Retrieve all document records accessible by the user."""
    logger.api(f"{request.method} {request.path}")
    logger.info("Retrieving all stored document records.")
    try:
        visibility_groups = flask_login.current_user.groups
        documents = g.db_manager.retrieve_documents(visibility_groups=visibility_groups)
        logger.success("Documents retrieved successfully.")
        return jsonify(documents)
    except Exception as e:
        logger.error(f"Error retrieving document records: {e}")
        return jsonify({"message": "Could not retrieve document records."}), 500


@ingest_router.route("/general/v0/docs/<s3_bucket>/<path:s3_path>/<filename>", methods=["GET"])
@flask_login.login_required
@setup_request_context
def doc_pages_list(s3_bucket: str, s3_path: str, filename: str):
    """Retrieve the markdown pages for a specific document."""
    logger.api(f"{request.method} {request.path}")
    logger.info(f"Retrieving pages for: '{s3_bucket}//{s3_path}//{filename}'")

    s3_page = request.args.get('s3_page')

    if (s3_page == None):
        try:
            pages = g.s3_manager.get_markdowns(s3_bucket=s3_bucket, s3_path=s3_path, filename=filename)
            pages_refs = {}
            for page_s3_path in pages:
                page_name = page_s3_path.key.split("_page")[-1].replace(".md", "")
                # page_name = page_name if len(page_name) < 8 else page_name[:6]+".." # TODO Set in FE
                pages_refs[page_name] = page_s3_path.key.split("/markdown/")[-1] # TODO Need to sort?
            return jsonify(pages_refs), 200
        except Exception as e:
            logger.error(f"Could not extract pages for '{s3_path}': {e}")
            return jsonify({"message": "Pages not found."}), 404
    else:
        try:
            page_binary = g.s3_manager.get_markdown_page(s3_bucket=s3_bucket, s3_path=s3_path, filename=filename, s3_page=s3_page)
            page_markdown = page_binary.decode('utf-8')
            return Response(page_markdown, mimetype='text/markdown')
        except ClientError as e:
            logger.error(f"Page '{s3_page}' not found: {e}")
            return jsonify({"message": "Page not found."}), 404
        except Exception as e:
            logger.error(f"Could not read page '{s3_page}': {e}")
            return jsonify({"message": "Error reading page content."}), 500


@ingest_router.route("/general/v0/docs/buckets", methods=["GET"])
@flask_login.login_required
@setup_request_context
def get_buckets():
    """Retrieve all available buckets"""
    logger.api(f"{request.method} {request.path}")
    logger.info("Retrieving buckets...")
    try:
        buckets = g.s3_manager.get_folders()
        logger.success("Buckets retrieved successfully.")
        return jsonify(buckets)
    except Exception as e:
        logger.error(f"Error retrieving buckets: {e}")
        return jsonify({"message": "Could not retrieve buckets."}), 500