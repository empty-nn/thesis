OVERALL ARCHITECTURE:
    Semantic chunking
    + Hybrid retrieval
    + Reranking
    + Constraint filtering
    + Reasoning


1. Data preparation phase
PDF to markdown
   Scraping
   → Cleaning
   → Text generation
   → Chunking
   → Embedding/indexing

    I. Scraping phase:
        1. Scraping:
        2. Normalize and clean data
        3. Create readable text: using template for each type of place (AI will fill in)
        4. Validate tags with allowed list
        4. Split into semantic chunks 
        5. Attach metadata
        6. Generate embeddings
        7. Save in DB

2. Retrieval phase
   User query
    Source: 
        https://arxiv.org/pdf/2407.18716
        https://arxiv.org/pdf/2501.10868
        User query
        ↓
        AI extracts into your fixed JSON schema
        ↓
        Your code validates/normalizes it
        ↓
        Use it for filtering + retrieval

   → Metadata filtering
      + After filtering we need will use BM25 + vector search to get the most suitable chunks

   → BM25 search: search by keyword → Vector search: search by vector  from embeddings
      + After search use formula to combine these results and get list
   → Hybrid fusion: combine result from 2 search methods for final results
   
   → Reranking: use model to rerank for more accurate chunk results

   → Top relevant chunks

3. LLM phase
   Top chunks + user query
   → Reasoning
   → Recommendation
   → Final answer


------ FiD = Fusion-in-Decoder to be researched
------ agentic RAG




1. Retrieval Evaluation
   - Recall@5
        1. Definition
        Recall@5 measures whether the system can retrieve the correct relevant documents/chunks within the top 5 results.
        Formula:
            Recall@5 = Number of relevant chunks retrieved in top 5 / Total number of relevant chunks
        2. Why use it?
            In RAG, the LLM can only answer well if the retriever gives it good evidence.

            So Recall@5 answers:
            Can the retrieval system find the right information before generation?

   - Precision@5
   - nDCG@5
   - MRR
   - Context relevance

2. Generation Evaluation
   - Faithfulness
   - Answer relevance
   - Correctness
   - Citation support

3. Recommendation Evaluation
   - Constraint satisfaction rate
   - Precision@5
   - nDCG@5
   - Diversity score
   - Coverage score


# 9-Week Thesis Timeline

## Thesis Topic

Personalized Tourism Recommendation Using Large Language Models and RAG

---

# WEEK 1 — Environment & Foundation

## Goals

Stabilize development environment and finalize project architecture.

## Tasks

* Fix Python environment issues
* Finalize PostgreSQL + pgvector setup
* Finalize SQLAlchemy ORM models
* Create clean project structure
* Create requirements.txt
* Test Ollama local LLM
* Test embedding model
* Test database insertion
* Finalize metadata schema and vocabularies

## Deliverables

* Stable environment
* Working PostgreSQL database
* Working pgvector
* Working embedding generation
* Working local LLM metadata extraction

---

# WEEK 2 — Ingestion Pipeline MVP

## Goals

Build complete PDF/HTML ingestion pipeline.

## Tasks

* PDF → Markdown conversion
* HTML → Markdown conversion
* Markdown cleaning
* Semantic section splitting
* Chunking pipeline
* Metadata extraction using local LLM
* Metadata normalization
* Embedding generation
* Save chunks into PostgreSQL

## Deliverables

* Complete ingestion pipeline
* Initial chunk database
* Successfully inserted tourism chunks into DB

---

# WEEK 3 — Tourism Dataset Building

## Goals

Build tourism knowledge base.

## Tasks

Collect and process:

* Vietnam tourism PDFs
* Official tourism websites
* Travel guides
* Attraction descriptions
* Restaurant descriptions
* Hotel descriptions

Focus cities:

* Hanoi
* Ho Chi Minh City
* Da Nang
* Hoi An
* Hue
* Ha Long

## Deliverables

* Initial tourism dataset
* 500–3000 chunks stored in DB

---

# WEEK 4 — Retrieval System

## Goals

Implement retrieval pipeline.

## Tasks

Implement:

* Vector retrieval
* BM25 retrieval
* Metadata filtering
* Hybrid retrieval

Integrate:

* LangChain retrieval orchestration
* PostgreSQL + pgvector

## Deliverables

* Semantic retrieval system
* Keyword retrieval system
* Hybrid retrieval pipeline

---

# WEEK 5 — Reranking & Search Optimization

## Goals

Improve retrieval quality.

## Tasks

Implement:

* CrossEncoder reranker
* BGE reranker
* Query preprocessing
* Metadata-aware reranking
* Search optimization

Example query:

* “family-friendly cultural attractions in Hanoi”

## Deliverables

* Reranked retrieval pipeline
* Improved retrieval precision
* Better contextual relevance

---

# WEEK 6 — Recommendation & Reasoning Layer

## Goals

Build personalized recommendation system.

## Tasks

Implement:

* User preference input
* Personalized filtering
* Recommendation generation
* Explanation generation
* LLM reasoning layer

Example:

* “Recommended because this attraction is family-friendly and culturally significant.”

## Deliverables

* Personalized tourism recommendation prototype
* Recommendation explanation system

---

# WEEK 7 — Evaluation Phase

## Goals

Evaluate retrieval and recommendation quality.

## Tasks

### Retrieval Evaluation

* Precision@5
* nDCG@5
* MRR
* Context relevance

### Generation Evaluation

* Faithfulness
* Answer relevance
* Correctness

### Recommendation Evaluation

* Constraint satisfaction
* Diversity score
* Coverage score

Compare:

* Vector-only retrieval
* Hybrid retrieval
* Hybrid + reranking

## Deliverables

* Evaluation tables
* Performance charts
* Experimental comparison results

---

# WEEK 8 — UI & Thesis Writing

## Goals

Build demo system and write thesis chapters.

## Tasks

Build simple UI:

* Streamlit or FastAPI frontend

Write:

* Introduction
* Literature Review
* Methodology
* System Architecture
* Experiments
* Evaluation

## Deliverables

* Working demo
* 80% thesis completion

---

# WEEK 9 — Finalization & Defense Preparation

## Goals

Finalize thesis and prepare presentation.

## Tasks

* Fix remaining bugs
* Improve UI
* Improve figures and diagrams
* Finalize thesis formatting
* Prepare slides
* Prepare demo scenario
* Rehearse defense presentation

## Deliverables

* Final thesis
* Final presentation slides
* Demo-ready system

---

# Final System Architecture

```text
PDF / HTML
→ Markdown
→ Cleaning
→ Semantic Chunking
→ AI Metadata Extraction
→ Embeddings
→ PostgreSQL + pgvector

Retrieval:
→ BM25
→ Vector Search
→ Hybrid Fusion
→ Reranking

Recommendation:
→ Personalized Filtering
→ LLM Reasoning
→ Recommendation Generation
```

---

# Expected Thesis Contributions

* AI-enriched tourism ingestion pipeline
* Metadata-aware tourism RAG system
* Hybrid retrieval for tourism recommendation
* Personalized tourism recommendation using LLM reasoning
* Comparative evaluation of retrieval approaches
