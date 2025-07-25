# image_db.py

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import OpenCLIPEmbeddingFunction
from chromadb.utils.data_loaders import ImageLoader
from pathlib import Path

class image_chroma:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8001,
        ssl: bool = False,
        tenant: str = "default_tenant",
        database: str = "default_database",
        collection_name: str = "my_images",
        collection_metadata: dict | None = None,
        embedder: OpenCLIPEmbeddingFunction | None = None,
    ):
        
        metadata = collection_metadata or {"created_by": "image_chroma"}

        self.embedder = embedder or OpenCLIPEmbeddingFunction()
        self.loader = ImageLoader()  

        self.client = chromadb.HttpClient(
            host=host,
            port=port,
            ssl=ssl,
            settings=Settings(),
            tenant=tenant,
            database=database,
        )

        # register both the embedder and the loader
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata=metadata,
            embedding_function=self.embedder,
            data_loader=self.loader,
        )

    def add_folder(
        self,
        folder_path: str,
        batch_size: int = 32,
    ) -> int:
        
        # find all .jpg/.png files
        image_paths = sorted(Path(folder_path).glob("*.[pj][pn]g"))
        uris = [str(p) for p in image_paths]

        total = 0
        for i in range(0, len(uris), batch_size):
            batch = uris[i : i + batch_size]
            ids = [Path(uri).stem for uri in batch]
            # attach a non-empty metadata dict per image
            metadatas = [{"filename": Path(uri).name} for uri in batch]

            self.collection.add(
                ids=ids,
                uris=batch,
                metadatas=metadatas,
            )
            total += len(batch)

        return total

    def query_by_text(self, text: str, n_results: int = 5, include=None):
        include = include or ["uris", "metadatas", "distances", "documents"]
        return self.collection.query(
            query_texts=[text],
            n_results=n_results,
            include=include,
        )

    def count(self) -> int:
        return self.collection.count()
