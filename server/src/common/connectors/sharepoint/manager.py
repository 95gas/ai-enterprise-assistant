import io
import os
import re
import tempfile
import mimetypes
import subprocess
from typing import Dict
from docx import Document
from office365.sharepoint.client_context import ClientContext
from office365.runtime.auth.client_credential import ClientCredential

from src.common.logging.logger import DebugLogger
from config.settings import settings

TENANT_ID = settings.connectors.sharepoint_tenant_id
CLIENT_ID = settings.connectors.sharepoint_client_id
CLIENT_SECRET = settings.connectors.sharepoint_client_secret
STORAGE_TEMP_DOCS = settings.STORAGE_TEMP_DOCS


class SharePointManager:
    def __init__(self, site_name: str):
        self.site_name = site_name
        self.logger = DebugLogger(class_name=self.__class__.__name__, main_feature="SHAREPOINT")
        self.ctx = None
        if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
            raise ConnectionAbortedError("SharePoint credentials are missing. Please setup a 'sharepoint.env' in your deployment folder.")
        self.logger.success(f"{self.__class__.__name__} initiated for site: {self.site_name}")

    def __enter__(self):
        self._authenticate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._disconnect()
        if exc_type:
            self.logger.error(f"Session closed with error: {exc_val}")
        else:
            self.logger.success("Session closed successfully.")

    def _authenticate(self):
        site_url = f"https://{TENANT_ID}.sharepoint.com/sites/{self.site_name}"
        try:
            creds = ClientCredential(CLIENT_ID, CLIENT_SECRET)
            self.ctx = ClientContext(site_url).with_credentials(creds)
            self.ctx.web.get().execute_query()
            self.logger.info(f"Connected to site: {site_url}")
        except Exception as e:
            self.logger.error(f"Failed to authenticate: {e}")
            raise ConnectionError(f"SharePoint connection failed: {e}")

    def _disconnect(self):
        self.ctx = None
        self.logger.info("Context cleared (Disconnected).")

    def get_files_from_folder(self, folder_name: str):
        if not self.ctx:
            raise RuntimeError("No active connection. Use 'with SharePointManager(...)'.")

        try:
            folder_url = f"/sites/{self.site_name}/{folder_name}"
            folder = self.ctx.web.get_folder_by_server_relative_url(folder_url)
            files = folder.files
            self.ctx.load(files)
            self.ctx.execute_query()
            return files
        except Exception as e:
            self.logger.error(f"Error retrieving files from '{folder_name}': {e}")
            return []

    def get_base_url(self) -> str: 
        return self.ctx.base_url.split("/sites/")

    def get_file_content(self, file_item):
        if not self.ctx:
            raise RuntimeError("No active connection.")
        try:
            file_content = file_item.get_content()
            self.ctx.execute_query()
            return file_content.value
        except Exception as e:
            self.logger.error(f"Error downloading file {file_item.name}: {e}")
            return None

    @staticmethod
    def sanitize_name(name: str) -> str:
        """Sanitizes filename while preserving the extension."""
        base_name, ext = os.path.splitext(name)
        safe_base = re.sub(r'[^a-zA-Z0-9-]', '_', base_name)
        return safe_base + ext

    def save_file_to_local(self, file_item, output_directory: str) -> Dict[str, str]:
        try:
            os.makedirs(output_directory, exist_ok=True)

            raw_content = self.get_file_content(file_item)
            if raw_content is None:
                raise ValueError(f"Could not retrieve content for {file_item.name}")

            safe_name = self.sanitize_name(file_item.name)
            file_path = os.path.join(output_directory, safe_name)

            mime_type, _ = mimetypes.guess_type(file_path)
            file_type = mime_type or "application/octet-stream"

            with open(file_path, "wb") as f:
                f.write(raw_content)

            self.logger.success(f"File saved successfully at: {file_path}")
            return {"file_path": file_path, 
                    "file_type": file_type,
                    "file_item": file_item}
        except Exception as e:
            self.logger.error(f"Failed to save binary file: {e}")
            raise e

    def save_text_to_local(self, file_item, output_directory):
        """
        Parses the file content and saves the extracted text as a .txt file locally.
        """
        try:
            result = self.send_to_processing_pipeline(file_item)
            if not result["success"]:
                raise ValueError(f"Could not extract text: {result['text']}")

            if not os.path.exists(output_directory):
                os.makedirs(output_directory)

            processed_filename = self.sanitize_name(f"{file_item.name}.md")
            file_path = os.path.join(output_directory, processed_filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(result["text"])

            self.logger.info(f"Text content saved successfully at: {file_path}")
            return file_path
        except Exception as e:
            self.logger.error(f"Failed to save text file: {e}")
            raise e

    def send_to_processing_pipeline(self, file_item):
        """Get file content and route to the correct parser by extension.

        Returns a dict with keys:
          - 'ext': extension,
          - 'name': file name,
          - 'text': extracted text (or error message),
          - 'success': bool
        """
        try:
            raw = self.get_file_content(file_item)
        except Exception as e:
            return {"ext": None, "name": getattr(file_item, "name", None),
                    "text": f"Failed to download file content: {e}", "success": False}

        ext = os.path.splitext(getattr(file_item, "name", "") or "")[1].lower()
        if not ext:
            return {"ext": ext, "name": getattr(file_item, "name", None),
                    "text": "No extension detected.", "success": False}

        try:
            if ext == ".docx":
                text = self.parse_docx(raw)
            elif ext == ".doc":
                text = self.parse_doc(raw)
            elif ext == ".pdf":
                text = self.parse_pdf(raw)
            elif ext == ".pptx":
                text = self.parse_pptx(raw)
            elif ext == ".xlsx":
                text = self.parse_xlsx(raw)
            elif ext == ".xls":
                text = self.parse_xls(raw)
            else:
                raise ValueError(f"Unsupported extension: {ext}")
            return {"name": getattr(file_item, "name", None),
                    "text": text, 
                    "success": True}
        except Exception as e:
            return {"name": getattr(file_item, "name", None),
                    "text": f"Processing pipeline error: {e}", 
                    "success": False}
        

    # --- Doc Processing ------------------------------------------------------------------------------------------------------------------------------------
    def parse_docx(self, binary_data):
        """Parse .docx binary data into text, including paragraphs, tables, textboxes, headers and footers.

        Notes:
        - python-docx's Document.paragraphs can miss text embedded in headers/footers and some drawing/textbox constructs.
        - This implementation walks the underlying XML to find all w:p/w:t nodes in the main document and in headers/footers,
        which captures table cell text and many textboxes as well.
        """
        try:
            # WordprocessingML namespace
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

            stream = io.BytesIO(binary_data)
            doc = Document(stream)

            paragraphs = []

            # 1) Extract paragraph text from the main document part (body).
            #    Using the underlying XML finds paragraphs inside tables and many kinds of textboxes.
            for p in doc.element.body.findall('.//w:p', ns):
                texts = [t.text for t in p.findall('.//w:t', ns) if t.text]
                if texts:
                    paragraphs.append(''.join(texts))

            # 2) Extract headers and footers for each section (covers header/footer text and many textboxes inside them).
            for section in doc.sections:
                # Header
                try:
                    header_elm = section.header._element
                    for p in header_elm.findall('.//w:p', ns):
                        texts = [t.text for t in p.findall('.//w:t', ns) if t.text]
                        if texts:
                            paragraphs.append(''.join(texts))
                except Exception:
                    # If header not present or some sections not linked, ignore and continue
                    pass

                # Footer
                try:
                    footer_elm = section.footer._element
                    for p in footer_elm.findall('.//w:p', ns):
                        texts = [t.text for t in p.findall('.//w:t', ns) if t.text]
                        if texts:
                            paragraphs.append(''.join(texts))
                except Exception:
                    pass

            # Return joined text (preserves a paragraph-per-line structure)
            return "\n".join(paragraphs)

        except Exception as e:
            return f"Error parsing DOCX: {e}"


    def parse_txt(self, binary_data):
        """Attempts to decode binary data as UTF-8 text."""
        try:
            return binary_data.decode('utf-8')
        except UnicodeDecodeError:
            return "Binary data (PDF/Image/Etc.) - Cannot decode as text."
    
    def parse_doc(self, binary_data):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "temp_doc.doc")
            
            with open(input_path, "wb") as f:
                f.write(binary_data)
                
            subprocess.run([
                'soffice', '--headless', '--convert-to', 'docx', 
                input_path, '--outdir', tmp_dir
            ], check=True, capture_output=True)
            
            output_path = os.path.join(tmp_dir, "temp_docx.docx")
            with open(output_path, "rb") as f:
                converted_data = f.read()
        return self.parse_docx(converted_data)
    

    def update_metadata(self, file_item, metadata_dict):
        try:
            # 1. Ensure we have the ListItem associated with the File
            item = file_item.listItemAllFields
            self.ctx.load(item)
            self.ctx.execute_query()

            self.logger.info(f"Available keys: {item.properties.keys()}")

            updates = {}
            for k, v in metadata_dict.items():
                if isinstance(v, list):
                    updates[k] = ";#".join(str(x) for x in v)
                else:
                    updates[k] = str(v) if v is not None else ""

            self.logger.info(updates)

            # 3. Execute the update
            item.validate_update_list_item(updates)
            self.ctx.execute_query()
            
            print(f"Successfully updated: {file_item.name}")
            return True
        except Exception as e:
            print(f"Error updating item: {e}")
            return False


    def parse_pptx(self, binary_data):
        """Extract text from PPTX slides and tables using python-pptx."""
        try:
            from pptx import Presentation
            prs = Presentation(io.BytesIO(binary_data))
            texts = []
            for slide in prs.slides:
                # slide shapes (text frames)
                for shape in slide.shapes:
                    try:
                        if hasattr(shape, "has_text_frame") and shape.has_text_frame:
                            txt = shape.text
                            if txt:
                                texts.append(txt)
                    except Exception:
                        # ignore individual shape extraction errors
                        pass

                    # tables inside shapes
                    try:
                        if hasattr(shape, "has_table") and shape.has_table:
                            tbl = shape.table
                            for r in tbl.rows:
                                row_vals = [cell.text for cell in r.cells if cell.text]
                                if row_vals:
                                    texts.append("\t".join(row_vals))
                    except Exception:
                        pass
            return "\n".join([t for t in texts if t])
        except Exception as e:
            return f"Error parsing PPTX: {e}"


    def parse_xlsx(self, binary_data):
        """Extract text from XLSX using openpyxl (read-only)."""
        try:
            from openpyxl import load_workbook
            wb = load_workbook(filename=io.BytesIO(binary_data), read_only=True, data_only=True)
            texts = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    row_vals = [str(c) for c in row if c is not None and c != ""]
                    if row_vals:
                        texts.append("\t".join(row_vals))
            return "\n".join(texts)
        except Exception as e:
            return f"Error parsing XLSX: {e}"


    def parse_xls(self, binary_data):
        """Extract text from legacy XLS using xlrd (via a temporary file)."""
        try:
            import xlrd
            with tempfile.NamedTemporaryFile(suffix=".xls") as tmp:
                tmp.write(binary_data)
                tmp.flush()
                book = xlrd.open_workbook(tmp.name)
                texts = []
                for sheet in book.sheets():
                    for rx in range(sheet.nrows):
                        row = sheet.row_values(rx)
                        row_vals = [str(c) for c in row if c is not None and c != ""]
                        if row_vals:
                            texts.append("\t".join(row_vals))
                return "\n".join(texts)
        except Exception as e:
            return f"Error parsing XLS: {e}"
    

    def parse_pdf(self, binary_data):
        """Extract text from PDF using PyPDF2."""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(binary_data))
            pages = []
            for p in reader.pages:
                text = p.extract_text()
                if text:
                    pages.append(text)
            return "\n".join(pages)
        except Exception as e:
            return f"Error parsing PDF: {e}"