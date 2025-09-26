from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from rag.graph import compiled_graph           # ✅ import the compiled graph
from core.security import get_current_user, AuthUser

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatRequest(BaseModel):
    question: str

@router.post("")
async def chat_endpoint(req: ChatRequest, auth: AuthUser = Depends(get_current_user)):
    # ✅ forward the raw token into the graph state
    state = {"question": req.question, "jwt": auth.token}
    result = await compiled_graph.ainvoke(state)

    return {
        "answer": result.get("answer", ""),
        "sources": result.get("raw", {})
    }
