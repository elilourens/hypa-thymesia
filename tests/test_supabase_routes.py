import os
from pathlib import Path
from routes.supabase_image_routes import (
    upload_image_to_bucket,
    delete_image_from_bucket,
    wipe_images_from_bucket,
)
from routes.supabase_text_routes import (
    upload_text_to_bucket,
    delete_text_from_bucket,
    wipe_text_from_bucket
)
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
image_path = BASE_DIR / "db" / "images" / "cat.jpg"
text_path = BASE_DIR / "db" / "texts" / "Des_van_Jaarsveldt.pdf"

def test_image_upload():
    with open(image_path, "rb") as f:
        file_bytes = f.read()
    filename = image_path.name
    uploaded_path = upload_image_to_bucket(file_bytes, filename)
    print("📤 Upload test:")
    print("→ Success:", bool(uploaded_path))
    print("→ Path:", uploaded_path)

def test_image_delete(file_path):
    result = delete_image_from_bucket(file_path)
    print("🗑️ Delete test:")
    print("→ Success:", result)

def test_image_wipe():
    result = wipe_images_from_bucket()
    print("🚿 Wipe test:")
    print("→ Result:", result)

def test_text_upload():
    with open(text_path, "rb") as f:
        file_bytes = f.read()
    filename = text_path.name
    uploaded_path = upload_text_to_bucket(file_bytes,filename)
    print("📤 Upload test:")
    print("→ Success:", bool(uploaded_path))
    print("→ Path:", uploaded_path)

def test_text_delete(file_path):
    result = delete_text_from_bucket(file_path)
    print("🗑️ Delete test:")
    print("→ Success:", result)

def test_text_wipe():
    result = wipe_text_from_bucket()
    print("🚿 Wipe test:")
    print("→ Result:", result)

if __name__ == "__main__":
    #test_image_upload()

    #test_image_delete("uploads/aef5ac0f-d34e-4589-95cb-e67a181f0fc4_cat.jpg")
    # Use the printed path from upload to delete it here manually:
    # test_image_delete("uploads/1234_uuid_cat.jpg")
    #test_image_wipe()


    #test_text_upload()
    #test_text_delete("uploads/95fed063-31b0-4357-8ba5-e1f91dfc79a7_Des_van_Jaarsveldt.pdf")
    test_text_wipe()