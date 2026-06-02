# Evaluation Framework for the Personalized Tourism RAG System

# 1. Purpose of Evaluation

Evaluation is one of the most important components of a Retrieval-Augmented Generation (RAG) system.

The purpose of evaluation is to measure:

* retrieval quality,
* recommendation relevance,
* answer correctness,
* personalization effectiveness,
* and overall system usefulness.

The proposed tourism recommendation system combines:

* semantic retrieval,
* metadata-aware filtering,
* hybrid retrieval,
* reranking,
* memory,
* and contextual reasoning.

Therefore, evaluation must assess not only retrieval accuracy, but also:

* personalization,
* itinerary quality,
* context awareness,
* and recommendation usefulness.

---

# 2. Overall Evaluation Workflow

```text id="workflow_eval"
User Query
→ Retrieval Evaluation
→ Reranking Evaluation
→ Recommendation Evaluation
→ Generation Evaluation
→ Personalization Evaluation
→ Context-aware Evaluation
→ Human / LLM-based Judging
→ Final Performance Analysis
```

---

# 3. Retrieval Evaluation

# Purpose

Retrieval evaluation measures:

* whether the system retrieves relevant tourism chunks,
* and whether the most useful chunks appear near the top results.

This is critical because:

* poor retrieval leads to poor recommendations,
* even if the LLM is strong.

---

# Metrics Used

## Precision@K

Measures:

* how many retrieved chunks are relevant.

Example:

```text id="precision_example"
Top 5 retrieved chunks
→ 4 relevant
→ Precision@5 = 0.8
```

---

## Recall@K

Measures:

* how many relevant chunks were successfully retrieved.

Useful for:

* retrieval coverage,
* recommendation completeness.

---

## MRR (Mean Reciprocal Rank)

Measures:

* how early the first relevant chunk appears.

Higher MRR means:

* useful chunks appear earlier.

---

## nDCG@K (Normalized Discounted Cumulative Gain)

Measures:

* ranking quality,
* and relevance ordering.

Important because:

* highly relevant chunks should appear before weakly relevant chunks.

---

# Why Retrieval Evaluation Matters

Retrieval evaluation measures:

* semantic search quality,
* metadata filtering effectiveness,
* reranking improvements,
* and hybrid retrieval performance.

---

# 4. Hybrid Retrieval Evaluation

# Purpose

The system combines:

* vector retrieval,
* BM25 retrieval,
* and metadata-aware retrieval.

Evaluation compares:

* vector-only retrieval,
* BM25-only retrieval,
* and hybrid retrieval.

---

# Comparison Goals

Determine whether hybrid retrieval improves:

* retrieval precision,
* semantic relevance,
* geographic relevance,
* and personalization quality.

---

# Example Comparison

| Retrieval Method | Strength                              |
| ---------------- | ------------------------------------- |
| Vector-only      | semantic similarity                   |
| BM25-only        | exact keyword matching                |
| Hybrid retrieval | balanced semantic + keyword retrieval |

---

# Expected Result

Hybrid retrieval is expected to:

* outperform individual retrieval methods,
* reduce irrelevant chunks,
* and improve recommendation quality.

---

# 5. Reranking Evaluation

# Purpose

Evaluate whether CrossEncoder reranking improves:

* final ranking quality,
* retrieval relevance,
* and recommendation usefulness.

---

# Evaluation Strategy

Compare:

* retrieval before reranking,
* retrieval after reranking.

---

# Metrics

* nDCG@K
* MRR
* Precision@K

---

# Expected Improvements

Reranking should:

* push highly relevant chunks upward,
* reduce noisy chunks,
* improve itinerary coherence,
* and improve semantic matching.

---

# 6. Semantic Query Parsing Evaluation

# Purpose

Evaluate whether semantic query parsing correctly extracts:

* cities,
* travel styles,
* activities,
* place types,
* and user intent.

---

# Example

User query:

```text id="query_eval_example"
family-friendly cultural attractions in Da Nang
```

Expected parsed output:

```json id="parsed_eval_example"
{
  "city": "Da Nang",
  "travel_styles": ["family", "culture"],
  "place_types": ["attraction"]
}
```

---

# Evaluation Criteria

Measure:

* extraction correctness,
* ontology consistency,
* and semantic parsing accuracy.

---

# Why It Matters

Semantic query parsing directly affects:

* metadata filtering,
* personalized retrieval,
* and recommendation quality.

---

# 7. Metadata-aware Retrieval Evaluation

# Purpose

Evaluate whether metadata filtering improves retrieval relevance.

---

# Example

Query:

```text id="metadata_query"
family activities in Da Nang
```

Expected behavior:

* prioritize family-related chunks,
* prioritize Da Nang chunks,
* reduce irrelevant city retrieval.

---

# Evaluation Focus

Measure:

* geographic relevance,
* metadata consistency,
* and filtering effectiveness.

---

# 8. Recommendation Evaluation

# Purpose

Evaluate recommendation usefulness and tourism relevance.

The goal is not only retrieving information, but generating:

* meaningful,
* diverse,
* practical,
* and personalized recommendations.

---

# Metrics Used

## Recommendation Precision

Measures:

* how many recommendations are relevant to user preferences.

---

## Diversity Score

Measures:

* variety of recommendations.

Example:

* museum
* cafe
* market
* cultural activity

instead of:

* repeating similar attractions.

---

## Coverage Score

Measures:

* how much of the tourism domain is represented.

Example:

* attractions,
* food,
* activities,
* transportation,
* accommodation.

---

## Constraint Satisfaction Rate

Measures whether generated recommendations satisfy:

* budget constraints,
* family preferences,
* travel styles,
* and itinerary constraints.

---

# Why Recommendation Evaluation Matters

This evaluates:

* personalization quality,
* itinerary usefulness,
* and practical recommendation quality.

---

# 9. Generation Evaluation

# Purpose

Evaluate the final generated answer from the LLM.

---

# Metrics Used

## Faithfulness

Measures:

* whether generated answers remain grounded in retrieved chunks.

This is critical for reducing hallucination.

---

## Answer Relevance

Measures:

* how well the final response answers the user query.

---

## Correctness

Measures:

* factual accuracy of recommendations and itinerary content.

---

## Citation Support

Measures:

* whether generated recommendations are supported by retrieved evidence.

---

# Why Generation Evaluation Matters

Even with good retrieval:

* the LLM may hallucinate,
* ignore retrieval context,
* or generate weak itineraries.

Generation evaluation ensures:

* grounded reasoning,
* reliable recommendations,
* and trustworthy responses.

---

# 10. Personalization Evaluation

# Purpose

Evaluate whether memory and user preferences improve recommendation quality.

---

# Example

User memory:

```json id="memory_example"
{
  "travel_styles": ["culture", "food"]
}
```

Expected behavior:

* prioritize cultural attractions,
* local food,
* and authentic experiences.

---

# Evaluation Focus

Measure:

* personalization quality,
* recommendation alignment,
* and preference satisfaction.

---

# Why It Matters

Without personalization:

* recommendations become generic.

Personalization is one of the core contributions of the system.

---

# 11. Context-aware Evaluation

# Purpose

Evaluate whether external contextual information improves itinerary quality.

---

# Example

Weather-aware itinerary generation.

Rainy weather should:

* reduce beach activities,
* increase indoor recommendations.

---

# Evaluation Focus

Measure:

* context adaptation quality,
* practical itinerary realism,
* and environmental awareness.

---

# Why It Matters

Tourism recommendation is highly context-dependent.

Static recommendations are often unrealistic.

---

# 12. Explainability Evaluation

# Purpose

Evaluate whether the system can explain:

* why recommendations were selected.

---

# Example

```text id="explain_example"
Recommended because:
- suitable for families,
- weather-friendly,
- and matches cultural travel style.
```

---

# Evaluation Focus

Measure:

* explanation clarity,
* recommendation transparency,
* and user trust.

---

# 13. Human Evaluation

# Purpose

Human users evaluate:

* recommendation quality,
* itinerary usefulness,
* and personalization satisfaction.

---

# Possible Human Evaluation Criteria

| Criteria        | Description               |
| --------------- | ------------------------- |
| Relevance       | recommendation usefulness |
| Personalization | preference matching       |
| Practicality    | realistic itinerary       |
| Diversity       | recommendation variety    |
| Satisfaction    | overall user satisfaction |

---

# Why Human Evaluation Matters

Many tourism recommendation qualities are difficult to measure using automatic metrics alone.

Human evaluation captures:

* practical usefulness,
* tourism realism,
* and user experience.

---

# 14. LLM-as-a-Judge Evaluation

# Purpose

Large Language Models can evaluate:

* relevance,
* faithfulness,
* and recommendation quality.

---

# Example Tasks

The judge model evaluates:

* whether recommendations match the query,
* whether the itinerary is coherent,
* and whether generated answers are supported by retrieval context.

---

# Why It Matters

LLM-as-a-judge enables:

* scalable evaluation,
* semantic relevance scoring,
* and automated assessment.

---

# 15. Baseline Comparison

# Purpose

Compare the proposed system against simpler baseline systems.

---

# Example Baselines

## Baseline 1

Vector-only retrieval.

---

## Baseline 2

Vector retrieval + no reranking.

---

## Baseline 3

No semantic query parsing.

---

## Baseline 4

No memory personalization.

---

# Expected Contribution

The proposed system should demonstrate improvements in:

* retrieval relevance,
* personalization,
* recommendation quality,
* and itinerary realism.

---

# 16. Overall Evaluation Goal

The evaluation framework measures the effectiveness of:

* semantic query parsing,
* metadata-aware retrieval,
* hybrid retrieval,
* reranking,
* personalization,
* memory,
* and contextual reasoning.

The goal is to demonstrate that the proposed architecture improves:

* retrieval quality,
* recommendation relevance,
* personalization,
* and tourism planning effectiveness

compared to traditional vector-only RAG systems.

---

# 17. Final Evaluation Vision

The final system aims to achieve:

```text id="final_eval_vision"
A reliable, personalized, context-aware tourism recommendation system
with strong retrieval quality, grounded reasoning,
and adaptive itinerary generation.
```

The evaluation framework ensures that the system is assessed not only as:

* a chatbot,

but as:

* an intelligent tourism planning and recommendation system.
