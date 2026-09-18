import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.reviews import router as reviews_router
from app.api.routes.vendors import router as vendors_router


logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="NTU Foodie Hub API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(reviews_router)
app.include_router(vendors_router)
