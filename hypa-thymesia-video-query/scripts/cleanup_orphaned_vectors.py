"""
Cleanup script to remove orphaned video frame and transcript vectors from Pinecone.

Orphaned vectors are those whose corresponding files no longer exist in Supabase storage
or whose video documents have been deleted from app_doc_meta.

Usage:
    python scripts/cleanup_orphaned_vectors.py --dry-run    # Preview what would be deleted
    python scripts/cleanup_orphaned_vectors.py              # Actually delete orphaned vectors
"""
import os
import sys
import argparse
from typing import Set, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone
from supabase import create_client

# Initialize clients
PINECONE_KEY = os.getenv("PINECONE_API_KEY") or os.getenv("PINECONE_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

if not PINECONE_KEY:
    raise RuntimeError("Missing PINECONE_API_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY")

pc = Pinecone(api_key=PINECONE_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Index names
VIDEO_FRAME_INDEX = os.getenv("PINECONE_VIDEO_FRAME_INDEX_NAME", "video-frames")
VIDEO_TRANSCRIPT_INDEX = os.getenv("PINECONE_VIDEO_TRANSCRIPT_INDEX_NAME", "video-transcripts")

# Bucket names
VIDEO_FRAMES_BUCKET = os.getenv("VIDEO_FRAMES_BUCKET", "video-frames")


def get_valid_video_ids() -> Set[str]:
    """Get all valid video document IDs from Supabase."""
    print("Fetching valid video IDs from app_doc_meta...")

    response = supabase.table("app_doc_meta").select("doc_id").eq("modality", "video").execute()

    valid_ids = {row["doc_id"] for row in response.data}
    print(f"  Found {len(valid_ids)} valid video documents")
    return valid_ids


def get_valid_storage_paths(bucket: str) -> Set[str]:
    """Get all valid storage paths from a Supabase bucket."""
    print(f"Fetching valid storage paths from bucket '{bucket}'...")

    valid_paths = set()

    try:
        # List all folders (user_ids) in the bucket
        folders = supabase.storage.from_(bucket).list()

        for folder in folders:
            if folder.get("id") is None:  # It's a folder
                folder_name = folder["name"]
                # List contents of each user folder
                try:
                    subfolders = supabase.storage.from_(bucket).list(folder_name)
                    for subfolder in subfolders:
                        if subfolder.get("id") is None:  # Video folder
                            video_folder = f"{folder_name}/{subfolder['name']}"
                            # List frames in video folder
                            try:
                                files = supabase.storage.from_(bucket).list(video_folder)
                                for file in files:
                                    if file.get("id"):  # It's a file
                                        path = f"{video_folder}/{file['name']}"
                                        valid_paths.add(path)
                            except Exception as e:
                                print(f"  Warning: Could not list {video_folder}: {e}")
                        elif subfolder.get("id"):  # Direct file in user folder
                            path = f"{folder_name}/{subfolder['name']}"
                            valid_paths.add(path)
                except Exception as e:
                    print(f"  Warning: Could not list {folder_name}: {e}")
    except Exception as e:
        print(f"  Error listing bucket: {e}")

    print(f"  Found {len(valid_paths)} valid storage paths")
    return valid_paths


def list_all_pinecone_vectors(index_name: str) -> List[Dict[str, Any]]:
    """List all vectors from a Pinecone index with their metadata."""
    print(f"Fetching vectors from Pinecone index '{index_name}'...")

    index = pc.Index(index_name)
    all_vectors = []

    # Get index stats to find all namespaces
    stats = index.describe_index_stats()
    namespaces = list(stats.get("namespaces", {}).keys())

    if not namespaces:
        namespaces = [""]  # Default namespace

    print(f"  Found {len(namespaces)} namespaces: {namespaces[:5]}{'...' if len(namespaces) > 5 else ''}")

    for namespace in namespaces:
        print(f"  Processing namespace: '{namespace or '(default)'}'...")

        # Use list operation to get all vector IDs in namespace
        try:
            # Pinecone list returns paginated results
            vector_ids = []
            for ids_batch in index.list(namespace=namespace):
                vector_ids.extend(ids_batch)

            if not vector_ids:
                continue

            print(f"    Found {len(vector_ids)} vector IDs")

            # Fetch vectors in batches to get metadata
            batch_size = 100
            for i in range(0, len(vector_ids), batch_size):
                batch_ids = vector_ids[i:i + batch_size]
                fetch_response = index.fetch(ids=batch_ids, namespace=namespace)

                for vec_id, vec_data in fetch_response.vectors.items():
                    all_vectors.append({
                        "id": vec_id,
                        "namespace": namespace,
                        "metadata": vec_data.metadata or {},
                    })

        except Exception as e:
            print(f"    Error processing namespace '{namespace}': {e}")
            continue

    print(f"  Total vectors fetched: {len(all_vectors)}")
    return all_vectors


def find_orphaned_frame_vectors(
    vectors: List[Dict[str, Any]],
    valid_video_ids: Set[str],
    valid_storage_paths: Set[str],
) -> List[Dict[str, Any]]:
    """Find frame vectors that are orphaned."""
    orphaned = []

    for vec in vectors:
        metadata = vec["metadata"]
        video_id = metadata.get("video_id")
        storage_path = metadata.get("storage_path")

        is_orphaned = False
        reason = []

        # Check if video document exists
        if video_id and video_id not in valid_video_ids:
            is_orphaned = True
            reason.append(f"video_id '{video_id}' not in app_doc_meta")

        # Check if storage file exists
        if storage_path and storage_path not in valid_storage_paths:
            is_orphaned = True
            reason.append(f"storage_path '{storage_path}' not in bucket")

        if is_orphaned:
            vec["orphan_reason"] = "; ".join(reason)
            orphaned.append(vec)

    return orphaned


def find_orphaned_transcript_vectors(
    vectors: List[Dict[str, Any]],
    valid_video_ids: Set[str],
) -> List[Dict[str, Any]]:
    """Find transcript vectors that are orphaned (video document deleted)."""
    orphaned = []

    for vec in vectors:
        metadata = vec["metadata"]
        video_id = metadata.get("video_id")

        if video_id and video_id not in valid_video_ids:
            vec["orphan_reason"] = f"video_id '{video_id}' not in app_doc_meta"
            orphaned.append(vec)

    return orphaned


def delete_vectors(index_name: str, vectors: List[Dict[str, Any]], dry_run: bool = True):
    """Delete orphaned vectors from Pinecone."""
    if not vectors:
        print("No vectors to delete.")
        return

    # Group by namespace
    by_namespace: Dict[str, List[str]] = {}
    for vec in vectors:
        ns = vec["namespace"]
        if ns not in by_namespace:
            by_namespace[ns] = []
        by_namespace[ns].append(vec["id"])

    index = pc.Index(index_name)

    for namespace, ids in by_namespace.items():
        if dry_run:
            print(f"  [DRY RUN] Would delete {len(ids)} vectors from namespace '{namespace or '(default)'}'")
        else:
            print(f"  Deleting {len(ids)} vectors from namespace '{namespace or '(default)'}'...")
            # Delete in batches
            batch_size = 100
            for i in range(0, len(ids), batch_size):
                batch = ids[i:i + batch_size]
                index.delete(ids=batch, namespace=namespace)
            print(f"    Deleted {len(ids)} vectors")


def main():
    parser = argparse.ArgumentParser(description="Cleanup orphaned video vectors from Pinecone")
    parser.add_argument("--dry-run", action="store_true", help="Preview deletions without actually deleting")
    parser.add_argument("--frames-only", action="store_true", help="Only cleanup frame vectors")
    parser.add_argument("--transcripts-only", action="store_true", help="Only cleanup transcript vectors")
    parser.add_argument("--skip-storage-check", action="store_true", help="Skip checking Supabase storage (faster)")
    args = parser.parse_args()

    if args.dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No vectors will be deleted")
        print("=" * 60)

    print()

    # Get valid video IDs from Supabase
    valid_video_ids = get_valid_video_ids()
    print()

    # Get valid storage paths (unless skipped)
    valid_storage_paths = set()
    if not args.skip_storage_check and not args.transcripts_only:
        valid_storage_paths = get_valid_storage_paths(VIDEO_FRAMES_BUCKET)
        print()

    # Process frame vectors
    if not args.transcripts_only:
        print("=" * 60)
        print("PROCESSING VIDEO FRAME VECTORS")
        print("=" * 60)

        frame_vectors = list_all_pinecone_vectors(VIDEO_FRAME_INDEX)
        print()

        if args.skip_storage_check:
            # Only check video_id
            orphaned_frames = [
                {**v, "orphan_reason": f"video_id '{v['metadata'].get('video_id')}' not in app_doc_meta"}
                for v in frame_vectors
                if v["metadata"].get("video_id") not in valid_video_ids
            ]
        else:
            orphaned_frames = find_orphaned_frame_vectors(
                frame_vectors, valid_video_ids, valid_storage_paths
            )

        print(f"Found {len(orphaned_frames)} orphaned frame vectors")

        if orphaned_frames:
            print("\nOrphaned frame vectors:")
            for vec in orphaned_frames[:10]:  # Show first 10
                print(f"  - {vec['id']}: {vec['orphan_reason']}")
            if len(orphaned_frames) > 10:
                print(f"  ... and {len(orphaned_frames) - 10} more")
            print()

            delete_vectors(VIDEO_FRAME_INDEX, orphaned_frames, dry_run=args.dry_run)
        print()

    # Process transcript vectors
    if not args.frames_only:
        print("=" * 60)
        print("PROCESSING VIDEO TRANSCRIPT VECTORS")
        print("=" * 60)

        transcript_vectors = list_all_pinecone_vectors(VIDEO_TRANSCRIPT_INDEX)
        print()

        orphaned_transcripts = find_orphaned_transcript_vectors(
            transcript_vectors, valid_video_ids
        )

        print(f"Found {len(orphaned_transcripts)} orphaned transcript vectors")

        if orphaned_transcripts:
            print("\nOrphaned transcript vectors:")
            for vec in orphaned_transcripts[:10]:  # Show first 10
                print(f"  - {vec['id']}: {vec['orphan_reason']}")
            if len(orphaned_transcripts) > 10:
                print(f"  ... and {len(orphaned_transcripts) - 10} more")
            print()

            delete_vectors(VIDEO_TRANSCRIPT_INDEX, orphaned_transcripts, dry_run=args.dry_run)
        print()

    print("=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)

    if args.dry_run:
        print("\nThis was a dry run. Run without --dry-run to actually delete vectors.")


if __name__ == "__main__":
    main()
