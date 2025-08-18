# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.ingest import router


def create_app() -> FastAPI:
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=False,  # keep False unless you're using cookies
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
        expose_headers=["Content-Length"],
        max_age=86400,
    )

    app.include_router(router)  # your APIRouter from ingest.py
    return app

app = create_app()
