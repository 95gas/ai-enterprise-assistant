import yaml
import boto3
from io import BytesIO
from copy import deepcopy
from botocore.response import StreamingBody
from mypy_boto3_s3 import S3ServiceResource
from typing import IO, Any, Union, Optional, Literal, List, Dict

from src.common.logging.logger import DebugLogger
from config.settings import settings

S3_STRUCTURE_CONFIG = settings.s3.structure_config



class S3DBManager:
    def __init__(
            self,
            url: str = None,
            username: str = None,
            password: str = None,
            logger: DebugLogger = None,
            query_tool: S3ServiceResource = None,
            config_path: str = S3_STRUCTURE_CONFIG  # Default config path
    ):
        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DATABASE")
        self.url = url or settings.s3.url
        self.username = username or settings.s3.username
        self.password = password or settings.s3.password
        self.config_path = config_path

        # Load the folder configuration
        self.folder_config = self._load_config()

        self.logger.info("Establishing new S3 connection...")
        self._validate_password()
        self.RunQueryTool = query_tool or boto3.resource(
            's3',
            endpoint_url=self.url,
            aws_access_key_id=self.username,
            aws_secret_access_key=self.password,
            aws_session_token=None,
            config=boto3.session.Config(signature_version='s3v4'),
        )

        self.users_bucket = self.RunQueryTool.Bucket('users')
        self.system_bucket = self.RunQueryTool.Bucket('system')
        self.shared_bucket = self.RunQueryTool.Bucket('shared')

        # Initialize buckets and folders defined in YAML
        self._init_structure()

        self.logger.success(f"S3DBManager connected with URL: '{self.url}'.")

    def _load_config(self) -> list[str]:
        """Loads folder structure from YAML file."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file) or {}
        except OSError as exc:
            raise FileNotFoundError(f"Could not read S3 structure config {self.config_path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in S3 structure config {self.config_path}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"S3 structure config {self.config_path} must contain a YAML mapping.")
        shared_structure = data.get("shared_structure", [])
        if not isinstance(shared_structure, list) or not all(
            isinstance(folder, str) and folder for folder in shared_structure
        ):
            raise ValueError(f"'shared_structure' in {self.config_path} must be a list of non-empty folder names.")
        return shared_structure

    def config_log(self, user: Optional[str]):
        """
        Configures the logger with user and class information.
        :param user: The username for logging context.
        """
        self.logger.set_user(user)

    def _validate_password(self):
        """
        Validates that the S3 password is provided.

        :raises ValueError: If the password is not set.
        """
        if not self.password:
            error_message = "S3 password is required."
            self.logger.error(error_message)
            raise ValueError(error_message)

    def _init_structure(self):
        """
        Ensures existence of required S3 buckets and creates
        folders defined in the configuration file.
        """
        # Ensure Buckets Exist
        for bucket in [self.users_bucket, self.shared_bucket, self.system_bucket]:
            if not bucket.creation_date:
                try:
                    bucket.create()
                    self.logger.info(f"Created bucket: {bucket.name}")
                except Exception as e:
                    self.logger.warning(f"Could not create bucket {bucket.name} (might already exist): {e}")

        # Create folder structure
        for folder in self.folder_config:
            folder_key = f"{folder}/"

            try:
                self.shared_bucket.put_object(Key=folder_key)
            except Exception as e:
                self.logger.error(f"Failed to init folder {folder_key}: {e}")

    def upload_failed_doc(self, filename: str, file: Union[IO[Any], StreamingBody], content_type: str):
        """
        Uploads the original file in the S3 instance

        :param filename: original filename
        :param file: bytes of the file
        :param content_type: content type of the file
        """
        filekey = f"failed/{filename}"
        self.system_bucket.upload_fileobj(file, filekey, ExtraArgs={"ContentType": content_type})

    def upload_markdowns(self, filename: str, markdowns: List[Dict[str, str]], s3_bucket: str, s3_path: str):
        """
        Uploads a file markdowns in the S3 instance

        :param filename: original filename
        :param markdowns: List of dictionaries containing the markdown pages of the files
        :return: List of dictionaries containing the markdown pages with s3 relevant metadata of the file.
        """
        bucket = self._get_bucket_by_name(name=s3_bucket)
        s3_file_path = f"{s3_path}/{filename}"
        results = []
        for page_dict in markdowns:
            page_name = page_dict["page_name"]
            filekey = f"{s3_file_path}/markdown/{page_name}"
            content_bytes = bytes(page_dict["page_content"], encoding="utf8")
            bucket.upload_fileobj(BytesIO(content_bytes), filekey, ExtraArgs={"ContentType": "text/markdown"})
            new_page_dict = deepcopy(page_dict)
            new_page_dict["metadata"].update({"s3_page": page_name})
            results.append(new_page_dict)
        return results
    

    # Documentation: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/object/get.html
    def get_original(self, s3_bucket: str, s3_path: str, og_filename: str) -> str | Exception:
        """
        Gets the original file of a document
        """
        bucket = self._get_bucket_by_name(name=s3_bucket)
        s3_file_path = f"{s3_path}/original/{og_filename}"
        return bucket.Object(s3_file_path).get()["Body"].read()


    def get_markdowns(self, s3_bucket: str, s3_path: str, filename: str) -> None | Exception:
        """
        Gets the list of markdown pages for a document
        """
        bucket = self._get_bucket_by_name(name=s3_bucket)
        return bucket.objects.filter(Prefix=f"{s3_path}/{filename}/markdown")


    def get_markdown_page(self, s3_bucket: str, s3_path: str, filename: str, s3_page: str) -> str | Exception:
        """
        Gets a single markdown page for a document
        """
        bucket = self._get_bucket_by_name(name=s3_bucket)
        s3_page_path = f"{s3_path}/{filename}/markdown/{s3_page}"
        return bucket.Object(s3_page_path).get()["Body"].read()


    def _get_bucket_by_name(self, name: Literal["users", "shared", "system"]):
        if name == "users":
            return self.users_bucket
        elif name == "shared":
            return self.shared_bucket
        elif name == "system":
            return self.system_bucket
        else:
            self.logger.error(f"Invalid bucket name: {name}")
            raise ValueError(f"Invalid bucket name: {name}")


    def delete_markdowns(self, 
                         s3_bucket: str,
                         s3_path: str,
                         filename: str) -> None | Exception:
        """
        Deletes a file in the S3 instance
        """
        bucket = self._get_bucket_by_name(name=s3_bucket)
        file_folder_path = f"{s3_path}/{filename}"
        file_md_folder_path = file_folder_path + "/markdown"
        bucket.objects.filter(Prefix=file_folder_path).delete()
        bucket.objects.filter(Prefix=file_md_folder_path).delete()

    def get_folders(self):
        """
        Returns the list of folders loaded from the configuration file.
        """
        return self.folder_config


    def get_file_tree(self, bucket_name: str = "shared") -> dict:
        """
        Returns a nested dictionary representing the file structure of the specified bucket.
        Stops before any 'markdown' folder, excluding sub-structure pages, ensuring filenames aren't duplicated.
        """
        bucket = self._get_bucket_by_name(name=bucket_name)

        structure = {}
        for obj in bucket.objects.all():
            if obj.key.endswith("/"):
                continue

            parts = obj.key.strip("/").split("/")

            if "markdown" in parts:
                markdown_index = parts.index("markdown")
                if markdown_index > 0:
                    doc_parts = parts[:markdown_index]
                    filename = doc_parts[-1]
                    node = structure
                    for part in doc_parts[:-1]:
                        if part not in node:
                            node[part] = {}
                        node = node[part]
                    # Use a set to avoid duplicates
                    node.setdefault('filenames', set()).add(filename)
                continue

            node = structure
            for part in parts[:-1]:
                if part not in node:
                    node[part] = {}
                node = node[part]
            node.setdefault('filenames', set()).add(parts[-1])

        # Convert filename sets to sorted lists for JSON compatibility and readability
        def convert_sets(obj):
            if isinstance(obj, dict):
                return {k: (sorted(list(v)) if k == 'filenames' else convert_sets(v)) for k, v in obj.items()}
            return obj

        return convert_sets(structure)