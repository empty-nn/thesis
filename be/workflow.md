# System Workflow: From User Query to Final Recommendation

The proposed tourism recommendation system follows a multi-stage intelligent workflow that combines:

* semantic understanding,
* retrieval,
* personalization,
* contextual reasoning,
* and real-time adaptation.

Instead of functioning as a simple chatbot, the system operates as a semantic tourism assistant capable of understanding user intent and generating context-aware travel recommendations.

---

# Full Workflow Overview

```text
User Query
→ Semantic Query Parsing
→ User Memory Retrieval
→ Metadata-aware Filtering
→ Hybrid Retrieval
    ├── Vector Search
    └── BM25 Keyword Search
→ Score Fusion
→ CrossEncoder Reranking
→ Retrieval Confidence Evaluation
→ Context-aware Reasoning
    ├── Weather API
    ├── Maps API
    ├── Event Information
    └── User Preferences
→ Final Recommendation / Itinerary Generation
→ Response Explanation
```

---

# Step 1 — User Query

The workflow begins when the user submits a natural language tourism query.

Example queries:

* “Family-friendly activities in Da Nang”
* “3-day cultural itinerary in Hanoi”
* “Luxury beach vacation for couples”
* “Indoor attractions in rainy weather”

Unlike traditional keyword search systems, the query is treated as semantic input rather than plain text.

---

# Step 2 — Semantic Query Parsing

The system analyzes the query to extract structured semantic information such as:

* city,
* travel style,
* activities,
* suitable traveler groups,
* place type,
* budget preference,
* and itinerary intent.

Example:

User Query:

```text
family-friendly cultural attractions in Da Nang
```

Parsed Representation:

```json
{
  "city": "Da Nang",
  "travel_styles": ["family", "culture"],
  "place_types": ["attraction"]
}
```

This stage transforms unstructured language into structured metadata that can improve retrieval quality.

---

# Step 3 — User Memory Retrieval

The system retrieves stored user preferences from the memory module.

Examples of stored memory:

* preferred travel styles,
* favorite cities,
* preferred activities,
* budget preference,
* disliked categories,
* and previous interactions.

Example memory:

```json
{
  "preferred_travel_styles": ["culture", "food"],
  "preferred_cities": ["Hoi An", "Hue"],
  "budget": "mid_range"
}
```

This enables long-term personalization.

---

# Step 4 — Metadata-aware Filtering

Before retrieval begins, the system uses semantic query metadata and user memory to filter candidate tourism chunks.

Example filters:

* city = Da Nang
* travel_style = family
* place_type = attraction

This reduces irrelevant retrieval results and improves geographic relevance.

---

# Step 5 — Hybrid Retrieval

The system combines two retrieval methods:

## Dense Vector Retrieval

Uses semantic embeddings to retrieve conceptually relevant chunks.

Strengths:

* semantic understanding,
* paraphrase handling,
* contextual similarity.

---

## Sparse BM25 Retrieval

Uses keyword-based retrieval.

Strengths:

* exact keyword matching,
* location matching,
* named entity matching.

---

# Why Hybrid Retrieval Is Used

Each retrieval method has strengths and weaknesses.

Vector retrieval:

* strong semantic understanding,
* but may retrieve geographically irrelevant chunks.

BM25 retrieval:

* strong exact matching,
* but weak semantic understanding.

Combining both improves:

* recall,
* precision,
* robustness,
* and retrieval quality.

---

# Step 6 — Score Fusion

Results from vector retrieval and BM25 retrieval are combined using weighted fusion scoring.

The system calculates final retrieval importance using:

* vector similarity,
* BM25 ranking,
* metadata matches,
* and preference alignment.

This creates a more balanced retrieval ranking.

---

# Step 7 — CrossEncoder Reranking

Retrieved chunks are reranked using a CrossEncoder model.

Unlike embedding similarity, reranking directly evaluates:

* query-chunk relevance,
* semantic interaction,
* and contextual consistency.

This stage significantly improves final retrieval quality and reduces noisy chunks.

---

# Step 8 — Retrieval Confidence Evaluation

The system evaluates whether retrieved information is sufficiently reliable.

This helps detect:

* irrelevant retrieval,
* weak context,
* and out-of-domain questions.

If retrieval confidence is too low, the system may:

* trigger fallback behavior,
* perform external search,
* or avoid hallucinated answers.

---

# Step 9 — Context-aware Reasoning

The system combines retrieved tourism knowledge with real-time external information.

Possible external data sources:

* weather APIs,
* event information,
* transportation status,
* and seasonal context.

Example:

* rainy weather may shift recommendations from beaches to museums or cafes.

This allows adaptive itinerary planning.

---

# Step 10 — Final Recommendation / Itinerary Generation

The LLM generates:

* tourism recommendations,
* travel plans,
* attraction suggestions,
* or personalized itineraries

using:

* retrieved tourism knowledge,
* user memory,
* semantic constraints,
* and contextual information.

The final response becomes:

* personalized,
* context-aware,
* geographically relevant,
* and dynamically adaptive.

---


# Workflow Summary

The proposed workflow transforms tourism recommendation from:

* simple vector retrieval

into:

* semantic understanding,
* personalized retrieval,
* context-aware planning,
* and intelligent itinerary generation.

The architecture integrates:

* semantic query parsing,
* hybrid retrieval,
* metadata-aware filtering,
* reranking,
* memory,
* and contextual reasoning

to create a modern intelligent tourism recommendation system.
