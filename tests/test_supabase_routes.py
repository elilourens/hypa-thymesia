import os
from pathlib import Path
from routes.image_routes import (
    upload_image_to_bucket,
    delete_image_from_bucket,
    wipe_images_from_bucket,
)
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
image_path = BASE_DIR / "db" / "images" / "cat.jpg"

def test_upload():
    with open(image_path, "rb") as f:
        file_bytes = f.read()
    filename = image_path.name
    uploaded_path = upload_image_to_bucket(file_bytes, filename)
    print("📤 Upload test:")
    print("→ Success:", bool(uploaded_path))
    print("→ Path:", uploaded_path)

def test_delete(file_path):
    result = delete_image_from_bucket(file_path)
    print("🗑️ Delete test:")
    print("→ Success:", result)

def test_wipe():
    result = wipe_images_from_bucket()
    print("🚿 Wipe test:")
    print("→ Result:", result)

if __name__ == "__main__":
    #test_upload()

    #test_delete("uploads/58c2a69e-8166-42e0-8ffd-8c0c20d8b5e2_cat.jpg")
    # Use the printed path from upload to delete it here manually:
    # test_delete("uploads/1234_uuid_cat.jpg")
    test_wipe()
