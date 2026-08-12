from __future__ import annotations

import json
import re

from langchain_core.documents import Document

from data_building.extract_metadata.extractor import (
    DEEPSEEK_RETRIEVAL_MODEL,
    get_deepseek_client,
)
from schemas.pipeline import (
    AgenticRetrievalPlan,
    EvidenceCoverage,
    RequirementCoverage,
    RetrievalTask,
)
from services.llm_telemetry import create_chat_completion


MAX_RETRIEVAL_TASKS = 6
MAX_REQUIREMENTS = 6
MAX_RECOVERY_QUERIES = 3


def _is_response_only_requirement(
    requirement: str,
    query: str,
    planner_context: dict,
    comparison_cities: list[str],
) -> bool:
    text = requirement.casefold()
    query_text = query.casefold()
    if re.search(r"\b(weather|climate|permits?|permission)\b", text) and not re.search(
        r"\b(weather|climate|permits?|permission|practical considerations?)\b",
        query_text,
    ):
        return True
    if re.search(
        r"\b(scenic views?|photograph(?:y|ic)? opportunities?)\b.*\b"
        r"(?:train|bus|route|transfer)\b|\b(?:train|bus|route|transfer)\b.*\b"
        r"(scenic views?|photograph(?:y|ic)? opportunities?)\b",
        text,
    ) and not re.search(
        r"\b(scenic|views? (?:from|along)|photos? (?:from|along)|"
        r"photograph(?:y|ic)? (?:from|along|on the route))\b",
        query_text,
    ):
        return True
    if comparison_cities and re.search(
        r"\b(compare|comparison|contrast|versus|vs\.?|which is better)\b", text
    ):
        return True
    if planner_context.get("intent") == "itinerary" and re.search(
        r"\b(itinerary|day[- ]by[- ]day|schedule|plan for \d+ days?)\b", text
    ):
        return True
    if "nightlife" in text and re.search(r"\b(avoid|without|not interested)\b", text):
        return True
    if re.search(r"\b(packaged?|organized|large group) tours?\b", text):
        return True
    if re.search(r"\b(flexibility|independent travel)\b", text):
        return True
    if "specified interests" in text or "specified constraints" in text:
        return True
    if re.search(
        r"\b(priority recommendations?|recommendations? for (?:a|the) \d+[- ]day|"
        r"prioriti[sz]e for (?:a|the) trip)\b",
        text,
    ):
        return True
    if re.search(r"\bsolo (travel|traveler|traveller)\b", text) and not re.search(
        r"\b(safety|safe|accessibility|access)\b", query_text
    ):
        return True
    if re.search(r"\b(mid[- ]range|budget level|budget traveler)\b", text) and not re.search(
        r"\b(cost|price|how much|afford|daily budget)\b", query_text
    ):
        return True
    return False


def _fallback_plan(
    query: str,
    comparison_cities: list[str] | None = None,
    planner_context: dict | None = None,
) -> AgenticRetrievalPlan:
    comparison_cities = (comparison_cities or [])[:MAX_RETRIEVAL_TASKS]
    planner_context = planner_context or {}
    context_cities = planner_context.get("cities") or comparison_cities
    if planner_context.get("intent") == "itinerary" and context_cities:
        requirements = [
            f"Supported places, activities, food, and practical travel facts in {city}"
            for city in context_cities
        ]
    elif comparison_cities:
        requirements = [
            f"Factual evidence about {city} for the requested comparison aspects"
            for city in comparison_cities
        ]
    else:
        requirements = [query]
    return AgenticRetrievalPlan(
        complexity="simple",
        requirements=requirements,
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
    planner_context: dict | None = None,
    model: str = DEEPSEEK_RETRIEVAL_MODEL,
) -> AgenticRetrievalPlan:
    """Create one to five focused retrieval tasks for a standalone query."""
    comparison_cities = comparison_cities or []
    planner_context = planner_context or {}
    system_prompt = f"""
You plan retrieval for a Vietnam travel RAG system.

Analyze the standalone user query and identify its independent information
requirements. Create one focused search query per requirement only when
decomposition is useful. A simple factual request must remain one task.

Rules:
- Return between 1 and 6 retrieval tasks and no more than 6 requirements.
- Preserve destinations, dates, duration, budget and hard constraints.
- Do not invent preferences or facts.
- Queries must search for evidence, not ask the model to write an answer.
- Requirements must be atomic, factual questions that retrieved documents can
  directly support. Do not create requirements merely to restate the whole
  request or the final synthesis/comparison.
- Use the minimum factual requirements needed to answer the explicit request.
  Do not expand a broad request into every potentially useful consideration.
- Do not add weather, permits, safety, accommodation, schedules, prices,
  comfort, amenities, scenic-route, or photography requirements unless the
  standalone query explicitly asks for that aspect.
- Avoid conclusion-bearing requirement words such as best, recommended,
  suitable, photogenic, or better. Retrieve observable facts; the answer stage
  makes recommendations and comparisons from those facts.
- For a transport comparison, normally use at most four combined factual
  requirements: availability/schedule, duration, cost, and practical
  convenience. A requirement may cover both named transport modes; do not
  duplicate every aspect once per mode.
- Treat solo travel, budget level, preferred pace, avoidance of nightlife or
  packaged tours, and desired flexibility as response constraints, not evidence
  requirements, unless the user explicitly asks for factual cost, safety,
  accessibility, nightlife, or tour-availability information.
- For an itinerary, retrieve supported places, activities, food, transport, and
  practical facts. Do not require the corpus to contain a prewritten day-by-day
  itinerary; the answer stage creates the schedule.
- For a destination comparison, split factual needs by destination. Do not
  require a document that directly compares both destinations.
- For accommodation_search, when the user asks where to stay but does not ask
  for named hotels or properties, retrieve neighborhood/base-area evidence:
  proximity to requested places, walkability or transport access, noise, and
  budget trade-offs. Do not require the corpus to name specific hotels. Search
  for specific properties only when the user explicitly requests them.
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
    user_payload = {
        "standalone_query": query,
        "parsed_context": planner_context,
    }

    try:
        client = get_deepseek_client()
        response = create_chat_completion(
            "retrieval_planner", client,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            return _fallback_plan(query, comparison_cities, planner_context)

        plan = AgenticRetrievalPlan.model_validate(json.loads(content))
        if (
            planner_context.get("intent") == "accommodation_search"
            and not re.search(
                r"\b(?:(?:specific|named)\s+(?:hotel|hostel|resort|property)|"
                r"(?:which|what)\s+(?:hotel|hostel|resort)|"
                r"(?:hotel|hostel|resort|property) names?)\b",
                query,
                re.IGNORECASE,
            )
        ):
            def area_level_text(value: str) -> str:
                value = re.sub(
                    r"\bwhich accommodations? (?:are )?located near\b",
                    "which neighborhoods or base areas provide access to",
                    value,
                    flags=re.IGNORECASE,
                )
                value = re.sub(
                    r"\bbudget[- ]friendly accommodation options\b",
                    "budget-friendly neighborhoods or base areas to stay",
                    value,
                    flags=re.IGNORECASE,
                )
                value = re.sub(
                    r"\baccommodation options\b",
                    "neighborhoods or base areas to stay",
                    value,
                    flags=re.IGNORECASE,
                )
                value = re.sub(
                    r"\baffordable accommodations?\b",
                    "budget-friendly neighborhoods or base areas",
                    value,
                    flags=re.IGNORECASE,
                )
                value = re.sub(
                    r"\b(?:budget )?hotels? near\b",
                    "budget-friendly areas to stay near",
                    value,
                    flags=re.IGNORECASE,
                )
                return value

            plan.requirements = [
                area_level_text(requirement)
                for requirement in plan.requirements
            ]
            for task in plan.retrieval_tasks:
                task.query = area_level_text(task.query)
        tasks = [
            task
            for task in plan.retrieval_tasks
            if task.query.strip()
        ][:MAX_RETRIEVAL_TASKS]
        if not tasks:
            return _fallback_plan(query, comparison_cities, planner_context)
        plan.retrieval_tasks = tasks
        original_requirements = list(plan.requirements)
        kept_requirements = [
            (index, item.strip())
            for index, item in enumerate(original_requirements)
            if item.strip() and not _is_response_only_requirement(
                item, query, planner_context, comparison_cities
            )
        ][:MAX_REQUIREMENTS]
        requirement_index_map = {
            old_index: new_index
            for new_index, (old_index, _) in enumerate(kept_requirements)
        }
        plan.requirements = [item for _, item in kept_requirements]
        for task in plan.retrieval_tasks:
            task.requirement_indexes = list(dict.fromkeys(
                requirement_index_map[index]
                for index in task.requirement_indexes
                if index in requirement_index_map
            ))
        if not plan.requirements:
            plan.requirements = [
                f"Factual travel evidence about {city} for the requested aspects"
                for city in comparison_cities
            ] or ["Factual evidence needed to answer the travel request"]
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
        return _fallback_plan(query, comparison_cities, planner_context)


def check_evidence_coverage(
    query: str,
    requirements: list[str],
    documents: list[Document],
    telemetry_stage: str = "coverage_checker",
    model: str = DEEPSEEK_RETRIEVAL_MODEL,
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
        f"[chunk_id={doc.metadata.get('chunk_id')}] {doc.page_content}"
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
Recovery queries must be concrete search phrases, not instructions such as
"assess suitability" or references to "specified interests/constraints". For
partially covered requirements, search only the unsupported sub-aspect named in
the reason instead of repeating the complete requirement.

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
            if assessment.status != "covered" and any(
                phrase in (assessment.additional_query or "").casefold()
                for phrase in (
                    "assess suitability",
                    "specified interests",
                    "specified constraints",
                )
            ):
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
