# Personalized Tourism Recommendation System Using LLM and Hybrid RAG

## System Architecture and Research Ideas Summary

# 1. Project Vision

The goal of this thesis is to build a personalized tourism recommendation and itinerary planning system using:

* Large Language Models (LLMs)
* Retrieval-Augmented Generation (RAG)
* Semantic retrieval
* Metadata-aware filtering
* Hybrid retrieval
* Context-aware recommendation

Instead of functioning as a simple chatbot, the system aims to behave like an intelligent tourism assistant capable of:

* understanding user intent,
* retrieving relevant tourism knowledge,
* adapting to user preferences,
* using external real-time information,
* and generating personalized travel recommendations.

---

# 2. Why Traditional RAG Is Not Enough

Basic RAG systems usually follow this architecture:

```text
User Query
→ Embedding Search
→ Retrieve Chunks
→ LLM Answer
```

This approach has several limitations:

* Retrieval depends only on vector similarity
* Weak understanding of user intent
* No personalization
* No memory
* No reranking
* No metadata filtering
* No real-time adaptation
* High chance of irrelevant retrieval

Example problem:

Query:

```text
family-friendly activities in Da Nang
```

Basic vector retrieval may incorrectly rank:

* Hue attractions
* unrelated cultural places
* generic tourism chunks

because semantic similarity alone is insufficient.

---

# 3. Proposed System Architecture

The proposed architecture extends traditional RAG with modern retrieval techniques.

## Full Architecture

```text
User Query
→ Semantic Query Parsing
→ User Memory Integration
→ Metadata-aware Retrieval
→ Hybrid Retrieval
    ├── Vector Search
    └── BM25 Search
→ Score Fusion
→ CrossEncoder Reranking
→ Retrieval Confidence Evaluation
→ Context-aware Reasoning
→ Final Recommendation / Itinerary
```

---

# 4. Semantic Query Parsing

## Purpose

Semantic query parsing converts natural language queries into structured metadata.

Instead of treating the query as plain text, the system extracts:

* city,
* travel style,
* activities,
* suitable traveler type,
* place type,
* trip intent,
* and other semantic constraints.

---

## Example

User query:

```text
family-friendly cultural attractions in Da Nang
```

Parsed metadata:

```json
{
  "city": "Da Nang",
  "travel_styles": ["family", "culture"],
  "place_types": ["attraction"]
}
```

---

## Why It Helps

Semantic parsing improves:

* retrieval accuracy,
* metadata filtering,
* personalization,
* itinerary quality,
* and recommendation relevance.

Without semantic parsing, retrieval relies only on text similarity.

---

# 5. Metadata-aware Retrieval

## Purpose

Metadata-aware retrieval filters or boosts chunks using structured metadata.

The system stores metadata such as:

* city,
* place type,
* activities,
* travel styles,
* suitable traveler groups,
* and chunk topics.

---

## Example

Query:

```text
family activities in Da Nang
```

The retrieval system can prioritize:

```text
city = Da Nang
travel_style = family
```

before vector search.

---

## Why It Helps

Metadata-aware retrieval:

* reduces irrelevant chunks,
* improves geographic relevance,
* improves personalization,
* and increases retrieval precision.

---

# 6. Hybrid Retrieval

## Purpose

The system combines:

* dense vector retrieval,
* and sparse keyword retrieval.

### Dense Retrieval

Uses semantic embeddings.

### Sparse Retrieval

Uses BM25 keyword matching.

---

## Why Both Are Needed

### Vector Search Strengths

* understands semantic meaning
* handles paraphrases
* retrieves conceptually related chunks

### Vector Search Weaknesses

* may retrieve semantically similar but geographically incorrect chunks

---

### BM25 Strengths

* exact keyword matching
* strong for named entities and locations

### BM25 Weaknesses

* weak semantic understanding

---

## Hybrid Retrieval Benefits

Combining both improves:

* recall,
* precision,
* robustness,
* and retrieval quality.

---

# 7. CrossEncoder Reranking

## Purpose

Initial retrieval retrieves candidate chunks.

Reranking then evaluates:

* how relevant each chunk is to the query.

The reranker uses:

* query,
* chunk,
* and contextual interaction.

---

## Why It Helps

Reranking:

* improves ranking quality,
* reduces noisy chunks,
* improves final recommendation relevance,
* and fixes many retrieval ordering problems.

This is one of the most important improvements in modern RAG systems.

---

# 8. Shared Tourism Ontology

## Purpose

The system uses a centralized vocabulary/ontology shared across:

* ingestion,
* metadata extraction,
* retrieval,
* reranking,
* and recommendation generation.

---

## Example Ontology Categories

### Place Types

* attraction
* beach
* museum
* restaurant
* hotel
* temple

### Travel Styles

* family
* culture
* adventure
* luxury
* photography

### Activities

* sightseeing
* hiking
* photography
* swimming

### Suitable For

* families
* couples
* backpackers
* solo travelers

---

## Why It Helps

A shared ontology:

* keeps metadata consistent,
* improves filtering,
* improves personalization,
* and supports semantic retrieval.

---

# 9. User Memory System

## Purpose

The memory system stores long-term user preferences.

---

## Example Memory

```json
{
  "preferred_cities": ["Hoi An", "Hue"],
  "travel_styles": ["culture", "food"],
  "budget": "mid_range"
}
```

---

## Why It Helps

Memory allows:

* personalized recommendations,
* adaptive itinerary planning,
* better retrieval ranking,
* and long-term user modeling.

Without memory:

* recommendations remain generic.

---

# 10. Context-aware Planning

## Purpose

The system combines:

* static tourism knowledge,
* with real-time external information.

---

## Example External APIs

* Weather API
* Maps API
* Event API
* Transportation API

---

## Example

If the weather forecast predicts rain:

The system can replace:

* beach activities

with:

* museums,
* cafes,
* food tours,
* or indoor attractions.

---

## Why It Helps

This enables:

* dynamic itinerary adjustment,
* context-aware recommendations,
* and real-world practical planning.

---

# 11. Retrieval Confidence Evaluation

## Purpose

The system evaluates whether retrieved chunks are reliable enough.

---

## Problem

Users may ask questions outside the tourism database.

Example:

```text
What is Vietnam work visa policy?
```

If retrieval quality is poor:

* the system should avoid hallucination.

---

## Possible Behaviors

* fallback response,
* web search fallback,
* external API usage,
* or confidence-based refusal.

---

## Why It Helps

This:

* reduces hallucinations,
* improves trustworthiness,
* and improves system reliability.

---

# 12. Agentic RAG Direction

## Purpose

Agentic RAG allows the system to:

* choose tools dynamically,
* gather multiple information sources,
* and reason over them.

---

## Example Workflow

```text
User Query
→ Query Understanding
→ Weather API
→ Tourism RAG
→ User Memory
→ Itinerary Generator
```

---

## Why It Helps

Agentic behavior supports:

* adaptive planning,
* multi-source reasoning,
* and intelligent orchestration.

---

# 13. Proposed Research Contribution

The proposed contribution is not merely:

* a chatbot,
* or a basic vector database.

Instead, the system contributes:

* semantic tourism retrieval,
* metadata-aware recommendation,
* personalized travel planning,
* hybrid retrieval architecture,
* and context-aware itinerary generation.

---

# 14. System Evolution Roadmap

## Phase 1

Basic ingestion pipeline

* PDF/HTML → Markdown
* Chunking
* Embeddings
* Vector retrieval

---

## Phase 2

Metadata extraction

* tourism ontology
* AI metadata generation
* metadata normalization

---

## Phase 3

Hybrid retrieval

* vector search
* BM25 retrieval
* metadata filtering

---

## Phase 4

Advanced retrieval

* reranking
* semantic query parsing
* weighted scoring

---

## Phase 5

Personalization

* user memory
* preference-aware retrieval
* adaptive recommendations

---

## Phase 6

Context-aware planning

* weather APIs
* dynamic itinerary adjustment
* real-time adaptation

---

## Phase 7

Agentic enhancement

* tool routing
* multi-source reasoning
* adaptive planning workflows

---

# 15. Final Research Direction

The thesis ultimately aims to build:

```text
A semantic, personalized, context-aware tourism recommendation system
using Large Language Models and Hybrid Retrieval-Augmented Generation.
```

The system combines:

* semantic understanding,
* structured tourism metadata,
* hybrid retrieval,
* personalization,
* memory,
* and contextual reasoning

to generate intelligent tourism recommendations and itinerary planning.
