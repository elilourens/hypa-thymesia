from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

ALLOWED_MODALITIES = {"text", "image"}

class QueryRequest(BaseModel):
    query_text: Optional[str] = None
    image_b64: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=200)
    route: Optional[str] = None  # "text" | "image" | None
    group_id: Optional[str] = None 

class QueryMatch(BaseModel):
    id: str
    score: float
    metadata: Dict[str, Any]

class QueryResponse(BaseModel):
    matches: List[QueryMatch]
    top_k: int
    route: str
    namespace: str
