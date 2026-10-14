import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import warm_intent_embeddings
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.reviews import router as reviews_router
from app.api.routes.vendors import router as vendors_router


logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_in_threadpool(warm_intent_embeddings)
    yield

app = FastAPI(
    title="NTU Foodie Hub API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(reviews_router)
app.include_router(vendors_router)
