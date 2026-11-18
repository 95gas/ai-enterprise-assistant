import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

import os
from typing import Any, List, Dict, Optional
import numpy as np
import pandas as pd
from io import StringIO
import math
import re
from copy import deepcopy
from src.common.document_processing.services.llm_service import LLMService
from src.common.prompt_manager import PromptManager
from src.common.logging.logger import DebugLogger
from src.common.models.tokenizer import TokenCounter
from src.common.document_processing.schemas.schemas import TableDescription
from config.settings import settings

MODELS_INFO_DICT = settings.models_info.model_dump()


class TableHelper:
    """Handles the different steps of processing the tables for a better retrieval and understanding from the llm."""

    def __init__(self,
                 llm_doc_service: LLMService,
                 logger: Optional[DebugLogger] = None,
                 max_retry: int = 5,
                ):

        self.logger = logger or DebugLogger(class_name=self.__class__.__name__, main_feature="DOC")
        self.logger.info("Initializing TableHelper...")

        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompts_folder = os.path.join(base_dir, "..", "prompts")
        self.prompt_manager = PromptManager(prompts_folder=prompts_folder)
        self.max_retry = max_retry
        self.counter = 0
        self.llm_doc_service = llm_doc_service
        self.tokenizer = TokenCounter(provider=MODELS_INFO_DICT["doc_model"]["provider"],
                                      model_name=MODELS_INFO_DICT["doc_model"]["custom_name"])
        self.logger.success("TableHelper ready.")

    def config_log(self, user:str):
        self.logger.set_user(user)
        self.tokenizer.logger.set_user(user)
        self.llm_doc_service.config_log(user)

    @staticmethod
    def _find_html_tables(md_text) \
            -> List[str]:
        """
        Extracts html tables from markdown text.
        :param md_text: markdown text.
        :return: list of table string formatted in html.
        """
        # Regex pattern to capture all Markdown tables
        regex = r"(<html>.*<\/html>)"
        table_pattern = re.compile(
            regex,
            re.MULTILINE
        )

        # Find all occurrences
        matches = table_pattern.finditer(md_text)
        return [match.group() for match in matches]


    def _convert_html_table_to_md(self,
                                  html_tables) \
            -> List[str]:
        """
        Convert html tables to markdown text.
        :param html_tables: the html tables.
        :return: list of table string formatted in markdown.
        """
        md_tables = []
        for html_table in html_tables:
            try:
                html = pd.read_html(html_table, index_col=0, header=0, keep_default_na=False)
                md_table = html[0].to_markdown(tablefmt="github")
                md_table = self.normalize_pandas_header(md_table, html[0])
                md_tables.append(md_table)
            except ValueError as e:
                if "No tables found matching pattern" in str(e):
                    md_tables.append("")
        return md_tables

    def reset_counter_max_retry(self):
        self.counter = 0

    async def descr_table(self, table_md, main_llm, helper_llm=None, max_retries=3) -> str:
        """Main entry point for describing a table. Retries handled by LLMCallManager."""
        prompt = self.prompt_manager.get_prompt("TABLE_DESCR").format()
        result = await self.llm_doc_service.arun(
            prompt=prompt,
            client=main_llm,
            helper_llm=helper_llm,
            text=table_md,
            max_retries=max_retries,
            structured=True,
            output_cls=TableDescription,
            label="TABLE_DESCRIPTION"
        )

        return result.table_description

    @staticmethod
    def _is_small_table(md_table: str) -> bool:
        """
        Check if a markdown table is small (less than 5 rows and 5 columns).
        :param md_table: markdown table string.
        :return: True if the table has < 5 rows and < 5 columns, False otherwise.
        """
        if not md_table:
            return True

        lines = [line.strip() for line in md_table.strip().split('\n') if line.strip()]
        if not lines:
            return True

        # Filter out the markdown separator line (e.g., |---|---|)
        content_lines = []
        for line in lines:
            # Remove borders to effectively check if it's just a separator string
            inner_content = line.strip('|')
            if not re.match(r'^[\s\-:]+$', inner_content):
                content_lines.append(line)

        num_rows = len(content_lines)
        if num_rows == 0:
            return True

        # Count columns in the first row (header row)
        first_row = content_lines[0].strip('|')
        num_cols = len(first_row.split('|'))

        return num_rows < 5 and num_cols < 5

    async def process_single_table(self,
                             table_data: tuple,
                             filename: str,
                             cache_dir: str,
                             header_rows: int,
                             max_token_table: int,
                             main_llm: Any,
                             helper_llm: Any) -> List[Dict[str, Any]]:
        """
        Worker method to process a single table asynchronously.
        """
        table_index, table_element = table_data
        sub_table_elements = []
        md_table = table_element["metadata"]["markdown_table"]

        # Check if table is small to skip LLM description
        if self._is_small_table(md_table):
            self.logger.info(f"Skipping description for table: {filename}_{table_index}")
            metadata = deepcopy(table_element["metadata"])
            metadata["table_tokens"] = self.tokenizer.count(md_table)

            # Place the raw markdown table string into the text field directly
            sub_table_elements.append({"text": md_table, "metadata": metadata})
            return sub_table_elements

        if self.need_split(md_table, header_rows, max_token_table):
            sub_tables = self.split_table(md_table, header_rows, max_token_table)
            tot_sub = len(sub_tables)

            for i, sub_table in enumerate(sub_tables):
                debug_path = os.path.join(cache_dir, f"{filename}_{table_index}_part_{i}.md")
                with open(debug_path, "w", encoding="utf-8") as file:
                    file.write(sub_table)

                # Retry logic
                descr = await self.descr_table(sub_table, main_llm, helper_llm)

                # Metadata updates
                metadata = deepcopy(table_element["metadata"])
                metadata.update({
                    "markdown_table": sub_table,
                    "chunk_number": metadata["chunk_number"] + (i / tot_sub),
                    "part": i,
                    "table_tokens": self.tokenizer.count(sub_table)
                })
                sub_table_elements.append({"text": descr, "metadata": metadata})
        else:
            # Non-split logic
            debug_path = os.path.join(cache_dir, f"{filename}_{table_index}.md")

            with open(debug_path, "w", encoding="utf-8") as file:
                file.write(md_table)

            descr = await self.descr_table(md_table, main_llm, helper_llm)

            metadata = deepcopy(table_element["metadata"])
            metadata["table_tokens"] = self.tokenizer.count(md_table)
            sub_table_elements.append({"text": descr, "metadata": metadata})

        return sub_table_elements


    @staticmethod
    def _extract_tables_from_md(md_text:str) \
            -> List[str]:
        """
        Extracts tables from markdown text.
        :param md_text: markdown text.
        :return: list of table string formatted in markdown.
        """
        # Regex pattern to capture all Markdown tables
        regex = r"(\|.*\|\s?)+"
        table_pattern = re.compile(
            regex,
            re.MULTILINE
        )

        # Find all occurrences
        matches = table_pattern.finditer(md_text)
        return [match.group() for match in matches]

    def need_split(self,
                   md_table: str,
                   header_rows: int = 10,
                   limit_tokens_sub_table: int = 10000) \
            -> bool:
        """
        Determine if a table needs to be split.
        :param md_table: the markdown table.
        :param header_rows: the number of the first rows in the table to consider as header.
        :param limit_tokens_sub_table: the maximum number of tokens the table needs to have.
        :return: true if the table needs to be split, false otherwise.
        """
        if self.tokenizer.count(md_table) > limit_tokens_sub_table:
            file = StringIO(md_table)
            df_table = pd.read_table(file, sep="|", header=0, index_col=0, skipinitialspace=True,
                                     keep_default_na=False, on_bad_lines='skip').iloc[1:]

            # drop last column
            df_table = df_table.iloc[:, :-1]

            # get header and rest of table
            header_df = df_table.iloc[:header_rows]
            sub_table_df = df_table.iloc[header_rows:]

            # process header
            _header_table = header_df.to_markdown(tablefmt="github", index=False)
            _header_table = self.normalize_pandas_header(_header_table, header_df)
            tokens_header_num = self.tokenizer.count(_header_table)

            # process sub_table
            _sub_table = sub_table_df.to_markdown(tablefmt="github", index=False)
            _sub_table = self.remove_pandas_headers(_sub_table)
            tokens_table_num = self.tokenizer.count(_sub_table)
            num_sub_tables = math.ceil(tokens_table_num / (limit_tokens_sub_table - tokens_header_num))
            return num_sub_tables > 1
        return False


    def split_table(self,
                    md_table : str,
                    header_rows: int = 10,
                    limit_tokens_sub_table: int = 10000) \
        -> list[str]:
        """
        Split a markdown table into multiple markdown tables.
        :param md_table: the markdown table.
        :param header_rows: the number of the first rows in the table to consider as header.
        :param limit_tokens_sub_table: the maximum number of tokens to consider for each sub table.
        :return: list of images_url string.
        """

        file = StringIO(md_table)
        df_table = pd.read_table(file, sep="|", header=0, index_col=0, skipinitialspace=True,
                                 keep_default_na=False, on_bad_lines='skip').iloc[1:]

        # drop last column
        df_table = df_table.iloc[:, :-1]

        # get header and rest of table
        header_df = df_table.iloc[:header_rows]
        sub_table_df = df_table.iloc[header_rows:]

        # process header
        _header_table = header_df.to_markdown(tablefmt="github", index=False)
        _header_table = self.normalize_pandas_header(_header_table, header_df)
        tokens_header_num = self.tokenizer.count(_header_table)

        # process sub_table
        _sub_table = sub_table_df.to_markdown(tablefmt="github", index=False)
        _sub_table = self.remove_pandas_headers(_sub_table)
        tokens_table_num = self.tokenizer.count(_sub_table)

        # split sub_table
        num_sub_tables = math.ceil(tokens_table_num / (limit_tokens_sub_table - tokens_header_num))
        sub_tables = np.array_split(sub_table_df, num_sub_tables)
        _sub_table_md = []
        for sub_table in sub_tables:
            sub_table = pd.DataFrame(sub_table)
            _sub_table = sub_table.to_markdown(tablefmt="github", index=False)
            _sub_table = self.remove_pandas_headers(_sub_table)
            _sub_table_md.append(_sub_table)

        # add header
        final_sub_tables = [_header_table +"\n"+ table_md for table_md in _sub_table_md]
        return final_sub_tables


    @staticmethod
    def get_rows_from_md(md_table: str)\
        ->List[str]:
        """
        Count the number of rows in a markdown table.
        :param md_table: markdown table.
        :return: the number of rows in the markdown table.
        """
        # Regex pattern to capture all the first empty cells
        regex = r"^\|.*((\|\n)|\|)"
        table_pattern = re.compile(
            regex,
            re.MULTILINE
        )
        matches = table_pattern.finditer(md_table)

        return [match.group() for match in matches]


    def remove_first_empty_column(self,
                                  md_table: str)\
        ->str:
        """
        Remove the first column from the markdown table if emtpy.
        Examples:
        Before
        |    | Unnamed: 1   | Unnamed: 2   | Unnamed: 3   |
        |----|--------------|--------------|--------------|
        |    |              |              |              |

        After
        | Unnamed: 1   | Unnamed: 2   | Unnamed: 3   |
        |--------------|--------------|--------------|
        |              |              |              |
        :param md_table: markdown table.
        :return: the markdown table without the first empty column.
        """
        # Regex pattern to capture all the first empty cells
        regex = r"^\|(\s*|\-*)+\|"
        table_pattern = re.compile(
            regex,
            re.MULTILINE
        )
        matches = table_pattern.finditer(md_table)
        empty_cells = [match.group() for match in matches]

        md_rows = self.get_rows_from_md(md_table)
        n_rows = len(md_rows)
        if n_rows == len(empty_cells):
            table = ""
            for index, row in enumerate(md_rows):
                cell = empty_cells[index]
                row = row.replace(cell, "", 1)
                table += "|"+row
            return table
        return md_table


    def normalize_pandas_header(self,
                                md_table: str,
                                df_table: pd.DataFrame = None)\
            ->str:
        """
        Remove artifact headers added when reading a string with pandas
        Examples:
        Before:
        | Unnamed: 1   | Unnamed: 2   | Unnamed: 3   |
        |--------------|--------------|--------------|
        |              |              |              |

        After:
        |              |              |              |
        |--------------|--------------|--------------|
        |              |              |              |
        :param md_table: markdown table from which to remove the column artifact header.
        :param df_table: if given, the row header will be removed from the md_table.
        :return: the md_table without artifact header.
        """
        # remove columns header
        md_table = self.remove_first_empty_column(md_table)
        _pandas_header = self.get_artifact_pandas_column_header(md_table)
        if _pandas_header:
            header = _pandas_header[0]
            pandas_header = header

            # Remove "Unnamed:"
            for word in pandas_header.split():
                if word.startswith("unnamed:") or word.startswith("Unnamed:"):
                    num_chars = len("unnamed:")
                    pandas_header = pandas_header.replace(word, " " * num_chars)

            # Remove numbers
            for word in pandas_header.split():
                if word.isdigit():
                    pandas_header = re.sub(fr'\b{word}\b', " " * len(word), pandas_header)
            md_table = md_table.replace(header, pandas_header)

        # remove rows header
        if df_table is not None:
            md_table = self.remove_artifact_rows_pandas_header(md_table, df_table)
        return md_table


    @staticmethod
    def get_artifact_pandas_column_header(
            md_table:str) -> list[str]:
        """
        Return the artifact column header from the markdown table.
        :param md_table: markdown table.
        :return: list of artifact headers.
        """
        # Regex pattern to capture all pandas header that is | unnamed: 0 | unnamed: 1 | ..
        regex = r"^\|((\s*\|)*(\s*(unnamed:|Unnamed:)* \d{1,}\s*\|)+)\n"
        table_pattern = re.compile(
            regex,
            re.MULTILINE
        )

        # Find all occurrences
        matches = table_pattern.finditer(md_table)
        return [match.group() for match in matches]


    def remove_pandas_headers(
            self,
            md_text)\
            ->str:
        """
        Replace the headers generated automatically by pandas to an empty header
        Examples:
        Before
        |    | Unnamed: 1   | Unnamed: 2   | Unnamed: 3   |
        |----|--------------|--------------|--------------|
        |    |              |              |              |

        After:
        |              |              |              |
        :param md_text: the markdown text.
        :return: the markdown text with the empty header.
        """
        md_text = self.remove_first_empty_column(md_text)
        return re.sub(r'^\|(.*\|)+\n\|(-*\|)+\n', "", md_text)


    @staticmethod
    def remove_artifact_rows_pandas_header(
            md_table: str,
            table_df: pd.DataFrame = None)\
            ->str:
        """
        Remove the artifact row headers added when reading a string with pandas
        Before:
        |  | Unnamed: 1    | Unnamed: 2    | Unnamed: 3    |
        |-:|--------------:|--------------:|--------------:|
        | 0|               |               |               |

        After:
        | Unnamed: 1    | Unnamed: 2    | Unnamed: 3    |
        |--------------:|--------------:|--------------:|
        |               |               |               |
        :param md_table: markdown table from which to remove the row artifact headers.
        :param table_df: the corresponding table in dataframe format
        :return: the md_table without the artifact header.
        """
        # Regex pattern to capture all columns header of md table
        regex = r"^\|(\s*\d+\s*|\-+\:)\|"
        table_pattern = re.compile(
            regex,
            re.MULTILINE
        )

        # Find all occurrences
        matches = table_pattern.finditer(md_table)
        num_rows_md = len([match.group() for match in matches])
        num_rows_df = len(table_df.axes[0])

        # md adds two more rows: one for the column header and one for the header separator i.e. '---'
        if num_rows_md == num_rows_df + 2:
            return re.sub(r'^\|(\s*\d*\s*|\-+\:)\|', "", md_table)
        return md_table


    @staticmethod
    def _get_consecutive_empty_rows(md_table) \
            -> List[str]:
        """
        Extracts consecutive emtpy rows from markdown table.
        :param md_table: markdown table.
        :return: list of consecutive empty rows.
        """
        # Regex pattern to capture all empty markdown rows
        regex = r"^(\|( +\|)+\n){2,}"
        table_pattern = re.compile(
            regex,
            re.MULTILINE
        )

        # Find all occurrences
        matches = table_pattern.finditer(md_table)
        return [match.group() for match in matches]


    @staticmethod
    def _get_single_empty_row(md_table) \
            -> List[str]:
        """
        Extracts each single empty row from a markdown table.
        :param md_table: markdown table.
        :return: list of empty rows.
        """
        # Regex pattern to capture all empty rows
        regex = r"^\|( +\|)+\n"
        table_pattern = re.compile(
            regex,
            re.MULTILINE
        )

        # Find all occurrences
        matches = table_pattern.finditer(md_table)
        return [match.group() for match in matches]


    def normalize_consecutive_empty_rows(self,
                                         md_table: str)\
            ->str:
        """
        Replace consecutive empty rows from markdown table with a single empty row for keeping the context separated.
        :param md_table: markdown table.
        :return: markdown table without consecutive empty rows.
        """
        empty_consecutive_rows = self._get_consecutive_empty_rows(md_table)
        if empty_consecutive_rows:
            single_empty_row = self._get_single_empty_row(empty_consecutive_rows[0])[0]
            for row in empty_consecutive_rows:
                md_table = md_table.replace(row, single_empty_row)
        return md_table