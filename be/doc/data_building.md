# Data Building Workflow: From Raw Tourism Data to Intelligent Retrieval

# WEB 
NEXT
│
├── 1. Hue
│      visithue.vn
│
├── 2. Nha Trang
│      nhatrang-travel.com/en
│
├── 3. Ha Long
│      halongtourism.com.vn/en
│      halongbay.com.vn/en
│
├── 4. Ninh Binh
│      dulichninhbinh.com.vn/en
│
├── 5. Hoi An
│      hoianworldheritage.org.vn/en
│      UNESCO
│
├── 6. Ho Chi Minh City
│      visithcmc.vn
│
└── 7. Hanoi
       Vietnam.travel
       + official attraction websites
# 1. Purpose of the Data Building Pipeline

The quality of a Retrieval-Augmented Generation (RAG) system depends heavily on the quality of its data pipeline.

The proposed tourism recommendation system requires a structured and scalable data-building workflow capable of:

* collecting tourism information,
* cleaning noisy documents,
* generating semantic metadata,
* creating embeddings,
* and preparing high-quality retrieval chunks.

The pipeline transforms raw tourism content into a semantic tourism knowledge base optimized for:

* retrieval,
* recommendation,
* personalization,
* and itinerary generation.

---

# 2. Full Data Building Workflow

```text id="9gjlwm"
Raw Tourism Sources
    ├── PDFs
    ├── HTML Websites

→ Scraping / Data Collection

→ Content Extraction
    ├── PDF → Markdown
    ├── HTML → Markdown

→ Markdown Cleaning & Normalization

→ Semantic Structuring

→ Chunking

→ AI Metadata Extraction

→ Metadata Normalization

→ Embedding Generation

→ Database Storage

→ Hybrid Retrieval Indexing
```

---

# 3. Raw Tourism Data Sources

The system collects tourism data from multiple heterogeneous sources.

## Example Sources

### PDFs

* travel brochures,
* tourism booklets,
* government tourism guides,
* travel itineraries.

### HTML Websites

* tourism blogs,
* official tourism websites,
* attraction pages,
* hotel descriptions.

### APIs

* weather APIs,
* tourism APIs,
* event APIs,
* maps services.

### OCR Sources

* scanned brochures,
* image-based tourism documents,
* travel advertisements.

---

# Why Multiple Sources Matter

Using multiple sources improves:

* knowledge diversity,
* retrieval coverage,
* recommendation richness,
* and tourism information completeness.

---

# 4. Content Extraction

## PDF to Markdown

PDF documents are converted into Markdown format.

Markdown preserves:

* headings,
* lists,
* sections,
* and semantic structure.

This is important because semantic structure improves:

* chunking,
* retrieval quality,
* and contextual understanding.

---

## HTML to Markdown

Tourism websites are converted into clean readable Markdown.

The extraction pipeline removes:

* navigation bars,
* advertisements,
* cookie banners,
* unrelated UI elements,
* and formatting noise.

---

## OCR Extraction

OCR extraction handles:

* scanned tourism materials,
* images,
* and non-text PDFs.

---

# Why Markdown Is Used

Markdown provides:

* lightweight structure,
* readable formatting,
* semantic section boundaries,
* and better chunking quality.

Compared to raw plain text, Markdown preserves:

* headings,
* itinerary sections,
* attraction categories,
* and contextual hierarchy.

---

# 5. Markdown Cleaning & Normalization

Raw extracted content often contains:

* OCR noise,
* broken formatting,
* duplicated text,
* irrelevant UI content,
* and navigation artifacts.

The cleaning stage removes:

* image placeholders,
* cookie banners,
* malformed symbols,
* duplicated headers,
* and irrelevant navigation text.

---

# Why Cleaning Matters

Poorly cleaned documents lead to:

* noisy chunks,
* weak retrieval,
* poor embeddings,
* and irrelevant recommendations.

High-quality retrieval strongly depends on clean semantic content.

---

# 6. Semantic Structuring

After cleaning, documents are semantically structured using:

* headings,
* itinerary sections,
* attraction categories,
* and contextual boundaries.

Example structure:

```markdown id="jlwm101"
## Day 1
### Ba Na Hills

## Day 2
### Hoi An Ancient Town
```

This stage preserves:

* document hierarchy,
* semantic relationships,
* and itinerary organization.

---

# Why Semantic Structuring Matters

Semantic structure improves:

* chunk coherence,
* retrieval relevance,
* and itinerary reasoning.

It also supports:

* hierarchical retrieval,
* semantic chunking,
* and context-aware recommendations.

---

# 7. Semantic Chunking

The system splits documents into semantically meaningful chunks.

Unlike fixed-size chunking, semantic chunking attempts to preserve:

* complete attraction descriptions,
* itinerary sections,
* and contextual continuity.

---

# Example

Instead of splitting every 500 tokens arbitrarily:

The system attempts to preserve:

* complete itinerary sections,
* attraction descriptions,
* and tourism context.

---

# Why Chunking Matters

Chunking quality directly affects:

* retrieval precision,
* context completeness,
* reranking quality,
* and final recommendation generation.

Poor chunking can:

* break semantic meaning,
* split itineraries incorrectly,
* and reduce retrieval accuracy.

---

# 8. AI Metadata Extraction

Each chunk is processed by an LLM-based metadata extraction system.

The system extracts structured tourism metadata such as:

* city,
* country,
* place type,
* activities,
* travel styles,
* suitable traveler groups,
* and semantic topics.

---

# Example Metadata

```json id="jlwm102"
{
  "city": "Da Nang",
  "place_type": "beach",
  "travel_styles": ["family", "relaxation"],
  "activities": ["swimming", "photography"],
  "chunk_topic": "attraction"
}
```

---

# Why Metadata Extraction Matters

Metadata enables:

* metadata-aware retrieval,
* semantic filtering,
* personalization,
* reranking,
* and context-aware recommendations.

Without metadata, retrieval depends only on vector similarity.

---

# 9. Shared Tourism Ontology

The metadata system follows a controlled tourism ontology.

Example ontology categories:

* place types,
* activities,
* travel styles,
* suitable traveler groups,
* and semantic chunk topics.

---

# Why Ontology Matters

A shared ontology ensures:

* consistent metadata,
* standardized retrieval,
* cleaner filtering,
* and stronger semantic reasoning.

It also improves:

* semantic query parsing,
* retrieval precision,
* and recommendation explainability.

---

# 10. Metadata Normalization

Extracted metadata is normalized into standardized formats.

Examples:

* lowercase normalization,
* duplicate removal,
* ontology matching,
* and synonym normalization.

---

# Example

```text id="jlwm103"
family-friendly
→ family
```

```text id="jlwm104"
historic
→ history
```

---

# Why Normalization Matters

Normalization prevents:

* inconsistent metadata,
* duplicate concepts,
* and weak retrieval filtering.

It improves:

* retrieval consistency,
* semantic matching,
* and ontology quality.

---

# 11. Embedding Generation

Each semantic chunk is converted into vector embeddings using sentence-transformer models.

Example embedding models:

* all-MiniLM-L6-v2
* BGE models
* multilingual embedding models

Embeddings capture:

* semantic meaning,
* contextual similarity,
* and conceptual relationships.

---

# Why Embeddings Matter

Embeddings enable:

* semantic retrieval,
* similarity search,
* paraphrase matching,
* and concept-aware search.

This is the foundation of vector retrieval.

---

# 12. Database Storage

The processed tourism knowledge is stored inside PostgreSQL with pgvector support.

The database stores:

* chunk text,
* embeddings,
* metadata,
* ontology fields,
* and retrieval indexes.

---

# Stored Information

Each chunk may contain:

* semantic content,
* city,
* travel style,
* activities,
* suitable traveler groups,
* vector embeddings,
* and retrieval metadata.

---

# Why Structured Storage Matters

Structured storage enables:

* metadata-aware filtering,
* hybrid retrieval,
* scalable retrieval,
* reranking,
* and personalized recommendation generation.

---

# 13. Hybrid Retrieval Indexing

The final database supports:

* vector retrieval,
* BM25 retrieval,
* and metadata-aware filtering.

This enables:

* semantic retrieval,
* exact keyword matching,
* and hybrid ranking.

---

# Why Hybrid Indexing Matters

Different retrieval methods have different strengths.

Hybrid indexing improves:

* recall,
* retrieval robustness,
* geographic relevance,
* and recommendation quality.

---

# 14. Final Knowledge Base

After the full data-building workflow, the system produces a structured tourism knowledge base optimized for:

* semantic retrieval,
* personalized recommendation,
* itinerary generation,
* reranking,
* and context-aware planning.

The final knowledge base combines:

* semantic chunks,
* structured metadata,
* embeddings,
* ontology information,
* and retrieval indexes.

---

# 15. Overall Importance of the Data Pipeline

The data-building workflow is one of the most important components of the entire RAG system.

High-quality retrieval depends on:

* clean data,
* semantic chunking,
* structured metadata,
* ontology consistency,
* and embedding quality.

The proposed pipeline transforms raw tourism documents into a structured semantic tourism knowledge system suitable for:

* intelligent retrieval,
* adaptive recommendation,
* and personalized itinerary planning.
