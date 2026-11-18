import os
import shutil
from src.common.logging.logger import DebugLogger
import subprocess
from pathvalidate import sanitize_filepath

def delete_dir_content(folder_path:str):
    """
    Delete all content inside a folder.
    :param folder_path: path of the folder to delete.
    """
    logger = DebugLogger()
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            logger.error('Failed to delete %s. Reason: %s' % (file_path, e))
            raise e

def merge_lists_without_empty(list1, list2):
    """
    Merges two lists, excluding any "falsy" elements.

    Falsy elements include: None, False, 0, "", [], {}, ().

    Args:
      list1: The first list.
      list2: The second list.

    Returns:
      A new list containing all non-empty elements from both lists.
    """
    combined_list = list1 + list2
    return [item for item in combined_list if item]


def write_md_file(md_pages:list[dict],
                  out_dir:str,
                  filename:str,
                  paginated:bool=False):
    """
    Save markdown pages
    :param filename: Name of the file being processed.
    :param md_pages: List of dictionaries containing the markdown pages of the files.
    :param out_dir: Directory where the markdown files will be saved.
    :param paginated: Whether the markdown pages should be paginated.
    """
    os.makedirs(out_dir, exist_ok=True)
    if paginated:
        for index, page in enumerate(md_pages):
            page_str =  sanitize_filepath(str(page["metadata"]["page_number"])) if "page_number" in page["metadata"].keys() else str(index+1)
            _filename = out_dir + f'/{filename}_page{page_str}.md'
            with open(_filename, "w", encoding="utf8") as f:
                f.write(page["page_content"])
    else:
        md_content = ""
        for index, page in enumerate(md_pages):
            md_content += page["page_content"]
        _filename = out_dir + f'/{sanitize_filepath(str(filename))}.md'
        with open(_filename, "w", encoding="utf8") as f:
            f.write(md_content)

def delete_file(path: str):
    """Delete file"""
    try:
        os.unlink(path)
    except Exception as e:
        raise e


def convert_file_to_pdf(input_path, output_dir):
    """Convert any file to pdf"""
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"The input file {input_path} does not exist.")

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        'soffice',
        '--convert-to', 'pdf',
        '--outdir', str(output_dir),
        str(input_path)
    ]

    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if process.returncode != 0:
        error_msg = process.stderr.decode().strip()
        output_msg = process.stdout.decode().strip()
        raise RuntimeError(f"LibreOffice conversion failed.\nStdErr: {error_msg}\nStdOut: {output_msg}")