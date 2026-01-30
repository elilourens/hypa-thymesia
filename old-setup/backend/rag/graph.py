"""
rag_graph.py
Minimal RAG pipeline for Pinecone query endpoint with improved agent for group selection
and query simplification.
"""

import os
import json
import logging
from typing import TypedDict, Optional, List

import httpx
from pydantic import BaseModel, Field, ValidationError
from langgraph.graph import StateGraph, START, END
# ⚠️ TODO: migrate to langchain-ollama package
from langchain.chat_models import ChatOllama
from langchain.prompts import ChatPromptTemplate

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
RETRIEVER_URL = os.getenv("RETRIEVER_URL", "http://localhost:8000/api/v1/ingest/query")
GROUPS_URL    = os.getenv("GROUPS_URL",    "http://localhost:8000/api/v1/groups")

OLLAMA_URL    = os.getenv("OLLAMA_URL",    "http://localhost:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL",  "mistral")
DOC_PREVIEW_CHARS = int(os.getenv("DOC_PREVIEW_CHARS", 50000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag_graph")
logging.getLogger("httpx").setLevel(logging.WARNING)   # silence httpx INFO logs

# -----------------------------------------------------------------------------
# STATE SCHEMA
# -----------------------------------------------------------------------------
class GraphState(TypedDict):
    question: str
    jwt: Optional[str]

    # Agent-selected RAG params
    query_text: Optional[str]
    top_k: Optional[int]
    group_id: Optional[str]

    groups: Optional[List[dict]]
    docs: Optional[str]
    raw: Optional[dict]
    answer: Optional[str]

# -----------------------------------------------------------------------------
# LLM
# -----------------------------------------------------------------------------
llm = ChatOllama(
    base_url=OLLAMA_URL,
    model=OLLAMA_MODEL
)

# -----------------------------------------------------------------------------
# TOOL NODE – fetch available groups
# -----------------------------------------------------------------------------
async def list_groups_tool(state: GraphState):
    headers = {"Authorization": f"Bearer {state.get('jwt')}"} if state.get("jwt") else {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(GROUPS_URL, headers=headers)
            r.raise_for_status()
            groups = r.json()
            logger.info(f"Fetched {len(groups)} groups")
    except Exception as e:
        logger.error(f"Could not fetch groups: {e}")
        groups = []
    return {"groups": groups}

# -----------------------------------------------------------------------------
# AGENT STEP – choose query params
# -----------------------------------------------------------------------------
class QueryParams(BaseModel):
    query_text: str
    top_k: int = Field(default=3, ge=1, le=5)
    group_id: Optional[str] = None


def clean_query(text: str) -> str:
    """Remove filler words like 'files about ...'"""
    stop_words = {"file", "files", "document", "documents", "about",
                  "regarding", "on", "what", "does", "say", "anything"}
    words = [w for w in text.split() if w.lower() not in stop_words]
    return " ".join(words) or text


def decide_query_params(state: GraphState):
    groups = state.get("groups", [])
    group_list = (
        "\n".join([f"- {g.get('name')} (id={g.get('group_id')})" for g in groups])
        if groups else "No groups available."
    )
    name_to_id = {g.get("name"): g.get("group_id") for g in groups}

    prompt = ChatPromptTemplate.from_template(
        """
You are a retrieval-parameter planner.

Available groups (name → id):
{group_list}

Respond ONLY with valid JSON. All three keys must be present:
{{
  "query_text": "cars",           // minimal topical keyword
  "top_k": 3,
  "group_id": null                // null if no group is specified by the user
}}

Rules:
- query_text: a SHORT keyword/phrase (1–3 words). Drop filler like "files about", "tell me about", "what does it say".
- top_k: 1–5
- group_id: null unless the user clearly names a group
Question:
{question}
"""
    )

    messages = prompt.format_messages(
        question=state["question"], group_list=group_list
    )

    res = llm.invoke(messages)
    raw_out = getattr(res, "content", "") or ""
    logger.info(f"Agent raw output: {raw_out}")

    try:
        parsed = QueryParams.parse_raw(raw_out)
        logger.info(f"Agent-selected parameters: {parsed.dict()}")
    except ValidationError as e:
        logger.warning(f"Validation failed: {e}")
        # Try loose JSON parse
        try:
            data = json.loads(raw_out)
        except Exception:
            data = {}
        parsed = QueryParams(
            query_text=data.get("query_text", state["question"]),
            top_k=data.get("top_k") or 3,
            group_id=data.get("group_id")
        )
        logger.info(f"Salvaged parameters: {parsed.dict()}")

    gid = parsed.group_id
    if gid and gid.lower() == "null":
        gid = None
    elif gid and gid in name_to_id:
        gid = name_to_id[gid]

    return {
        "query_text": clean_query(parsed.query_text or state["question"]),
        "top_k":  3,
        "group_id": gid,  # stays None if not needed
    }

# -----------------------------------------------------------------------------
# RETRIEVER
# -----------------------------------------------------------------------------
async def retrieve_docs(state: GraphState):
    payload = {
        "query_text": state.get("query_text"),
        "top_k": max(1, min(state.get("top_k", 3), 5)),
        "group_id": state.get("group_id"),
        "route": "text"
    }
    headers = {"Authorization": f"Bearer {state.get('jwt')}"} if state.get("jwt") else {}

    logger.info(f"Retrieving docs with payload: {payload}")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(RETRIEVER_URL, json=payload, headers=headers)
            r.raise_for_status()
            result = r.json()
            logger.info(f"Pinecone response: {json.dumps(result)[:500]}...")
    except Exception as e:
        logger.error(f"Retriever error: {e}")
        return {"docs": "", "raw": {"error": str(e)}}

    matches = result.get("matches", [])
    if not matches:
        logger.info("No matches found by retriever.")
        return {"docs": "", "raw": result}

    context_blocks = []
    for i, m in enumerate(matches, start=1):
        md = m.get("metadata", {})
        # use 'text' field if present, else 'preview'
        snippet = (md.get("text") or md.get("preview") or "")[:DOC_PREVIEW_CHARS]
        context_blocks.append(
            f"[{i}] Source: {md.get('title','unknown')} "
            f"(uploaded {md.get('upload_date','N/A')})\n{snippet}"
        )

    docs_text = "\n\n".join(context_blocks)
    return {"docs": docs_text, "raw": result}

# -----------------------------------------------------------------------------
# ANSWER
# -----------------------------------------------------------------------------
def answer_with_context(state: GraphState):
    prompt = ChatPromptTemplate.from_template(
        """You are a concise and helpful AI assistant.

Use the provided context below ONLY when it is relevant.
If no relevant context is available, say: "No relevant documents found."
When talking about files or documents be clear about if you are talking about user uploaded files or documents which is the title in the returned context or sub files: files found within the parent file.

Context:
{docs}

Question:
{question}
"""
    )

    messages = prompt.format_messages(
        question=state.get("question", ""),
        docs=state.get("docs", "")
    )

    try:
        res = llm.invoke(messages)
        answer_text = getattr(res, "content", None) or str(res)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        answer_text = f"⚠️ Error generating answer: {e}"

    return {"answer": answer_text}

# -----------------------------------------------------------------------------
# BUILD GRAPH
# -----------------------------------------------------------------------------
graph = StateGraph(GraphState)

graph.add_node("list_groups", list_groups_tool)
graph.add_node("decide_params", decide_query_params)
graph.add_node("retrieve", retrieve_docs)
graph.add_node("answer", answer_with_context)

graph.add_edge(START, "list_groups")
graph.add_edge("list_groups", "decide_params")
graph.add_edge("decide_params", "retrieve")
graph.add_edge("retrieve", "answer")
graph.add_edge("answer", END)

compiled_graph = graph.compile()

# -----------------------------------------------------------------------------
# HELPER
# -----------------------------------------------------------------------------
async def run_pipeline(question: str, jwt: Optional[str] = None) -> dict:
    state: GraphState = {"question": question, "jwt": jwt}
    logger.info(f"Running pipeline for question: {question}")
    result = await compiled_graph.invoke(state)
    logger.info("Pipeline completed.")
    return result
