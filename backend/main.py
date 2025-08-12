from fastapi import FastAPI
from routers.ingest import router as ingest_router

app = FastAPI()
app.include_router(ingest_router)
