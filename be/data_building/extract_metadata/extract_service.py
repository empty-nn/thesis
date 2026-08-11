from data_building.extract_metadata.extractor import safe_extract_ai_metadata_batch
from schemas.metadata_schema import TourismMetadata

from typing import Any, Dict, List


def batch_items(
    items: List[Dict[str, Any]],
    batch_size: int = 7,
    min_last_batch_size: int = 4,
) -> List[List[Dict[str, Any]]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")

    if min_last_batch_size <= 0:
        raise ValueError(
            "min_last_batch_size must be greater than 0"
        )

    batches = [
        items[index:index + batch_size]
        for index in range(0, len(items), batch_size)
    ]

    # Merge a very small final batch into the previous batch.
    if (
        len(batches) > 1
        and len(batches[-1]) < min_last_batch_size
    ):
        small_last_batch = batches.pop()
        batches[-1].extend(small_last_batch)

    return batches
        
def process_chunks_by_batch(chunks, batch_size=7):
    enriched_chunks = []

    previous_summary = None
    previous_heading = None
    previous_country = None
    previous_city = None

    batches = batch_items(
        items=chunks,
        batch_size=batch_size,
        min_last_batch_size=4,
    )

    for batch in batches:
        start_index = batch[0]["chunk_index"]
        end_index = batch[-1]["chunk_index"]

        print(f"[BATCH] Processing chunks {start_index} -> {end_index}")

        context = {
            "previous_summary": previous_summary,
            "previous_heading": previous_heading,
            "previous_country": previous_country,
            "previous_city": previous_city,
        }

        try:
            metadata_by_index = safe_extract_ai_metadata_batch(
                batch_chunks=batch,
                context=context,
                provider="deepseek",
            )
            
        except Exception as e:
            print(f"[FAILED BATCH {start_index}-{end_index}]")
            print(e)
            metadata_by_index = {}

        for chunk in batch:
            chunk_index = chunk["chunk_index"]

            metadata = metadata_by_index.get(chunk_index)

            enriched_chunk = {
                **chunk,

                "country": metadata.country,
                "city": metadata.city,
                "province": metadata.province,
                "place_name": metadata.place_name,
                "place_type": metadata.place_type,
                "ai_tags": metadata.ai_tags,
                "ai_activities": metadata.ai_activities,
                "ai_travel_styles": metadata.ai_travel_styles,
                "ai_suitable_for": metadata.ai_suitable_for,
                "ai_topic": metadata.chunk_topic,
                "ai_summary": metadata.summary,
                "metadata_confidence": metadata.confidence,
                "metadata_reasoning": metadata.reasoning,
            }

            enriched_chunks.append(enriched_chunk)

            previous_summary = metadata.summary
            previous_heading = chunk.get("section_heading")
            previous_country = metadata.country or previous_country
            previous_city = metadata.city or previous_city


    return enriched_chunks
