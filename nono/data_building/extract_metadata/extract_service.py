from data_building.extract_metadata.extractor import safe_extract_ai_metadata_batch
from schemas.metadata_schema import TourismMetadata

def batch_items(items, batch_size=10):
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]
        
def process_chunks_by_batch(chunks, batch_size=10):
    enriched_chunks = []

    previous_summary = None
    previous_heading = None
    previous_country = None
    previous_city = None

    for batch in batch_items(chunks, batch_size):
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
                provider="gemini",
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

            print(f"[OK] Chunk {chunk_index}")
    print(enriched_chunks)
    return enriched_chunks
