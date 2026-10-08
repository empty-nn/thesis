# Restored Data Building page

The Angular page is `/data-building`, linked in the Workspace sidebar.
All `/api/data-building/*` endpoints require the existing signed-in session.

1. Extract a public HTML URL with Trafilatura or Markdownify, or upload a text-based PDF.
2. Review/edit raw Markdown and run the existing Markdown cleaner.
3. Review source metadata manually (no paid AI metadata requests).
4. Preview heading-aware chunks with configurable size/overlap.
5. Confirm saving. The shared, already-loaded MiniLM model generates 384-dimensional
   embeddings, and the document/chunks are committed atomically to the configured database.

Only active users whose emails are in the comma-separated environment variable
`DATA_BUILDING_ADMIN_EMAILS` can save. With no configured administrators, saving
is disabled; signed-in users can still preview the construction steps.

Existing documents are not overwritten. Duplicate source URLs or PDF hashes return
HTTP 409. New evidence is marked unverified and metadata is labeled manual.
No uploaded PDFs are retained on the container filesystem.

Limits: 8 MB / 100 pages per PDF, 2 MB downloaded HTML, 200,000 extracted characters,
250 chunks per document. Scanned PDFs must be OCR-processed first. URL extraction
validates every redirect and connects only to resolved public addresses.

Tests: `.venv/Scripts/python.exe -m unittest discover -s tests -v` from `be`.
