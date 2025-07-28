from ingestion.text.extract_text_from_pdf import extract_pdf_text_metadata
from ingestion.text.extract_text_from_docx import extract_docx_text_metadata
from ingestion.text.extract_text_from_txt import extract_txt_text_metadata
from pathlib import Path
import os

def test_real_pdf():
    project_root = Path(__file__).parent.parent
    data_folder = project_root / "db" / "texts"
    print("Available files:", os.listdir(data_folder))

    file_path = data_folder / "Des_van_Jaarsveldt.pdf"
    user_id = "test-user-001"
    result = extract_pdf_text_metadata(str(file_path), user_id)

    assert isinstance(result, dict)
    assert "text_chunks" in result
    assert isinstance(result["text_chunks"], list)
    assert len(result["text_chunks"]) > 0

    total_chunks = len(result["text_chunks"])
    print(f"\nExtracted {total_chunks} PDF text chunks with metadata:\n")

    for i, chunk in enumerate(result["text_chunks"]):
        print(f"\n--- Chunk {i + 1}/{total_chunks} ---")
        print(f"Page {chunk['page_number']}, PDF: {chunk['pdf_name']}, User: {chunk['user_id']}, Time: {chunk['timestamp']}")
        print(chunk["chunk_text"][:300], "...")

def test_real_docx():
    project_root = Path(__file__).parent.parent
    data_folder = project_root / "db" / "texts"
    file_path = data_folder / "Grellingen railway station.docx"  
    user_id = "test-user-001"
    result = extract_docx_text_metadata(str(file_path), user_id)

    assert isinstance(result, dict)
    assert "text_chunks" in result
    assert len(result["text_chunks"]) > 0

    total_chunks = len(result["text_chunks"])
    print(f"\nExtracted {total_chunks} DOCX text chunks with metadata:\n")

    for i, chunk in enumerate(result["text_chunks"]):
        print(f"\n--- Chunk {i + 1}/{total_chunks} ---")
        print(f"DOCX: {chunk['docx_name']}, User: {chunk['user_id']}, Time: {chunk['timestamp']}")
        print(chunk["chunk_text"][:300], "...")

def test_real_txt():
    project_root = Path(__file__).parent.parent
    data_folder = project_root / "db" / "texts"
    file_path = data_folder / "Adrian Conan Doyle.txt"  
    user_id = "test-user-001"
    result = extract_txt_text_metadata(str(file_path), user_id)

    assert isinstance(result, dict)
    assert "text_chunks" in result
    assert len(result["text_chunks"]) > 0

    total_chunks = len(result["text_chunks"])
    print(f"\nExtracted {total_chunks} TXT text chunks:\n")
    for i, chunk in enumerate(result["text_chunks"]):
        print(f"\n--- Chunk {i + 1}/{total_chunks} ---")
        print(f"TXT: {chunk['txt_name']}, User: {chunk['user_id']}, Time: {chunk['timestamp']}")
        print(chunk["chunk_text"][:300], "...")

if __name__ == "__main__":
    # test_real_pdf()
    # test_real_docx()
    test_real_txt()
