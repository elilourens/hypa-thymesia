# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import all_routers  # keep your current imports

app = FastAPI(title="SmartQuery API")

# Allow your Nuxt dev origins (adjust if you use a different port/host)
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # do NOT use "*" with allow_credentials=True
    allow_credentials=True,          # ok if you ever use cookies; harmless otherwise
    allow_methods=["*"],             # or ["GET","POST","DELETE","OPTIONS"]
    allow_headers=["*"],             # at least include "Authorization","Content-Type"
)

# keep your existing router mounting/prefix
for r in all_routers:
    app.include_router(r, prefix="/api/v1")
