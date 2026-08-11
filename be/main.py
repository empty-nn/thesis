from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.model_registry import load_models, unload_models
from routers import auth, chat, health, memory, retrieval_debug


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

# Angular dev server.
# Add your production frontend origin when you deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(retrieval_debug.router, prefix="/api")
