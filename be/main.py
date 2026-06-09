from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from routers import data_building_router
import logging
import urllib3

urllib3.disable_warnings()

logger = logging.getLogger(__name__)

# setup_logging()
app = FastAPI(
    title="Variance Cost Calculation API",
    description="API for running single and bulk RFC cost calculations.",
    version="1.0.0",
    docs_url="/api",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Filename"]
)

app.include_router(data_building_router)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",             
        host="localhost",
        port=8001,
        reload=True,             
    )