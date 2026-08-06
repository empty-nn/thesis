import pymupdf4llm
import requests
import trafilatura


def pdf_to_markdown(pdf_path: str):

    markdown = pymupdf4llm.to_markdown(pdf_path)

    return markdown

def html_to_markdown(url: str):

    html = requests.get(url, timeout=20).text

    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
    )

    return markdown