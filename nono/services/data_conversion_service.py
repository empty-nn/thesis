import requests
from typing import Optional
from pathlib import Path
import shutil
import uuid
from fastapi import UploadFile
import requests

from data_building.loaders import PdfConverter, HtmlConverter, HtmlCleanerResult


class PdfConversionService:
    def __init__(self, upload_dir: str = "uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(exist_ok=True)

    def save_upload_file(self, file: UploadFile) -> Path:
        file_id = str(uuid.uuid4())
        safe_filename = Path(file.filename).name
        file_path = self.upload_dir / f"{file_id}_{safe_filename}"

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return file_path

    def convert_to_markdown(self, file_path: Path, method: str = "pymupdf") -> str:
        converter = PdfConverter(str(file_path))
        return converter.to_markdown(method=method)



DEFAULT_HEADERS = {
    "User-Agent": (
        "VictorTourismRAG/0.1 "
        "(thesis research) Python requests"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en,en-US;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


class HtmlConversionService:
    def convert_url_to_markdown(
        self,
        url: str,
        method: str = "trafilatura",
        timeout: int = 30,
    ) -> HtmlCleanerResult:
        html_text = self.fetch_html(
            url=url,
            timeout=timeout,
        )

        cleaner = HtmlConverter(
            html_text=html_text,
            source_url=url,
        )

        return cleaner.clean(method=method)

    def convert_html_text_to_markdown(
        self,
        html_text: str,
        source_url: Optional[str] = None,
        method: str = "trafilatura",
    ) -> HtmlCleanerResult:
        cleaner = HtmlConverter(
            html_text=html_text,
            source_url=source_url,
        )

        return cleaner.clean(method=method)

    def compare_url_methods(
        self,
        url: str,
        timeout: int = 30,
    ) -> list[HtmlCleanerResult]:
        html_text = self.fetch_html(
            url=url,
            timeout=timeout,
        )

        cleaner = HtmlConverter(
            html_text=html_text,
            source_name=url,
            source_url=url,
        )

        return cleaner.compare_methods()

    def fetch_html(
        self,
        url: str,
        timeout: int = 30,
    ) -> str:
        response = requests.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
        )

        response.raise_for_status()

        if not response.encoding:
            response.encoding = response.apparent_encoding

        return response.text