
import chromadb
from chromadb.config import Settings

client = chromadb.HttpClient(
    host="localhost",      
    port=8000,
    ssl=False,             
    headers=None,          
    settings=Settings(),   
    tenant="default_tenant",
    database="default_database",
)

collection = client.get_or_create_collection(
    name="my_collection",
    metadata={"project": "alpha"}
)
'''
collection.add(
    ids=["doc1", "doc2"],
    documents=["Here’s the first text.", "And here’s the second."],
    metadatas=[{"source": "notion"}, {"source": "google-docs"}],
    
)
'''
# this should now succeed
print(client.heartbeat())
print(f"Collection now has {collection.count()} items.")

'''
'''