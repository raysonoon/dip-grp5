from fastapi import FastAPI

from app.api.routes.chat import router as chat_router
from app.api.routes.reviews import router as reviews_router
from app.api.routes.vendors import router as vendors_router


app = FastAPI(
    title="NTU Foodie Hub API",
    version="0.1.0",
)
app.include_router(chat_router)
app.include_router(reviews_router)
app.include_router(vendors_router)
