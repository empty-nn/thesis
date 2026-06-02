# Modern RAG — What Is It Really About?

## Traditional Understanding of RAG

Originally, Retrieval-Augmented Generation (RAG) was:

```text id="old_rag"
query
→ retrieve documents
→ send to LLM
→ generate answer
```

The goal was:

* reduce hallucinations
* use external knowledge
* avoid retraining LLMs
* support domain-specific information

The original RAG architecture combined:

* dense retrieval
* external memory
* text generation

Modern RAG systems still follow this core idea.

---

# Why Traditional RAG Is No Longer Enough

Researchers realized that:

```text id="key_realization"
retrieval quality determines answer quality
```

If retrieval is poor:

* answers become incorrect
* hallucinations increase
* personalization fails
* recommendations become weak

Therefore, modern RAG evolved far beyond:

* simple vector search
* simple embedding retrieval

---

# Modern RAG Architecture

Modern RAG is now composed of multiple layers.

---

# 1. Ingestion Layer

This is the knowledge preparation stage.

## Pipeline

```text id="ingestion_pipeline"
PDF / HTML
→ Markdown
→ Cleaning
→ Semantic Chunking
→ Metadata Extraction
→ Embeddings
→ Vector Database
```

## Important Concepts

### Semantic Chunking

Instead of splitting text randomly:

* split by meaning
* split by sections/topics
* preserve context

### Metadata Extraction

AI extracts:

* city
* place type
* activities
* travel styles
* tourism tags

Example:

```json id="metadata_example"
{
  "city": "Hanoi",
  "place_type": "attraction",
  "ai_tags": ["historical", "photography"]
}
```

### Embeddings

Chunks become vectors for semantic retrieval.

---

# 2. Retrieval Layer

Traditional RAG used:

```text id="traditional_retrieval"
vector similarity search only
```

Modern RAG uses:

```text id="modern_retrieval"
- dense retrieval
- BM25 keyword retrieval
- metadata filtering
- hybrid retrieval
- reranking
- query rewriting
```

---

# Hybrid Retrieval

Hybrid retrieval combines:

```text id="hybrid_formula"
dense retrieval
+
sparse retrieval (BM25)
```

Advantages:

* semantic understanding
* keyword precision
* better retrieval recall
* more robust search

Example:

```text id="hybrid_example"
family-friendly cultural attractions in Hanoi
```

Semantic retrieval:

* understands meaning

BM25:

* catches exact keywords

---

# Reranking

Modern RAG systems often retrieve:

* top 20–50 chunks

Then rerank them:

* using CrossEncoder
* BGE reranker
* Jina reranker

Pipeline:

```text id="reranking_pipeline"
retrieve
→ rerank
→ final context
→ generation
```

Advantages:

* improves relevance
* reduces noisy chunks
* improves final answers

---

# 3. Reasoning Layer

Modern RAG is not just:

* retrieve
* dump chunks into prompt

Now systems:

* summarize
* compare
* filter
* reason
* validate
* compress context

This creates:

* better explanations
* more grounded answers
* personalized reasoning

---

# 4. Agentic RAG

Agentic RAG is the newest evolution.

Instead of:

```text id="static_rag"
retrieve once
→ answer once
```

Agentic RAG uses:

```text id="agentic_flow"
retrieve
→ evaluate
→ retrieve again
→ reason
→ plan
→ answer
```

The LLM actively controls:

* retrieval strategy
* tool usage
* reasoning process
* query refinement

---

# Example of Agentic RAG in Tourism

User query:

```text id="tourism_query"
Suggest a 3-day cultural and food trip in Hanoi under budget.
```

Possible workflow:

```text id="agentic_tourism_flow"
Query Understanding Agent
→ Attraction Retrieval Agent
→ Restaurant Retrieval Agent
→ Budget Checking Agent
→ Itinerary Planning Agent
→ Final Recommendation Generation
```

Advantages:

* adaptive retrieval
* multi-step reasoning
* personalized planning
* better recommendations

---

# 5. Evaluation Layer

Modern RAG research heavily focuses on evaluation.

Good-looking answers are not always:

* correct
* grounded
* relevant

Therefore modern evaluation includes:

---

## Retrieval Evaluation

### Precision@K

Measures how many retrieved chunks are relevant.

### nDCG

Measures ranking quality.

### MRR

Measures how early the first correct chunk appears.

---

## Generation Evaluation

### Faithfulness

Whether answers are supported by retrieved context.

### Answer Relevance

Whether generated answers match user intent.

### Correctness

Whether information is factually correct.

---

## Recommendation Evaluation

### Constraint Satisfaction

Whether recommendations satisfy:

* budget
* travel style
* preferences

### Diversity Score

Whether recommendations are diverse.

### Coverage Score

Whether recommendations cover different aspects of tourism.

---

# Technologies That Enhance Modern RAG

---

# LangChain

Best for:

* retrieval orchestration
* hybrid retrieval
* retriever pipelines
* memory
* reranking integration

Recommended usage:

* retrieval layer only

---

# LangGraph

Best for:

* agent workflows
* multi-step reasoning
* stateful pipelines
* agentic RAG

Recommended for:

* lightweight agentic workflows

Example:

```text id="langgraph_pipeline"
query
→ retrieval
→ reranking
→ recommendation planning
→ answer generation
```

---

# LlamaIndex

Best for:

* indexing
* query engines
* document retrieval

Optional for this thesis.

---

# GraphRAG

Uses graph relationships:

```text id="graph_example"
Hoan Kiem Lake
↔ Old Quarter
↔ Street Food
↔ Walking Tours
```

Advantages:

* connected recommendations
* itinerary planning

Disadvantages:

* more complex
* higher engineering cost

Recommended as:

* future work
* lightweight exploration only

---

# LightRAG

Focuses on:

* lightweight retrieval
* graph-enhanced retrieval
* efficient context management

Interesting but more experimental.

---

# Recommended Thesis Architecture

```text id="recommended_architecture"
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
→ Hybrid Retrieval
→ Reranking

Reasoning:
→ Lightweight Agentic Workflow
→ Recommendation Reasoning
→ Personalized Recommendation
```

---

# Recommended Thesis Positioning

This thesis can be positioned as:

```text id="thesis_positioning"
AI-enriched personalized tourism recommendation system
using Retrieval-Augmented Generation (RAG),
hybrid retrieval,
and lightweight agentic reasoning.
```

---

# Important Design Philosophy

The thesis should focus on:

```text id="focus"
retrieval quality
+
reasoning quality
+
grounded recommendations
+
personalization
```

rather than:

* overly complex agent swarms
* massive graph infrastructures
* autonomous multi-agent ecosystems

A focused and explainable system is stronger academically and more feasible within the project timeline.
