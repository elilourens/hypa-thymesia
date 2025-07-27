import os
from dotenv import load_dotenv
from fastapi import APIRouter, UploadFile, File
#from ..db import image_db
from supabase import create_client, Client
from uuid import uuid4
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from io import BytesIO

#example for testing
BASE_DIR = Path(__file__).resolve().parent.parent 
image_path = BASE_DIR / "db" / "images" / "cat.jpg"

load_dotenv()
router = APIRouter()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url,key)

from uuid import uuid4
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import os



#SupaBase Image bucket interactions: 

def upload_image_to_bucket(file_content: bytes, filename: str, bucket: str = "images") -> str | None:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png"]:
        return None

    try:
        img = Image.open(BytesIO(file_content))
        img.verify()
    except Exception:
        return None

    file_path = f"uploads/{uuid4()}_{filename}"
    response = supabase.storage.from_(bucket).upload(file_path, file_content)

    return file_path if response else None

def delete_image_from_bucket(filepath: str, bucket: str = "images") -> bool:
    try:
        res = supabase.storage.from_(bucket).remove([filepath])
        return any(obj.get("name") == filepath for obj in res)
    except Exception as e:
        print(f"Deletion failed: {e}")
        return False

def wipe_images_from_bucket(bucket: str = "images") -> str:
    result = supabase.storage.empty_bucket(bucket)
    return result







#@router.post("/image/add/")
#async def add_image()