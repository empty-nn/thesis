from typing import List
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

def generate_embedding(text: str) -> List[float]:
    """
    Generate normalized embedding.
    all-MiniLM-L6-v2 returns 384 dimensions.
    """

    vector = embedding_model.encode(
        text,
        normalize_embeddings=True,
    )

    return vector.tolist()