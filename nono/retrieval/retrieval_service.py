from langchain_postgres import PGVector
from langchain_huggingface import (
    HuggingFaceEmbeddings,
)
from sqlalchemy import create_engine
from db.session import DATABASE_URL



# ====================================
# EMBEDDING MODEL
# ====================================

embedding_model = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2"
)


# ====================================
# VECTOR STORE
# ====================================

vector_store = PGVector(

    embeddings=embedding_model,

    collection_name="rag_chunks",

    connection=DATABASE_URL,
)