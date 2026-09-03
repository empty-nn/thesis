from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.model_registry import load_models, unload_models
from routers import auth, chat, external_knowledge, health, memory, retrieval_debug


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load SentenceTransformer + CrossEncoder once for the whole API process.
    load_models()
    yield
    unload_models()


app = FastAPI(
    title="Travel Guide Assistant API",
    version="0.1.0",
    lifespan=lifespan,
)

def _allowed_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return origins or [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(retrieval_debug.router, prefix="/api")
app.include_router(external_knowledge.router, prefix="/api")
