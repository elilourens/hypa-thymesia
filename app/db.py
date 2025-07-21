import ollama
import numpy as np
import chromadb
from chromadb.config import Settings


class OllamaEmbeddingFunction:
    
    def __init__(self, model: str = "mxbai-embed-large"):
        self.model = model
        self._name = f"ollama-{model}"

    def name(self) -> str:
        return self._name

    def __call__(self, input: list[str]) -> np.ndarray:
        
        resp = ollama.embed(model=self.model, input=input)
        embeddings = resp["embeddings"]        # List[List[float]]
        return np.array(embeddings)            # <-- has .tolist()

    
    embed_documents = __call__
    embed_query = __call__


class ChromaDB:
    """
    Wraps a Chroma HTTP client + collection + Ollama embedder.
    Both add_texts() and query() auto‑vectorize via Ollama.
    """
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        ssl: bool = False,
        tenant: str = "default_tenant",
        database: str = "default_database",
        collection_name: str = "my_collection",
        collection_metadata: dict | None = None,
        embedder: OllamaEmbeddingFunction | None = None,
    ):
        #embedder defaults to Ollama
        self.embedder = embedder or OllamaEmbeddingFunction()

        #Chroma HTTP client
        self.client = chromadb.HttpClient(
            host=host,
            port=port,
            ssl=ssl,
            headers=None,
            settings=Settings(),
            tenant=tenant,
            database=database,
        )

        # Create/get
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata=collection_metadata or {},
            embedding_function=self.embedder,   # ensures correct dim & auto-embed
        )

    def add_texts(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict] | None = None,
    ):
        metadatas = metadatas or [{}] * len(documents)
        embeddings = self.embedder.embed_documents(documents)
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self,
        query: str,
        n_results: int = 1,
        include: list[str] | None = None,
    ) -> dict:
        include = include or ["documents", "metadatas"]
        return self.collection.query(
            query_texts=[query],
            n_results=n_results,
            include=include,
        )

    def count(self) -> int:
        return self.collection.count()
