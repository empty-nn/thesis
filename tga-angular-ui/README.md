# TGA Angular UI

A clean frontend starter for the **Personalized Travel Guide Assistant** and its **RAG retrieval debugger**.

## Why this stack

This starter intentionally does **not** use Angular AI Kit or Spartan.

- Angular 21 (LTS)
- Angular Signals + zoneless change detection
- Zone.js is installed only to satisfy ngx-markdown 21's peer contract; the app itself is bootstrapped zoneless
- Tailwind CSS 4 for the custom ChatGPT-like shell
- PrimeNG 21 for data-heavy retrieval/debug UI
- ngx-markdown + Marked + Prism for assistant responses and code blocks
- Lucide Angular for icons
- Native Angular HttpClient for FastAPI integration

## Screens

### `/chat`

- ChatGPT-style dark shell
- Assistant/user messages
- Markdown rendering
- Syntax highlighting
- Copy/regenerate controls
- Loading indicator
- Responsive sidebar
- Mock mode so the UI runs before FastAPI is connected

### `/retrieval-debug`

- Query input
- Stage tabs:
  - Vector
  - BM25
  - Hybrid
  - Rerank
  - Final
- Rank + scores
- Chunk table
- Full chunk content
- Metadata inspection
- Source link
- Mock pipeline data

## Requirements

Recommended:

```bash
node --version
# Node 22.x
```

Install Angular CLI if needed:

```bash
npm install -g @angular/cli@21
```

## Run

```bash
npm install
npm start
```

Open:

```text
http://localhost:4200
```

## Backend connection

The project starts with:

```ts
useMockApi: true
```

in:

```text
src/environments/environment.ts
```

When your FastAPI backend is ready:

```ts
export const environment = {
  production: false,
  useMockApi: false,
  apiBaseUrl: 'http://localhost:8000/api',
};
```

### Chat endpoint

Expected request:

```http
POST /api/chat
Content-Type: application/json
```

```json
{
  "message": "What should I do in Hanoi for 3 days?"
}
```

Expected response:

```json
{
  "answer": "Markdown answer here...",
  "sources": [
    {
      "id": "source-1",
      "title": "Hanoi Travel Guide",
      "url": "https://example.com"
    }
  ]
}
```

### Retrieval debug endpoint

Expected request:

```http
POST /api/retrieval/debug
Content-Type: application/json
```

```json
{
  "query": "best places around Hoan Kiem Lake"
}
```

The frontend model is defined in:

```text
src/app/core/models/retrieval.models.ts
```

Return the same `RetrievalDebugRun` structure from FastAPI.

## Suggested backend retrieval stages

```text
query
  ↓
query parsing / filters
  ↓
BM25 ─────────────┐
                  ├─→ hybrid candidate pool
vector ───────────┘
                  ↓
metadata / geo boost
                  ↓
cross-encoder rerank
                  ↓
top chunks
                  ↓
LLM answer + citations
```

The debug endpoint should preserve every stage instead of returning only the final top chunks. This lets the UI compare how a document moves through the pipeline.

## Project structure

```text
src/app/
├── core/
│   ├── models/
│   │   ├── chat.models.ts
│   │   └── retrieval.models.ts
│   └── services/
│       ├── chat.service.ts
│       └── retrieval-debug.service.ts
│
├── features/
│   ├── chat/
│   │   ├── chat-page.component.ts
│   │   └── chat-page.component.html
│   │
│   └── retrieval-debug/
│       ├── retrieval-debug-page.component.ts
│       └── retrieval-debug-page.component.html
│
├── app.component.ts
├── app.component.html
├── app.config.ts
└── app.routes.ts
```

## Next recommended additions

1. Real SSE/streaming responses from FastAPI.
2. Conversation persistence.
3. Edit/save chunk metadata from Retrieval Debug.
4. Evaluation mode with expected relevant chunk IDs.
5. Side-by-side retrieval configuration comparison.
6. AI judge results for top-k retrieval.
7. P@K, Recall@K, MRR and nDCG metrics.
