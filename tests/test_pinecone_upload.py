
import os
from data_upload.pinecone_service import upload_to_pinecone

def test_upload_one_file(
    file_type: str = 'txt',
    user_id: str = 'user123',
    record_id: str = 'rec456',
    upload_date: str = '2025-08-03',
    vectors: list[list[float]] | None = None,
) -> bool:
    
    # Use default sample vectors if none provided
    if vectors is None:
        vectors = [
            [0.4] * 512,
            [0.1] * 512,
        ]

    return upload_to_pinecone(
        file_type=file_type,
        user_id=user_id,
        record_id=record_id,
        vectors=vectors,
        upload_date=upload_date,
    )


def main():
    success = test_upload_one_file()
    if success:
        print('Upload succeeded!')
    else:
        print('Upload failed.')

if __name__ == '__main__':
    main()
