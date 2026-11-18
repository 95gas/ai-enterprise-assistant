import os
from datetime import datetime, timezone
from llama_index.core.prompts import RichPromptTemplate
from typing import Optional, Union
from pathlib import Path
from src.common.logging.logger import DebugLogger
from config.settings import settings

DEFAULT_PROMPTS_PATH = settings.DEFAULT_PROMPTS_PATH
THEME_PROMPTS_PATH = settings.THEME_PROMPTS_PATH
PROMPTS_KEYS_DICT = settings.prompts_keys


class PromptManager:
    def __init__(self,
                 user: str = None,
                 prompts_folder: Optional[Union[str, Path]] = None
                 ):
        self.user = user
        self.logger = DebugLogger(user=self.user,
                                  class_name=self.__class__.__name__,
                                  main_feature="PROMPTS")
        self.default_prompts_folder = DEFAULT_PROMPTS_PATH
        self.theme_prompts_folder = THEME_PROMPTS_PATH
        self.prompts_keys = PROMPTS_KEYS_DICT
        self.custom_prompts_folder = Path(prompts_folder) if prompts_folder else None

    def _fetch_prompt(self, prompt_name: str) -> str:
        """
        Fetches the content of a prompt file by name, searching in the configured folders priority:
        1. Custom folder (if provided)
        2. Theme folder
        3. Default folder
        """
        search_paths = []

        # Custom folder (Microservice specific)
        if self.custom_prompts_folder:
            search_paths.append(self.custom_prompts_folder / f"{prompt_name}.md")

        else:
            # Theme folder
            search_paths.append(self.theme_prompts_folder / f"{prompt_name}.md")

            # Default folder
            search_paths.append(self.default_prompts_folder / f"{prompt_name}.md")

        for path in search_paths:

            if path.exists() and path.is_file():

                try:
                    with open(path, "r", encoding="utf-8") as f:
                        prompt = f.read().strip()
                        return prompt
                except Exception as e:
                    self.logger.warning(f"Failed to read prompt at {path}: {e}")

        searched_locations = "\n".join([str(p) for p in search_paths])
        raise FileNotFoundError(
            f"Prompt file '{prompt_name}.md' not found in any of the following locations:\n{searched_locations}")

    def _get_param(self, arg_name: str) -> str:
        if arg_name == "datetime":
            return datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S %Z")
        elif arg_name == "username":
            return self.user
        return self.prompts_keys.get(arg_name)

    def get_prompt(self, prompt_name: str, **kwargs) -> RichPromptTemplate:
        try:
            prompt_md = self._fetch_prompt(prompt_name=prompt_name.lower())
            prompt_tmpl = RichPromptTemplate(prompt_md)
            prompt_tmpl.metadata["prompt_name"] = prompt_name.upper()
            if kwargs:
                params = {k: str(v) for k, v in kwargs.items()}
            else:
                params = dict()
            missing_args = list()
            for arg in prompt_tmpl.template_vars:
                if arg not in params:
                    param = self._get_param(arg_name=arg)
                    if param:
                        params[arg] = param
                    else:
                        missing_args.append(arg)
            if missing_args:
                self.logger.warning(f"Prompt '{prompt_name}' not fully initialized, missing arguments: {missing_args}")
            return prompt_tmpl.partial_format(**params)

        except Exception as e:
            raise RuntimeError(f"Error retrieving prompt '{prompt_name}': {e}")