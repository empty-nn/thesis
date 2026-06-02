import pymupdf4llm

from ingestion.split_chunk import prepare_markdown_for_rag

pdf_path = r"pdfs\beginner_guide.pdf"

raw_md = pymupdf4llm.to_markdown(pdf_path)

chunks = prepare_markdown_for_rag(
    raw_md=raw_md,
    source_file=r"pdfs\beginner_guide.pdf",
    chunk_size=1200,
    chunk_overlap=150,
    keep_picture_text=True,
    min_picture_text_chars=80,
    separate_picture_text=True,
)

print("Total chunks:", len(chunks))

for chunk in chunks[:3]:
    print("\n--- CHUNK ---")
    print(chunk["metadata"])
    print(chunk["content"])