import os
import time
import logging
import traceback
from datetime import datetime
from typing import List, Tuple, Any, Optional
from src.common.logging.config import LOG_PATH as LOG_FILE_PATH
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from contextlib import contextmanager
import asyncio
import functools
from src.common.privacy.pii_redactor import get_default_redactor

LOGGING_MODE = os.environ.get("LOGGING_MODE")

class DebugLogger:
    """
    A logger with optional panel-based error messages, file-based or console-based
    output, and utility methods for rich formatting of logs, prompts, and results.
    """
    console: Console = Console()

    def __init__(self,
                 use_panel_for_errors: bool = False,
                 user: Optional[str] = "undefined",
                 class_name: Optional[str] = None,
                 main_feature: Optional[str] = None):
        """
        Initialize the logger with custom themes and optional panel usage for errors.

        :param use_panel_for_errors: Whether to automatically use a panel for error messages.
        :type use_panel_for_errors: bool
        """
        # Define custom theme for log levels
        self.custom_theme = Theme({
            "info": "cyan",
            "warning": "yellow",
            "error": "bold red",
            "success": "green",
            "debug": "dim",
            "api": "white",
            "time": "light_sea_green"
        })
        self.use_panel_for_errors = use_panel_for_errors

        # Setup console to file output
        if not os.path.exists(LOG_FILE_PATH):
            os.makedirs(LOG_FILE_PATH)
        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = timestamp + ".log"
        file_path = LOG_FILE_PATH / filename
        self.log_file = open(file_path, 'a+', encoding='utf-8')
        self.console_to_file = Console(file=self.log_file, theme=self.custom_theme)

        # Setup console to screen output
        self.console_to_screen = Console(theme=self.custom_theme)
        self.user = user
        self.class_name = class_name
        self.main_feature = main_feature

    def set_user(self, user: Optional[str]):
        self.user = user

    def set_class_name(self, class_name: Optional[str]):
        self.class_name = class_name

    def set_main_feature(self, main_feature: Optional[str]):
        self.main_feature = main_feature

    def log(self, message: str, level: str = "info", use_panel: bool = False):
        """
        Log a message with a given severity level and optional panel.

        :param message: The message to log.
        :type message: str
        :param level: The severity level ('info', 'warning', 'error', 'success', 'debug').
        :type level: str
        :param use_panel: If True, the message will be displayed inside a panel.
        :type use_panel: bool
        :raises ValueError: If the log level is not valid.
        """
        valid_levels = ["info", "warning", "error", "success", "debug", "api", "time"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if level not in valid_levels:
            raise ValueError(f"Invalid log level: {level}. Must be one of {valid_levels}")

        redactor = get_default_redactor()
        message = redactor.redact(str(message))
        safe_user = redactor.redact(self.user) if self.user else self.user

        # Automatically use a panel for errors if configured
        if level == "error" and self.use_panel_for_errors:
            use_panel = True

        # Format the message to include the log level in uppercase
        log = f"[{timestamp:<12}]"
        if safe_user:
            log += f"-[{safe_user:^25}]"

        if self.class_name:
            class_name = self.class_name
            log += f"-[{class_name:^24}]"

        if self.main_feature:
            log += f"-[{self.main_feature:^8}]"

        log += f"-[{level.upper():^7}] {message:<1000}"

        formatted_message = Text(log, style=level)
        logging.getLogger("ask.telemetry").log(
            getattr(logging, level.upper(), logging.INFO),
            formatted_message.plain,
        )

        # Print message using a panel or as plain text based on the flag
        if use_panel:
            self.console_to_file.print(Panel(formatted_message, title=level.capitalize(), expand=False))
            self.console_to_screen.print(Panel(formatted_message, title=level.capitalize(), expand=False))
        else:
            self.console_to_file.print(formatted_message)
            self.console_to_screen.print(formatted_message)

    def info(self, message: str, user: Optional[str]=None):
        """Log an info message."""
        self.log(message, level="info")

    def api(self, message: str):
        """Log an API request message."""
        self.log(message, level="api")

    def time(self, message: str):
        """Log a time message."""
        self.log(message, level="time")

    def warning(self, message: str):
        """Log a warning message."""
        self.log(message, level="warning")

    def error(self, message: str,  exc_info: bool = True):
        """
        Log an error message.

        :param message: The message to log.
        :type message: str
        :param exc_info: Whether to log an exception or just the message.
        :type exc_info: bool
        """
        if exc_info:
            message = f"{message}: {traceback.format_exc()}"
        self.log(message, level="error")

    def success(self, message: str):
        """Log a success message."""
        self.log(message, level="success")

    def debug(self, message: str):
        """Log a debug message."""
        self.log(message, level="debug")

    def pretty_print_prompt(self, prompt: str, variables: dict = None):
        """
        Pretty-print an LLM prompt and its variables in a table format.
        """
        table = Table(title="LLM Prompt", expand=False)
        table.add_column("Section", style="bold cyan", no_wrap=True)
        table.add_column("Content", style="bold white")

        redactor = get_default_redactor()
        table.add_row("Prompt", redactor.redact(prompt))

        if variables:
            for key, value in variables.items():
                table.add_row(
                    redactor.redact(f"Variable: {key}"),
                    redactor.redact(str(value)),
                )

        self.console_to_file.print(table)
        self.console_to_screen.print(table)

    def pretty_print_list_docs(self, docs: List[Tuple[Any]], additional_score: bool = False):
        """
        Pretty-print a list of docs in a table format, with optional additional score column.
        """
        table = Table(title="DOCs retrieved", expand=False)

        if not additional_score:
            table.add_column("Filename", style="bold cyan", no_wrap=True)
            table.add_column("Policy", style="bold white")
            for doc in docs:
                redactor = get_default_redactor()
                table.add_row(
                    redactor.redact(str(doc[0])),
                    redactor.redact(str(doc[1])),
                )
        else:
            table.add_column("Filename", style="bold cyan", no_wrap=True)
            table.add_column("Aggregated MMR", style="bold white")
            table.add_column("Policy", style="bold white")
            for doc in docs:
                redactor = get_default_redactor()
                table.add_row(
                    redactor.redact(str(doc[0])),
                    redactor.redact(str(doc[1])),
                    redactor.redact(str(doc[2])),
                )

        self.console_to_file.print(table)
        self.console_to_screen.print(table)

    def pretty_print_answer(self, answer: str, additional_info: dict = None):
        """
        Pretty-print an LLM answer and optional additional info in a table format.
        """
        table = Table(title="LLM Answer", expand=False)
        table.add_column("Section", style="bold cyan", no_wrap=True)
        table.add_column("Content", style="bold white")

        redactor = get_default_redactor()
        table.add_row("Answer", redactor.redact(answer))

        if additional_info:
            for key, value in additional_info.items():
                table.add_row(
                    redactor.redact(f"Info: {key}"),
                    redactor.redact(str(value)),
                )

        self.console_to_file.print(table)
        self.console_to_screen.print(table)

    @staticmethod
    def profile(func):
        """
        A decorator that profiles the execution time of both synchronous and
        asynchronous functions.
        """
        @contextmanager
        def wrapping_logic(self):
            self.logger.time(f"Starting execution of {func.__name__}...")
            start_ts = time.monotonic()
            yield
            dur = time.monotonic() - start_ts
            self.logger.time(f"Execution of {func.__name__} completed in {dur:.4f} seconds.")

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not asyncio.iscoroutinefunction(func):
                with wrapping_logic(self):
                    return func(self, *args, **kwargs)
            else:
                async def tmp():
                    with wrapping_logic(self):
                        return (await func(self, *args, **kwargs))

                return tmp()

        return wrapper

    @staticmethod
    def profile_static(logger):
        """
        A decorator factory that takes a logger and returns a decorator for
        profiling both synchronous and asynchronous functions.
        """
        def decorator(func):
            @contextmanager
            def wrapping_logic():
                # The logger is now "captured" from the outer scope
                logger.time(f"Starting execution of {func.__name__}...")
                start_ts = time.monotonic()
                yield
                dur = time.monotonic() - start_ts
                logger.time(f"Execution of {func.__name__} completed in {dur:.4f} seconds.")

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if not asyncio.iscoroutinefunction(func):
                    with wrapping_logic():
                        return func(*args, **kwargs)
                else:
                    async def tmp():
                        with wrapping_logic():
                            return await func(*args, **kwargs)

                    return tmp()

            return wrapper

        return decorator
