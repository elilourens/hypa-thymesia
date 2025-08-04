from fastapi import FastAPI
from app.routers.ingest import router as ingest_router

app = FastAPI()
app.include_router(ingest_router)
