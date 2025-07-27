import os
from dotenv import load_dotenv
from supabase import create_client, Client
from uuid import uuid4
from pathlib import Path

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url,key)

def upload_text_to_bucket(file_content: bytes, filename: str, bucket: str = "texts") -> str | None:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".txt", ".pdf", ".docx"]:
        print(f"Unsupported file type: {ext}")
        return None
    
    file_path = f"uploads/{uuid4()}_{filename}"
    response = supabase.storage.from_(bucket).upload(file_path, file_content)
    return file_path if response else None

def delete_text_from_bucket(filepath: str, bucket: str = "texts") -> bool:
    try:
        res = supabase.storage.from_(bucket).remove([filepath])
        return any(obj.get("name") == filepath for obj in res)
    except Exception as e:
        print(f"Deletion failed: {e}")
        print(res)
        return False

def wipe_text_from_bucket(bucket: str = "texts") -> str:
    result = supabase.storage.empty_bucket(bucket)
    return result