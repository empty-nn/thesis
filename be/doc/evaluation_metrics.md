# Evaluation Metrics for the Personalized Travel RAG System

## 1. Evaluation objective

The evaluation should measure whether the system:

1. Retrieves relevant travel evidence.
2. Ranks the strongest evidence near the top.
3. Generates answers that address the user query.
4. Grounds factual claims in retrieved evidence.
5. Produces correct and complete citations.
6. Applies user preferences only when relevant.
7. Preserves trip-specific conversation context.
8. Operates with acceptable latency.

The evaluation therefore covers four dimensions:

- Retrieval effectiveness
- Answer quality and grounding
- Personalization quality
- System efficiency

## 2. Recommended primary metrics

| Component | Metric | Purpose |
|---|---|---|
| Retrieval | Recall@10 | Determines whether relevant evidence is present in the top ten results |
| Ranking | nDCG@5 | Rewards highly relevant chunks appearing near the top |
| Ranking | MRR | Measures how early the first relevant result appears |
| Generation | Answer relevance | Measures whether the answer directly addresses the query |
| Grounding | Faithfulness | Measures whether factual claims are supported by evidence |
| Citations | Citation correctness | Measures whether cited evidence supports its associated claims |
| Personalization | Preference adherence | Measures whether relevant user preferences are applied correctly |
| Efficiency | End-to-end latency | Measures the practical response time of the complete pipeline |

The smallest recommended metric set is:

- Recall@10
- nDCG@5
- Answer relevance
- Faithfulness
- Citation correctness
- Preference adherence
- End-to-end latency

## 3. Retrieval metrics

### 3.1 Recall@K

Recall@K measures the proportion of known relevant chunks retrieved in the top K results.

```text
Recall@K = relevant chunks in top K / all relevant chunks
```

Recommended values:

- Recall@5
- Recall@10

Recall is important because the generation model cannot produce a grounded answer when the required evidence was not retrieved.

### 3.2 nDCG@K

Normalized Discounted Cumulative Gain evaluates ranking quality using graded relevance. It gives more value to highly relevant chunks appearing near the top.

Recommended value:

- nDCG@5

Suggested relevance labels:

| Label | Meaning |
|---:|---|
| 0 | Irrelevant |
| 1 | Partially relevant |
| 2 | Relevant |
| 3 | Highly relevant |

### 3.3 Mean Reciprocal Rank

MRR evaluates the rank of the first relevant chunk.

```text
Reciprocal rank = 1 / rank of first relevant result
MRR = mean reciprocal rank across all queries
```

MRR is particularly useful for direct factual questions where one strong result should appear near the top.

### 3.4 Precision@K

Precision@K can be reported as a secondary metric.

```text
Precision@K = relevant chunks in top K / K
```

It measures how much irrelevant context is passed to the generation model.

## 4. Answer-quality metrics

### 4.1 Answer relevance

Answer relevance measures whether the generated response directly and adequately addresses the user query.

Suggested rubric:

| Score | Description |
|---:|---|
| 0 | Does not answer the query |
| 1 | Partially relevant but misses major requirements |
| 2 | Mostly relevant with minor omissions |
| 3 | Directly and completely addresses the query |

### 4.2 Faithfulness

Faithfulness measures whether factual claims are supported by the retrieved evidence.

Suggested rubric:

| Score | Description |
|---:|---|
| 0 | Contains major unsupported or contradictory claims |
| 1 | Important claims are unsupported |
| 2 | Most claims are supported, with minor issues |
| 3 | All material factual claims are supported |

### 4.3 Completeness

Completeness measures whether the answer covers all important aspects of the query that can be answered from the evidence.

This can be used as a secondary generation metric.

BLEU and ROUGE should not be primary metrics because a correct travel answer may use wording that differs substantially from a reference answer.

## 5. Citation metrics

### 5.1 Citation precision

Citation precision measures the proportion of citations that genuinely support the claims to which they are attached.

```text
Citation precision = supporting citations / all citations
```

### 5.2 Citation recall

Citation recall measures the proportion of verifiable factual claims that include an appropriate supporting citation.

```text
Citation recall = cited factual claims / all factual claims requiring support
```

### 5.3 Citation correctness

Citation correctness can be reported as a combined judgment covering:

- Entailment between the evidence and claim
- Correct evidence identifier
- Appropriate citation placement
- Absence of unsupported evidence references

The system's `[E1]`, `[E2]`, and similar evidence identifiers make citation evaluation directly traceable.

## 6. Personalization metrics

### 6.1 Preference adherence

Preference adherence measures whether the answer correctly uses relevant long-term user memories.

Example test case:

```text
User memory:
- Prefers quiet cultural places
- Avoids crowded attractions

Query:
What should I do in Hoi An?
```

Suggested rubric:

| Score | Description |
|---:|---|
| 0 | Ignores or contradicts relevant preferences |
| 1 | Uses preferences weakly or generically |
| 2 | Correctly applies some relevant preferences |
| 3 | Clearly and appropriately personalizes the answer |

### 6.2 Inappropriate personalization

The evaluation should also check whether the system avoids applying a stored preference when it is irrelevant to the current query.

This can be measured as an error rate:

```text
Inappropriate personalization rate =
answers using irrelevant memories / answers where memories are irrelevant
```

### 6.3 Conversation-context consistency

Conversation-context consistency measures whether the answer respects trip-specific state such as:

- Destination
- Dates and duration
- Temporary budget
- Selected places
- Trip constraints

Suggested rubric:

| Score | Description |
|---:|---|
| 0 | Contradicts or loses important conversation state |
| 1 | Uses some state but misses important details |
| 2 | Correctly applies most relevant state |
| 3 | Fully and consistently applies relevant state |

## 7. Efficiency metrics

Record latency for:

- Query rewriting
- Query parsing
- Vector retrieval
- BM25 retrieval
- Hybrid fusion and boosts
- Cross-encoder reranking
- DeepSeek answer generation
- Total end-to-end execution

Report at least:

- Mean latency
- Median latency
- 95th-percentile latency

Generation and reranking latency should be reported separately because they may dominate total response time.

## 8. Ablation study

Evaluate the following configurations using the same dataset:

1. Vector retrieval only
2. BM25 retrieval only
3. Hybrid vector and BM25 retrieval
4. Hybrid retrieval with metadata and geographic boosts
5. Hybrid retrieval with cross-encoder reranking
6. Full RAG without user memory
7. Full RAG with user memory
8. Full RAG with user and conversation memory

Recommended comparison table:

| Configuration | Recall@10 | nDCG@5 | MRR | Relevance | Faithfulness | Citation correctness | Preference adherence | Latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Vector only | | | | | | | N/A | |
| BM25 only | | | | | | | N/A | |
| Hybrid | | | | | | | N/A | |
| Hybrid + boosts | | | | | | | N/A | |
| Hybrid + reranking | | | | | | | N/A | |
| Full RAG without memory | | | | | | | 0 | |
| Full RAG + user memory | | | | | | | | |
| Full RAG + user and conversation memory | | | | | | | | |

## 9. Evaluation dataset requirements

The dataset should contain:

- Query identifier
- User query
- Query type or intent
- Relevant chunk identifiers
- Graded relevance labels
- Expected answer facts
- Claims requiring citations
- Optional user-memory scenario
- Optional conversation-state scenario

Include multiple intents:

- Travel information
- Attraction search
- Food search
- Accommodation search
- Transportation
- Events
- Recommendations
- Multi-day itinerary planning
- Follow-up questions requiring conversation context

## 10. Recommended final reporting

The thesis should report:

### Retrieval effectiveness

- Recall@5 and Recall@10
- nDCG@5
- MRR

### Generation quality

- Answer relevance
- Faithfulness
- Citation precision and recall

### Personalization

- Preference adherence
- Inappropriate personalization rate
- Conversation-context consistency

### Efficiency

- Mean, median, and 95th-percentile stage latency
- Total end-to-end latency

The primary conclusion should be based on whether hybrid retrieval and reranking improve retrieval quality, and whether user and conversation memory improve personalization without reducing faithfulness or introducing irrelevant personalization.
