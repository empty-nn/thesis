from db.models import RagChunkORM
from db.session import SessionLocal
from sqlalchemy import select


def insert_chunk(chunk_data):

    db = SessionLocal()

    try:

        row = RagChunkORM(
            document_title=chunk_data["document_title"],
            section_heading=chunk_data["section_heading"],
            subsection_heading=chunk_data["subsection_heading"],

            chunk_text=chunk_data["chunk_text"],

            place_name=chunk_data["place_name"],

            city=chunk_data["city"],
            province=chunk_data["province"],

            place_type=chunk_data["place_type"],
            chunk_topic=chunk_data["chunk_topic"],

            tags=chunk_data["tags"],

            source_file=chunk_data["source_file"],

            embedding=chunk_data["embedding"],
        )

        db.add(row)
        db.commit()

    finally:
        db.close()

def vector_search(query_embedding, top_k=5):

    db = SessionLocal()

    try:

        stmt = (
            select(
                RagChunkORM,
                RagChunkORM.embedding.cosine_distance(
                    query_embedding
                ).label("distance")
            )
            .order_by("distance")
            .limit(top_k)
        )

        rows = db.execute(stmt).all()

        return rows

    finally:
        db.close()