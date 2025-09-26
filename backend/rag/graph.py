from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langchain.chat_models import ChatOllama           # ✅ use ChatOllama as you asked
from langchain.prompts import ChatPromptTemplate
import httpx

# --- State schema ---
class GraphState(TypedDict):
    question: str
    jwt: Optional[str]
    docs: Optional[str]
    raw: Optional[dict]
    answer: Optional[str]

# --- LLM setup (Ollama Mistral) ---
llm = ChatOllama(
    base_url="http://localhost:11434",
    model="mistral"
)

# --- Retriever ---
async def retrieve_docs(state: GraphState):
    question = state["question"]
    token = state.get("jwt")

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {"query_text": question, "top_k": 5}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://localhost:8000/api/v1/ingest/query",
            json=payload,
            headers=headers
        )
        r.raise_for_status()
        result = r.json()

    # Format retrieved docs
    context_blocks = []
    for m in result.get("matches", []):
        md = m.get("metadata", {})
        context_blocks.append(
            f"Source: {md.get('title', 'unknown')} (uploaded {md.get('upload_date', 'N/A')})\n"
            f"{(md.get('text') or '')[:800]}"
        )

    return {
        "docs": "\n\n".join(context_blocks),
        "raw": result
    }

# --- Route decision ---
def decide_rag(state: GraphState):
    q = state["question"].lower()
    if any(k in q for k in ["doc", "file", "upload", "pdf", "report"]):
        return "retrieve"
    return "answer"

# --- Answer with context ---
def answer_with_context(state: GraphState):
    prompt = ChatPromptTemplate.from_template("""
You are a helpful AI assistant.
Use the provided context below when relevant.

Context:
{docs}

Question:
{question}
""")
    messages = prompt.format_messages(
        question=state["question"],
        docs=state.get("docs", "")
    )
    res = llm(messages)
    return {"answer": res.content}

# --- Build the graph ---
graph = StateGraph(GraphState)

graph.add_node("retrieve", retrieve_docs)
graph.add_node("answer", answer_with_context)

graph.add_conditional_edges(
    START,
    decide_rag,
    {"retrieve": "retrieve", "answer": "answer"}
)
graph.add_edge("retrieve", "answer")
graph.add_edge("answer", END)

# ✅ Compile graph to use in chat.py
compiled_graph = graph.compile()
