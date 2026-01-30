from fastapi import APIRouter, Depends
from core.security import get_current_user, AuthUser

router = APIRouter(prefix="/ingest", tags=["ingestion"])

@router.get("/whoami")
def whoami(auth: AuthUser = Depends(get_current_user)):
    return {"id": auth.id, "email": auth.email}
