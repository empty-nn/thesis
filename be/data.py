import re

import pymupdf4llm

class DataProcessing:
    def __init__(self, file_path):
        self.file_path = file_path

    def pdf_to_markdown(self):
        md_text = pymupdf4llm.to_markdown(self.file_path)
        return md_text

    def clean_markdown(self, md_text: str) -> str:

        # remove image placeholders
        md_text = re.sub(
            r"\*\*==> picture.*?End of picture text -----\*\*<br>",
            "",
            md_text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # remove html breaks
        md_text = re.sub(r"<br>", "\n", md_text)

        # remove excessive symbols/noise lines
        cleaned_lines = []

        for line in md_text.splitlines():

            stripped = line.strip()

            # skip empty
            if not stripped:
                continue

            # remove OCR garbage
            if len(re.findall(r"[A-Za-z]", stripped)) < 3:
                continue

            # remove weird symbol-heavy lines
            weird_ratio = len(re.findall(r"[^A-Za-z0-9\s]", stripped)) / max(len(stripped), 1)

            if weird_ratio > 0.45:
                continue

            # remove repeated website/footer
            if "nashtechglobal.com" in stripped.lower():
                continue

            cleaned_lines.append(stripped)

        cleaned = "\n".join(cleaned_lines)

        # normalize spaces
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        return cleaned.strip()
    
    
    def main(self):
        markdown_content = self.pdf_to_markdown()
        markdown_content = self.clean_markdown(markdown_content)
        print(markdown_content)

if __name__ == "__main__":
    file_path = f"E:\Thesis\pdf\Beginner's Guide to Vietnam Now.pdf"  # Replace with your PDF file path
    data_processor = DataProcessing(file_path)
    data_processor.main()
