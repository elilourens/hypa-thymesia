import os
from dotenv import load_dotenv
from fastapi import APIRouter, UploadFile, File
#from ..db import image_db
from supabase import create_client, Client
from uuid import uuid4
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent 
image_path = BASE_DIR / "db" / "images" / "cat.jpg"
load_dotenv()
router = APIRouter()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url,key)

def upload_image_to_bucket(file_content: bytes, filename: str, bucket: str = "images") -> str:
    file_path = f"uploads/{uuid4()}_{filename}"

    supabase.storage.from_(bucket).upload(file_path, file_content)

    return file_path

def main():
    
    with open(image_path, "rb") as f:
        file_bytes = f.read()
    
    filename = os.path.basename(image_path)
    uploaded_path = upload_image_to_bucket(file_bytes,filename)
    public_url = supabase.storage.from_("images").get_public_url(uploaded_path)
    print("📎 Public URL:", public_url)

if __name__ == "__main__":
    main()



#@router.post("/image/add/")
#async def add_image()