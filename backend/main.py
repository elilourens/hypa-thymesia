from fastapi import FastAPI
from routers.ingest import router

app = FastAPI()
app.include_router(router)
