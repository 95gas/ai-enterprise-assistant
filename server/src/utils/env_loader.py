import logging
from pathlib import Path

from dotenv import load_dotenv

class EnvLoader:
    def __init__(self, env_dir: str | Path | None = None):
        """
        Initialize the loader for the shared environment file.

        :param env_dir: Optional config directory containing secrets.env.
        """
        self.config_dir = Path(env_dir) if env_dir else Path(__file__).resolve().parents[2] / "config"
        self.logger = logging

    def load_env_files(self):
        """
        Load the shared environment file without overriding process-level values.
        """
        if not self.config_dir.is_dir():
            raise FileNotFoundError(f"Configuration directory not found: {self.config_dir}")

        env_file = self.config_dir / "secrets.env"
        if env_file.is_file():
            self.logger.info("Loading %s", env_file)
            load_dotenv(env_file)