# app/api/routes/storage.py
from fastapi import APIRouter, Depends, HTTPException, Query
from core.security import get_current_user, AuthUser
from core.deps import get_supabase

router = APIRouter(prefix="/storage", tags=["storage"])

@router.get("/signed-url")
def get_signed_url(
    bucket: str = Query(...),
    path: str = Query(...),
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """
    Lazily generate a signed URL for any object in Supabase storage.
    """
    try:
        res = supabase.storage.from_(bucket).create_signed_url(path, expires_in=3600)
        signed_url = res.get("signedURL")
        if not signed_url:
            raise HTTPException(500, detail="Supabase did not return a signed URL.")
        return {"signed_url": signed_url}
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to create signed URL: {e}")
