from __future__ import annotations

import json

from langchain_core.documents import Document

from data_building.extract_metadata.extractor import (
    DEEPSEEK_METADATA_MODEL,
    get_deepseek_client,
)
from schemas.pipeline import (
    AgenticRetrievalPlan,
    EvidenceCoverage,
    RequirementCoverage,
    RetrievalTask,
)
from services.llm_telemetry import create_chat_completion


MAX_RETRIEVAL_TASKS = 5
MAX_RECOVERY_QUERIES = 3


def _fallback_plan(
    query: str,
    comparison_cities: list[str] | None = None,
) -> AgenticRetrievalPlan:
    comparison_cities = (comparison_cities or [])[:MAX_RETRIEVAL_TASKS]
    return AgenticRetrievalPlan(
        complexity="simple",
        requirements=[query],
        retrieval_tasks=(
            [
                RetrievalTask(
                    task_type="destination_comparison",
                    query=f"{city} {query}",
                    top_k=10,
                    cities=[city],
                    requirement_indexes=[0],
                )
                for city in comparison_cities
            ]
            if comparison_cities else [
            RetrievalTask(
                task_type="general",
                query=query,
                top_k=10,
            )
            ]
        ),
        used_fallback=True,
    )


def plan_retrieval(
    query: str,
    comparison_cities: list[str] | None = None,
    model: str = DEEPSEEK_METADATA_MODEL,
) -> AgenticRetrievalPlan:
    """Create one to five focused retrieval tasks for a standalone query."""
    comparison_cities = comparison_cities or []
    system_prompt = f"""
You plan retrieval for a Vietnam travel RAG system.

Analyze the standalone user query and identify its independent information
requirements. Create one focused search query per requirement only when
decomposition is useful. A simple factual request must remain one task.

Rules:
- Return between 1 and 5 retrieval tasks.
- Preserve destinations, dates, duration, budget and hard constraints.
- Do not invent preferences or facts.
- Queries must search for evidence, not ask the model to write an answer.
- Allowed complexity values: simple, medium, complex, very_complex.
- top_k must be between 5 and 20.
- cities scopes a task to one or more destinations. Use only these comparison
  cities: {json.dumps(comparison_cities, ensure_ascii=False)}.
- For a destination comparison, create at least one city-scoped task for every
  supplied comparison city.
- requirement_indexes contains zero-based indexes into requirements addressed
  by the task.

Return JSON only:
{{
  "complexity": "simple|medium|complex|very_complex",
  "requirements": ["atomic information requirement"],
  "retrieval_tasks": [
    {{"task_type": "general", "query": "focused query", "top_k": 10,
      "cities": [], "requirement_indexes": []}}
  ]
}}
""".strip()

    try:
        client = get_deepseek_client()
        response = create_chat_completion(
            "retrieval_planner", client,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            temperature=0,
            max_tokens=700,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            return _fallback_plan(query, comparison_cities)

        plan = AgenticRetrievalPlan.model_validate(json.loads(content))
        tasks = [
            task
            for task in plan.retrieval_tasks
            if task.query.strip()
        ][:MAX_RETRIEVAL_TASKS]
        if not tasks:
            return _fallback_plan(query, comparison_cities)
        plan.retrieval_tasks = tasks
        plan.requirements = [
            item.strip()
            for item in plan.requirements
            if item.strip()
        ][:MAX_RETRIEVAL_TASKS]
        if comparison_cities:
            allowed_cities = set(comparison_cities)
            for task in plan.retrieval_tasks:
                task.cities = [
                    city for city in task.cities
                    if city in allowed_cities
                ]
            scoped_cities = {
                city
                for task in plan.retrieval_tasks
                for city in task.cities
            }
            missing_city_tasks = [
                RetrievalTask(
                    task_type="destination_comparison",
                    query=f"{city} {query}",
                    top_k=10,
                    cities=[city],
                    requirement_indexes=list(range(len(plan.requirements))),
                )
                for city in comparison_cities
                if city not in scoped_cities
            ]
            plan.retrieval_tasks = (
                missing_city_tasks + plan.retrieval_tasks
            )[:MAX_RETRIEVAL_TASKS]
        return plan
    except Exception as exc:
        print(f"[RETRIEVAL PLANNER WARNING] {exc}")
        return _fallback_plan(query, comparison_cities)


def check_evidence_coverage(
    query: str,
    requirements: list[str],
    documents: list[Document],
    telemetry_stage: str = "coverage_checker",
    model: str = DEEPSEEK_METADATA_MODEL,
) -> EvidenceCoverage:
    """Check coverage and propose bounded recovery queries for missing needs."""
    if not requirements:
        return EvidenceCoverage(sufficient=bool(documents))

    valid_chunk_ids = {
        str(doc.metadata.get("chunk_id"))
        for doc in documents
        if doc.metadata.get("chunk_id")
    }
    evidence = "\n\n".join(
        f"[chunk_id={doc.metadata.get('chunk_id')}] {doc.page_content[:1200]}"
        for doc in documents
    )
    system_prompt = f"""
You check evidence coverage for a Vietnam travel RAG system.

Assess every requirement independently. Copy each requirement exactly as
supplied. Judge coverage only; do not write the final answer and do not assume
facts absent from the evidence.

Status definitions:
- covered: enough direct evidence to answer the complete requirement.
- partially_covered: evidence directly supports only part of the requirement.
- not_covered: no directly useful evidence.

For covered or partially_covered, cite only chunk_id values shown in the
evidence. A covered assessment without a valid supporting chunk ID will be
downgraded by the application. For every non-covered requirement, provide one
focused additional_query that includes the destination and missing aspect.

If something is missing, create a focused retrieval query for it. Return no
more than {MAX_RECOVERY_QUERIES} additional queries.

Return JSON only:
{{
  "requirement_assessments": [
    {{
      "requirement": "exact requirement text",
      "status": "covered | partially_covered | not_covered",
      "supporting_chunk_ids": [],
      "reason": "short evidence-based reason",
      "additional_query": null
    }}
  ]
}}
""".strip()
    user_prompt = f"""
Original query:
{query}

Requirements:
{json.dumps(requirements, ensure_ascii=False)}

Evidence:
{evidence or "No evidence was retrieved."}
""".strip()

    try:
        client = get_deepseek_client()
        response = create_chat_completion(
            telemetry_stage, client,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("empty coverage result")
        payload = json.loads(content)
        raw_assessments = payload.get("requirement_assessments") or []
        by_requirement = {
            str(item.get("requirement", "")).strip().casefold(): item
            for item in raw_assessments
            if isinstance(item, dict)
        }
        assessments: list[RequirementCoverage] = []
        for requirement in requirements:
            raw = by_requirement.get(requirement.strip().casefold())
            if raw is None:
                assessments.append(RequirementCoverage(
                    requirement=requirement,
                    status="not_covered",
                    reason="The checker omitted this requirement.",
                    additional_query=requirement,
                ))
                continue
            assessment = RequirementCoverage.model_validate({
                **raw,
                "requirement": requirement,
            })
            assessment.supporting_chunk_ids = list(dict.fromkeys(
                chunk_id
                for chunk_id in assessment.supporting_chunk_ids
                if chunk_id in valid_chunk_ids
            ))
            if (
                assessment.status in {"covered", "partially_covered"}
                and not assessment.supporting_chunk_ids
            ):
                assessment.status = "not_covered"
                assessment.reason = (
                    assessment.reason
                    + " No valid supporting chunk ID was supplied."
                ).strip()
            if assessment.status != "covered" and not (
                assessment.additional_query or ""
            ).strip():
                assessment.additional_query = requirement
            assessments.append(assessment)

        additional_queries = list(dict.fromkeys(
            item.additional_query.strip()
            for item in assessments
            if item.status != "covered"
            and item.additional_query
            and item.additional_query.strip()
        ))[:MAX_RECOVERY_QUERIES]
        return EvidenceCoverage(
            requirement_assessments=assessments,
            additional_queries=additional_queries,
        )
    except Exception as exc:
        print(f"[EVIDENCE CHECKER WARNING] {exc}")
        return EvidenceCoverage(
            requirement_assessments=[
                RequirementCoverage(
                    requirement=requirement,
                    status="not_covered",
                    reason="Coverage checker failed; requirement was not assumed covered.",
                    additional_query=requirement,
                )
                for requirement in requirements
            ],
            additional_queries=requirements[:MAX_RECOVERY_QUERIES],
            used_fallback=True,
        )


def merge_unique_documents(document_groups: list[list[Document]]) -> list[Document]:
    """Keep first/best-ranked occurrence while retaining task provenance."""
    unique: dict[str, Document] = {}
    for task_index, documents in enumerate(document_groups, start=1):
        for document in documents:
            chunk_id = str(document.metadata.get("chunk_id"))
            if chunk_id not in unique:
                document.metadata["retrieval_task_indexes"] = [task_index]
                unique[chunk_id] = document
            else:
                indexes = unique[chunk_id].metadata.setdefault(
                    "retrieval_task_indexes", []
                )
                if task_index not in indexes:
                    indexes.append(task_index)
    return list(unique.values())
